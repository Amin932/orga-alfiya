import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { AtSign, Clock3, FileText, ImagePlus, MessageCircle, Paperclip, Save, Trash2, Upload, X } from 'lucide-react'
import './collaboration.css'

type Author = { first_name: string; last_name: string; color: string | null }
type Comment = Author & { id: number; body: string; author_id: number; created_at: string; updated_at: string }
type Attachment = { id: number; file_name: string; mime_type: string; size_bytes: number; is_cover: boolean; uploaded_by: number }
type Activity = Author & { id: number; action: string; details: Record<string, unknown>; created_at: string }
type Collaboration = { comments: Comment[]; files: Attachment[]; activity: Activity[] }
type MentionUser = { id: number; first_name: string; last_name: string; color: string | null }
type MentionPole = { id: number; name: string; color: string }
type Mentions = { users: MentionUser[]; poles: MentionPole[] }
type Props = { cardId: number; projectId: number; viewer: { id: number; role: string }; onChanged: () => Promise<void> }

async function request<T>(path: string, method: 'GET' | 'POST' | 'PATCH' | 'DELETE' = 'GET', body?: unknown): Promise<T> {
  const r = await fetch(path, {method,credentials:'same-origin',
    headers: method === 'GET' ? undefined : {'X-Orga-Request':'1','Content-Type':'application/json'},
    body: body === undefined ? undefined : JSON.stringify(body)})
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Opération impossible')
  return data as T
}

function displayName(who: Author) {
  return [who.first_name, who.last_name].filter(Boolean).join(' ') || 'Membre'
}

function when(value: string) {
  return new Date(value).toLocaleString('fr-FR',{dateStyle:'short',timeStyle:'short'})
}
function renderMentions(text: string) {
  const regex = /@\[(.{1,100}?)\]\((user|pole):\d+\)/g
  const parts: (string | ReactNode)[] = []
  let last = 0; let match: RegExpExecArray | null
  while ((match = regex.exec(text)) !== null) {
    if (match.index > last) parts.push(text.slice(last, match.index))
    parts.push(<span className="co-mention" key={match.index}>@{match[1]}</span>)
    last = regex.lastIndex
  }
  parts.push(text.slice(last))
  return parts
}

const actionLabels: Record<string,string> = {
  card_created:'a créé la carte', card_updated:'a modifié la fiche',
  card_moved:'a déplacé la carte', card_trashed:'a envoyé la carte à la corbeille',
  card_restored:'a restauré la carte', assignees_changed:'a modifié les responsables',
  comment_created:'a ajouté un commentaire',comment_updated:'a modifié un commentaire',
  comment_deleted:'a supprimé un commentaire',file_added:'a joint un fichier',
  file_deleted:'a retiré un fichier',cover_changed:'a modifié la couverture',
  checklist_checked:'a mis à jour une tâche',checklist_created:'a créé une checklist',
  checklist_deleted:'a supprimé une checklist',checklist_item_added:'a ajouté une tâche',
  checklist_item_deleted:'a supprimé une tâche',checklist_item_updated:'a modifié une tâche',
  template_updated:'a rempli les informations du modèle',
}

export default function CollaborationV6({cardId,projectId,viewer,onChanged}: Props) {
  const [data,setData] = useState<Collaboration | null>(null)
  const [mentions,setMentions] = useState<Mentions>({users:[],poles:[]})
  const [body,setBody] = useState('')
  const [mentionOpen,setMentionOpen] = useState(false)
  const [editId,setEditId] = useState<number | null>(null)
  const [editText,setEditText] = useState('')
  const [error,setError] = useState('')
  const [busy,setBusy] = useState(false)
  const [fileBusy,setFileBusy] = useState(false)

  const reload = useCallback(async () => {
    const result = await request<Collaboration>('/api/cards/' + cardId + '/collaboration')
    setData(result)
  },[cardId])
  useEffect(() => {
    let active=true
    setData(null);setError('');setBody('');setEditId(null)
    void Promise.all([request<Collaboration>('/api/cards/' + cardId + '/collaboration'),
      request<Mentions>('/api/projects/' + projectId + '/mentions')])
      .then(([d,m])=>{if(active){setData(d);setMentions(m)}})
      .catch(e=>{if(active)setError(e.message)})
    return ()=>{active=false}
  },[cardId,projectId])

  async function act(callback:()=>Promise<unknown>) {
    setBusy(true);setError('')
    try {await callback();await reload()}
    catch(e){setError(e instanceof Error ? e.message : 'Opération impossible')}
    finally {setBusy(false)}
  }

  function addMention(kind:'user' | 'pole',id:number,label:string) {
    setBody(old => (old && !/\s$/.test(old) ? old + ' ' : old) + '@[' + label.replace(/[\]\r\n]/g,'') + '](' + kind + ':' + id + ') ')
    setMentionOpen(false)
  }
  async function addComment(e:FormEvent) {
    e.preventDefault()
    if (!body.trim())return
    await act(async () => {await request('/api/cards/' + cardId + '/comments','POST',{body:body.trim()});setBody('')})
  }
  async function updateComment(e:FormEvent) {
    e.preventDefault()
    if (editId===null || !editText.trim())return
    await act(async () => {await request('/api/cards/' + cardId + '/comments/' + editId,'PATCH',{body:editText.trim()});setEditId(null)})
  }
  async function removeComment(id:number) {
    if (!window.confirm('Supprimer ce commentaire ?'))return
    await act(() => request('/api/cards/' + cardId + '/comments/' + id,'DELETE'))
  }
  async function sendFile(input:HTMLInputElement) {
    const file = input.files?.[0]
    if (!file)return
    setFileBusy(true);setError('')
    try {
      if(file.size > 15*1024*1024) throw new Error('Le fichier ne doit pas dépasser 15 Mo.')
      const payload=new FormData();payload.append('file',file)
      const response = await fetch('/api/cards/' + cardId + '/attachments',{
        method:'POST',credentials:'same-origin',headers:{'X-Orga-Request':'1'},body:payload
      })
      const result = await response.json().catch(()=>({}))
      if(!response.ok) throw new Error(result.detail || 'Import impossible')
      await reload()
    } catch(e) {setError(e instanceof Error ? e.message : 'Échec du téléchargement')}
    finally {setFileBusy(false);input.value=''}
  }
  async function setCover(id:number|null) {
    await act(async()=>{
      await request('/api/cards/' + cardId + '/cover','POST',{attachment_id:id})
      await onChanged()
    })
  }
  async function removeFile(id:number) {
    if (!window.confirm('Retirer ce fichier de la carte ?'))return
    await act(async()=>{
      await request('/api/cards/' + cardId + '/attachments/' + id,'DELETE')
      await onChanged()
    })
  }
  const fileUrl=(id:number)=>'/api/cards/' + cardId + '/attachments/' + id
  return <div className="co-root">
    {error && <p className="kb-error" role="alert">{error}</p>}
    <section className="co-section">
      <div className="co-title"><Paperclip size={17}/><h3>Images et documents</h3><span>{data?.files.length || 0}</span></div>
      <p className="co-muted">Fichiers privés accessibles aux membres autorisés du projet. Maximum 15 Mo par fichier.</p>
      <label className="co-upload"><Upload size={16}/> {fileBusy?'Import en cours…':'Joindre un fichier'}
        <input aria-label="Choisir une image ou un document" disabled={fileBusy} type="file"
          accept=".png,.jpg,.jpeg,.webp,.gif,.pdf,.docx,.xlsx,.pptx,.txt"
          onChange={e => void sendFile(e.currentTarget)}/>
      </label>
      <div className="co-files">
        {data?.files.map(f=><div className="co-file" key={f.id}>
          {f.mime_type.startsWith('image/') ? <img src={fileUrl(f.id)} alt={f.file_name} loading="lazy"/> : <FileText size={24}/>}
          <div className="co-file-info"><a href={fileUrl(f.id)} target="_blank" rel="noreferrer">{f.file_name}</a>
            <small>{(f.size_bytes/1024/1024).toFixed(2)} Mo {f.is_cover?'· Couverture':''}</small></div>
          {f.mime_type.startsWith('image/') && <button disabled={busy} className="co-file-button" title={f.is_cover?'Retirer la couverture':'Afficher sur la carte'} onClick={() => void setCover(f.is_cover?null:f.id)}><ImagePlus size={16}/></button>}
          {(f.uploaded_by===viewer.id || viewer.role==='superadmin') && <button disabled={busy} className="co-file-button" title="Supprimer le fichier" onClick={()=>void removeFile(f.id)}><Trash2 size={15}/></button>}
        </div>)}
      </div>
    </section>
    <section className="co-section">
      <div className="co-title"><MessageCircle size={17}/><h3>Commentaires</h3><span>{data?.comments.length || 0}</span></div>
      {data?.comments.map(c => <article className="co-comment" key={c.id}>
        <div className="co-author-line">
          <span className="co-name" style={{borderColor:c.color||'#c0b5ab'}}>{displayName(c)}</span>
          <time>{when(c.created_at)}</time>
        </div>
        {editId===c.id ? <form onSubmit={e=>void updateComment(e)} className="co-comment-edit">
          <textarea maxLength={5000} rows={3} required value={editText} onChange={e=>setEditText(e.target.value)}/>
          <div className="co-actions"><button type="submit" disabled={busy || !editText.trim()}><Save size={14}/> Enregistrer</button><button type="button" onClick={()=>setEditId(null)}><X size={14}/> Annuler</button></div>
        </form> : <div className="co-body">{renderMentions(c.body)}</div>}
        <div className="co-comment-actions">
          {c.author_id===viewer.id && editId!==c.id && <button disabled={busy} type="button" onClick={()=>{setEditId(c.id);setEditText(c.body)}}>Modifier</button>}
          {(c.author_id===viewer.id || viewer.role==='superadmin') && <button disabled={busy} type="button" onClick={()=>void removeComment(c.id)}>Supprimer</button>}
        </div>
      </article>)}
      {!data?.comments.length && <p className="co-muted">Pas encore de commentaire sur cette carte.</p>}
      <form className="co-comment-form" onSubmit={e=>void addComment(e)}>
        <label>Écrire un commentaire<textarea value={body} onChange={e=>setBody(e.target.value)} maxLength={5000} rows={3} placeholder="Échanger avec les membres du BDE…" required/></label>
        <div className="co-comment-toolbar"><button type="button" onClick={()=>setMentionOpen(!mentionOpen)}><AtSign size={15}/> Mentionner</button><button type="submit" disabled={!body.trim() || busy}>Publier</button></div>
        {mentionOpen && <div className="co-mentions">
          <strong>Mentionner un membre</strong><div>{mentions.users.map(u=><button key={u.id} type="button" onClick={()=>addMention('user',u.id,[u.first_name,u.last_name].filter(Boolean).join(' '))}><span style={{backgroundColor:u.color||'#aa8c75'}}/> {u.first_name} {u.last_name}</button>)}</div>
          <strong>Mentionner un pôle</strong><div>{mentions.poles.map(p=><button key={p.id} type="button" onClick={()=>addMention('pole',p.id,p.name)}><span style={{backgroundColor:p.color}}/> {p.name}</button>)}</div>
        </div>}
      </form>
    </section>
    <section className="co-section">
      <div className="co-title"><Clock3 size={17}/><h3>Historique des actions</h3></div>
      <div className="co-timeline">{data?.activity.map(event=><div className="co-event" key={event.id}>
        <div><span className="co-name" style={{borderColor:event.color||'#c0b5ab'}}>{displayName(event)}</span> {actionLabels[event.action] || event.action}</div>
        <time>{when(event.created_at)}</time>
      </div>)}
        {!data?.activity.length && <p className="co-muted">L'historique débutera dès les prochaines actions.</p>}
      </div>
    </section>
  </div>
}
