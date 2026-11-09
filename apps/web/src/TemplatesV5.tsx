import { useEffect, useState, type FormEvent } from 'react'
import { ChevronDown, Plus, Save, Trash2, X } from 'lucide-react'
import './templates.css'

export type FieldSpec = { key: string; label: string; section: string; kind: 'text' | 'longtext' | 'choice' | 'yesno' | 'number' | 'date' | 'time'; options: string[] }
export type ListSpec = { title: string; items: string[] }
export type Template = { id: number; slug: string | null; name: string; official: boolean; created_by: number | null; fields: FieldSpec[]; checklists: ListSpec[] }
type CheckItem = { id: number; text: string; done: boolean; done_by_name: string | null; done_at: string | null }
type CheckList = { id: number; title: string; items: CheckItem[] }
type CardContent = { template_id: number | null; fields: FieldSpec[]; values: Record<string, string>; checklists: CheckList[] }

async function request<T>(path: string, method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE' = 'GET', body?: unknown): Promise<T> {
  const res = await fetch(path, { method, credentials: 'same-origin',
    headers: method === 'GET' ? undefined : { 'Content-Type': 'application/json', 'X-Orga-Request': '1' },
    body: body === undefined ? undefined : JSON.stringify(body) })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Opération impossible')
  return data as T
}

export async function listTemplates(): Promise<Template[]> {
  const result = await request<{templates: Template[]}>('/api/templates')
  return result.templates
}

function generatedKey(fields: FieldSpec[]): string {
  let index = fields.length + 1
  while (fields.some(f => f.key === 'field_' + index)) index++
  return 'field_' + index
}

export function TemplateLibrary({ viewer, onClose }: {viewer: {id: number; role: string}; onClose: () => void}) {
  const [templates, setTemplates] = useState<Template[]>([])
  const [selected, setSelected] = useState<number | 'new' | null>(null)
  const [name, setName] = useState('')
  const [fields, setFields] = useState<FieldSpec[]>([])
  const [checklists, setChecklists] = useState<ListSpec[]>([])
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')

  async function reload() { setTemplates(await listTemplates()) }
  useEffect(() => { void reload().catch(e => setMessage(e.message)) }, [])
  const current = templates.find(t => t.id === selected)
  const editable = selected === 'new' || !!current && (viewer.role === 'superadmin' || (!current.official && current.created_by === viewer.id))
  function select(t: Template | null) {
    setSelected(t ? t.id : 'new'); setName(t?.name ?? ''); setFields(t?.fields.map(f => ({...f, options:[...f.options]})) ?? [])
    setChecklists(t?.checklists.map(c => ({title:c.title,items:[...c.items]})) ?? []); setMessage('')
  }
  function changeField(index: number, field: Partial<FieldSpec>) {
    setFields(previous => previous.map((x,i) => i === index ? {...x,...field} : x))
  }
  function changeList(index: number, updates: Partial<ListSpec>) {
    setChecklists(previous => previous.map((x,i) => i === index ? {...x,...updates} : x))
  }
  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!editable || !name.trim()) return
    setBusy(true); setMessage('')
    try {
      const payload = {name:name.trim(),fields,checklists}
      if (selected === 'new') await request('/api/templates','POST',payload)
      else await request('/api/templates/' + selected,'PUT',payload)
      await reload(); setSelected(null); setMessage('Modèle enregistré dans la bibliothèque commune.')
    } catch(e) { setMessage(e instanceof Error ? e.message : 'Erreur de sauvegarde') }
    finally {setBusy(false)}
  }
  async function remove() {
    if (!current || current.official || !editable || !window.confirm('Supprimer ce modèle ? Les cartes déjà créées seront conservées.')) return
    setBusy(true)
    try { await request('/api/templates/' + current.id,'DELETE'); await reload(); setSelected(null); setMessage('Modèle supprimé.') }
    catch(e) {setMessage(e instanceof Error ? e.message : 'Suppression impossible')}
    finally {setBusy(false)}
  }
  return <section className="tpl-library">
    <div className="tpl-heading"><div><span className="eyebrow">BIBLIOTHÈQUE COMMUNE</span><h1>Modèles de cartes</h1><p>Les modèles officiels sont protégés ; chaque membre peut proposer ses propres modèles.</p></div><button type="button" className="quiet-button" onClick={onClose}><X size={17}/> Retour aux projets</button></div>
    {message && <p className="tpl-message" role="status">{message}</p>}
    <div className="tpl-layout">
      <aside className="tpl-index"><button type="button" className="tpl-new" onClick={() => select(null)}><Plus size={17}/> Créer un modèle</button>
        {templates.map(t => <button type="button" key={t.id} className={'tpl-index-item' + (selected === t.id ? ' selected' : '')} onClick={() => select(t)}>
          <strong>{t.name}</strong><small>{t.official ? 'Modèle officiel' : 'Modèle personnalisé'}</small>
        </button>)}
      </aside>
      <div className="tpl-editor">
        {selected === null ? <div className="tpl-empty">Sélectionnez un modèle pour le consulter, ou créez votre propre modèle.</div> :
        <form onSubmit={submit}>
          <div className="tpl-editor-top"><h2>{selected === 'new' ? 'Nouveau modèle' : current?.name}</h2>
            {current?.official && <span className="tpl-official">Modèle officiel</span>}</div>
          <label className="tpl-label">Nom du modèle<input required maxLength={120} disabled={!editable} value={name} onChange={e => setName(e.target.value)}/></label>
          <div className="tpl-editor-title"><h3>Champs à compléter dans la carte</h3>
            {editable && <button type="button" onClick={() => setFields(old => [...old,{key:generatedKey(old),section:'Description',label:'Nouveau champ',kind:'text',options:[]}])}><Plus size={15}/> Champ</button>}</div>
          {fields.map((f,i) => <div className="tpl-field-editor" key={f.key}>
            <div className="tpl-editor-row"><label>Rubrique<input disabled={!editable} value={f.section} maxLength={90} onChange={e => changeField(i,{section:e.target.value})}/></label>
              <label>Libellé<input disabled={!editable} value={f.label} maxLength={180} onChange={e => changeField(i,{label:e.target.value})}/></label></div>
            <div className="tpl-editor-row"><label>Type<select disabled={!editable} value={f.kind} onChange={e => changeField(i,{kind:e.target.value as FieldSpec['kind'],options:e.target.value === 'choice' ? (f.options.length ? f.options : ['Option 1']) : []})}>
              <option value="text">Texte court</option><option value="longtext">Texte long</option><option value="choice">Sélection</option><option value="yesno">Oui / Non</option><option value="date">Date</option><option value="time">Heure</option><option value="number">Nombre</option>
            </select></label>
            {editable && <button type="button" className="tpl-remove" aria-label={'Supprimer le champ ' + f.label} onClick={() => setFields(v => v.filter((_,j) => i !== j))}><Trash2 size={16}/></button>}</div>
            {f.kind === 'choice' && <label>Options (une par ligne)<textarea disabled={!editable} value={f.options.join('\n')} onChange={e => changeField(i,{options:e.target.value.split('\n')})}/></label>}
          </div>)}
          <div className="tpl-editor-title"><h3>Checklists du modèle</h3>{editable && <button type="button" onClick={() => setChecklists(old => [...old,{title:'Nouvelle checklist',items:[]}])}><Plus size={15}/> Checklist</button>}</div>
          {checklists.map((group,i) => <div className="tpl-checklist-editor" key={i}>
            <div className="tpl-editor-row"><label>Nom de la checklist<input disabled={!editable} value={group.title} maxLength={120} onChange={e => changeList(i,{title:e.target.value})}/></label>
              {editable && <button type="button" className="tpl-remove" aria-label="Supprimer la checklist" onClick={() => setChecklists(old => old.filter((_,j) => j !== i))}><Trash2 size={16}/></button>}</div>
            {group.items.map((item,j) => <div className="tpl-item-row" key={j}><input disabled={!editable} maxLength={300} value={item} onChange={e => changeList(i,{items:group.items.map((s,n) => n === j ? e.target.value : s)})}/>
              {editable && <button type="button" aria-label="Enlever cette tâche" onClick={() => changeList(i,{items:group.items.filter((_,n) => n !== j)})}><X size={15}/></button>}</div>)}
            {editable && <button className="tpl-minor" type="button" onClick={() => changeList(i,{items:[...group.items,'Nouvelle tâche']})}><Plus size={15}/> Ajouter une tâche</button>}
          </div>)}
          {editable && <div className="tpl-save-row"><button className="primary-button" disabled={busy || !name.trim()}><Save size={16}/> Enregistrer le modèle</button>
            {current && !current.official && <button className="tpl-danger" type="button" disabled={busy} onClick={() => void remove()}><Trash2 size={15}/> Supprimer</button>}</div>}
          {!editable && <p className="tpl-note">Vous pouvez utiliser ce modèle pour vos cartes. Seul son créateur peut le modifier.</p>}
        </form>}
      </div>
    </div>
  </section>
}

export function CardTemplateContent({ cardId, onChanged }: {cardId: number; onChanged?: () => void}) {
  const [content, setContent] = useState<CardContent | null>(null)
  const [values, setValues] = useState<Record<string,string>>({})
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [newList, setNewList] = useState('')
  const [newItem, setNewItem] = useState<Record<number,string>>({})
  async function load(preserve = false) {
    const data = await request<CardContent>('/api/cards/' + cardId + '/template-content')
    setContent(data)
    if (!preserve) setValues(data.values)
  }
  useEffect(() => { let active = true
    request<CardContent>('/api/cards/' + cardId + '/template-content').then(data => { if(active){setContent(data);setValues(data.values)} }).catch(e=>{if(active)setError(e.message)})
    return () => {active = false}
  },[cardId])

  async function run(action: () => Promise<unknown>, preserve = true) {
    setBusy(true); setError(''); setNotice('')
    try {await action(); await load(preserve); onChanged?.(); setNotice('Modifications enregistrées.')}
    catch(e){setError(e instanceof Error ? e.message : 'Modification impossible')}
    finally {setBusy(false)}
  }
  async function saveFields(e: FormEvent) {
    e.preventDefault()
    await run(async () => { await request('/api/cards/' + cardId + '/template-values', 'PATCH', {values}) }, false)
  }
  const sections = [...new Set(content?.fields.map(f => f.section) ?? [])]
  return <div className="tpl-card-content">
    {error && <p className="kb-error" role="alert">{error}</p>}{notice && <p className="tpl-note" role="status">{notice}</p>}
    {!content && !error && <p>Chargement des rubriques…</p>}
    {!!content?.fields.length && <form onSubmit={saveFields} className="tpl-card-form">
      {sections.map(section => <details className="tpl-section" key={section} open>
        <summary><strong>{section}</strong><ChevronDown size={17}/></summary>
        <div className="tpl-section-content">{content.fields.filter(f => f.section === section).map(f =>
          <label key={f.key}>{f.label}
            {f.kind === 'longtext' ? <textarea rows={3} value={values[f.key] || ''} maxLength={20000} onChange={e=>setValues(old=>({...old,[f.key]:e.target.value}))}/> :
            f.kind === 'choice' || f.kind === 'yesno' ? <select value={values[f.key] || ''} onChange={e=>setValues(old=>({...old,[f.key]:e.target.value}))}>
              <option value="">À compléter</option>{(f.kind === 'yesno' ? ['Oui','Non'] : f.options).map(x => <option key={x} value={x}>{x}</option>)}
            </select> :
            <input type={f.kind === 'date' ? 'date' : f.kind === 'time' ? 'time' : f.kind === 'number' ? 'number' : 'text'}
              value={values[f.key] || ''} maxLength={f.kind === 'text' ? 20000 : undefined}
              placeholder="À compléter ultérieurement" onChange={e=>setValues(old=>({...old,[f.key]:e.target.value}))}/>}
          </label>)}</div>
      </details>)}
      <button className="tpl-card-save" type="submit" disabled={busy}><Save size={15}/> Enregistrer les informations</button>
    </form>}
    <div className="tpl-checklists">
      <h3>Checklists</h3>
      {content?.checklists.map(group => {
        const completed = group.items.filter(i => i.done).length
        return <div className="tpl-card-list" key={group.id}>
          <div className="tpl-card-list-head"><strong>{group.title}</strong><span>{completed}/{group.items.length}</span>
            <button type="button" disabled={busy} aria-label={'Supprimer la checklist ' + group.title} title="Supprimer la checklist" onClick={() => {if(window.confirm('Supprimer cette checklist de la carte ?')) void run(()=>request('/api/cards/' + cardId + '/checklists/' + group.id,'DELETE'))}}><Trash2 size={15}/></button></div>
          <div className="tpl-progress"><span style={{width:(group.items.length ? completed / group.items.length * 100 : 0)+'%'}}/></div>
          {group.items.map(item => <div className="tpl-card-item" key={item.id}>
            <label><input type="checkbox" checked={item.done} disabled={busy} onChange={e=>void run(()=>request('/api/cards/' + cardId + '/checklists/' + group.id + '/items/' + item.id + '/done','PATCH',{done:e.target.checked}))}/>
              <span className={item.done ? 'completed' : ''}>{item.text}{item.done && item.done_by_name && <small> — {item.done_by_name}</small>}</span></label>
            <button type="button" title="Supprimer cette tâche" disabled={busy} onClick={() => void run(()=>request('/api/cards/' + cardId + '/checklists/' + group.id + '/items/' + item.id,'DELETE'))}><X size={15}/></button>
          </div>)}
          <form className="tpl-inline-add" onSubmit={e=>{e.preventDefault(); const text=newItem[group.id]?.trim(); if(text) void run(async()=>{await request('/api/cards/' + cardId + '/checklists/' + group.id + '/items','POST',{text}); setNewItem(old=>({...old,[group.id]:''}))})}}>
            <input placeholder="Ajouter une tâche…" maxLength={300} value={newItem[group.id] || ''} onChange={e=>setNewItem(old=>({...old,[group.id]:e.target.value}))}/><button disabled={busy || !newItem[group.id]?.trim()}><Plus size={16}/></button>
          </form>
        </div>})}
      <form className="tpl-inline-add" onSubmit={e=>{e.preventDefault(); if(newList.trim()) void run(async()=>{await request('/api/cards/' + cardId + '/checklists','POST',{title:newList.trim()});setNewList('')})}}>
        <input value={newList} maxLength={120} placeholder="Nouvelle checklist…" onChange={e=>setNewList(e.target.value)}/><button disabled={busy || !newList.trim()}><Plus size={15}/> Ajouter</button>
      </form>
    </div>
  </div>
}
