import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { ArrowDown, ArrowLeft, ArrowUp, Check, FolderKanban, Mail, Plus, Save, ShieldCheck, Trash2, Users, X } from 'lucide-react'
import './admin-workspace.css'
import AdminTrash from './AdminTrash'

type Pole = { id: number; project_id: number; name: string; color: string; description: string }
type Project = { id: number; name: string; description: string; poles: Pole[] }
type Membership = { pole_id: number; position: number; name: string; color: string; project_id: number }
type Member = { id: number; first_name: string; last_name: string; email: string; role: 'member' | 'superadmin'; active: boolean; state: 'active' | 'pending' | 'disabled'; project_ids: number[]; poles: Membership[] }

async function request<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(path, { method: body === undefined ? 'GET' : 'POST', credentials: 'same-origin',
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json', 'X-Orga-Request': '1' },
    body: body === undefined ? undefined : JSON.stringify(body) })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Opération impossible')
  return data as T
}

export default function AdminWorkspace({ back }: { back: () => void }) {
  const [projects, setProjects] = useState<Project[]>([])
  const [members, setMembers] = useState<Member[]>([])
  const [tab, setTab] = useState<'members' | 'projects' | 'trash'>('members')
  const [selectedMember, setSelectedMember] = useState<number | null>(null)
  const [access, setAccess] = useState<number[]>([])
  const [poles, setPoles] = useState<number[]>([])
  const [inviteEmail, setInviteEmail] = useState('')
  const [inviteProjects, setInviteProjects] = useState<number[]>([])
  const [newProject, setNewProject] = useState('')
  const [newPole, setNewPole] = useState('')
  const [newPoleProject, setNewPoleProject] = useState('')
  const [newPoleColor, setNewPoleColor] = useState('#B57460')
  const [editProjectId, setEditProjectId] = useState<number | null>(null)
  const [editProjectName, setEditProjectName] = useState('')
  const [editProjectDescription, setEditProjectDescription] = useState('')
  const [editPoleId, setEditPoleId] = useState<number | null>(null)
  const [editPoleName, setEditPoleName] = useState('')
  const [editPoleDescription, setEditPoleDescription] = useState('')
  const [editPoleColor, setEditPoleColor] = useState('#B57460')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)

  const refresh = useCallback(async () => {
    const [workspace, people] = await Promise.all([
      request<{ projects: Project[] }>('/api/workspace'),
      request<Member[]>('/api/admin/directory')
    ])
    setProjects(workspace.projects); setMembers(people)
    return { projects: workspace.projects, members: people }
  }, [])

  useEffect(() => { void refresh().catch(e => setNotice(e.message)) }, [refresh])

  async function perform(action: () => Promise<unknown>) {
    setBusy(true); setNotice('')
    try {
      await action()
      const updated = await refresh()
      const member = updated.members.find(u => u.id === selectedMember)
      if (member) { setAccess(member.project_ids); setPoles(member.poles.map(p => p.pole_id)) }
      setNotice('Modifications enregistrées.')
    } catch (e) { setNotice(e instanceof Error ? e.message : 'Erreur inconnue') }
    finally { setBusy(false) }
  }

  function chooseMember(id: number | null) {
    setSelectedMember(id)
    const member = members.find(u => u.id === id)
    setAccess(member?.project_ids ?? [])
    setPoles(member?.poles.map(p => p.pole_id) ?? [])
  }

  function chooseProject(id: number | null) {
    const p = projects.find(p => p.id === id)
    setEditProjectId(id); setEditProjectName(p?.name ?? '')
    setEditProjectDescription(p?.description ?? '')
    choosePole(null)
  }

  function choosePole(id: number | null) {
    const p = projects.flatMap(project => project.poles).find(pole => pole.id === id)
    setEditPoleId(id); setEditPoleName(p?.name ?? '')
    setEditPoleDescription(p?.description ?? ''); setEditPoleColor(p?.color ?? '#B57460')
  }

  const selected = members.find(u => u.id === selectedMember) ?? null
  const allPoles = projects.flatMap(project => project.poles.map(p => ({ ...p, project: project.name })))
  const possiblePoles = selected?.role === 'superadmin' ? allPoles : allPoles.filter(p => access.includes(p.project_id))
  const orderedPoles = poles.map(id => possiblePoles.find(p => p.id === id)).filter((p): p is typeof possiblePoles[number] => Boolean(p))
  const editedProject = projects.find(p => p.id === editProjectId)
  const editedPole = allPoles.find(p => p.id === editPoleId)

  function movePole(index: number, offset: number) {
    const next = [...poles]; const to = index + offset
    if (to < 0 || to >= next.length) return
    ;[next[index], next[to]] = [next[to], next[index]]
    setPoles(next)
  }

  async function invite(e: FormEvent) {
    e.preventDefault()
    await perform(async () => {
      await request('/api/admin/invitations', { email: inviteEmail, project_ids: inviteProjects })
      setInviteEmail(''); setInviteProjects([])
    })
  }

  return <main className="aw-layout">
    <div className="aw-heading">
      <button className="aw-back" onClick={back}><ArrowLeft size={17}/> Retour à mes projets</button>
      <div className="aw-title"><ShieldCheck size={24}/><div><h1>Administration</h1><p>Projets, membres et couleurs du BDE Alfiya</p></div></div>
    </div>
    <div className="aw-stats">
      <div><Users size={18}/><strong>{members.filter(m => m.role === 'member').length}</strong><span>Membres</span></div>
      <div><FolderKanban size={18}/><strong>{projects.length}</strong><span>Projets</span></div>
      <div><Mail size={18}/><strong>{members.filter(m => m.state === 'pending').length}</strong><span>Invitations en attente</span></div>
    </div>
    {notice && <div className="aw-notice" role="status">{notice}</div>}
    <div className="aw-tabs" role="tablist" aria-label="Navigation administration">
      <button role="tab" aria-selected={tab === 'members'} className={tab === 'members' ? 'selected' : ''} onClick={() => setTab('members')}>Membres et accès</button>
      <button role="tab" aria-selected={tab === 'projects'} className={tab === 'projects' ? 'selected' : ''} onClick={() => setTab('projects')}>Projets et pôles</button>
      <button role="tab" aria-selected={tab === 'trash'} className={tab === 'trash' ? 'selected' : ''} onClick={() => setTab('trash')}>Corbeille</button>
    </div>

    {tab === 'members' ? <div className="aw-columns">
      <div className="aw-stack">
        <section className="aw-panel"><h2>Inviter un membre</h2>
          <p>Invitation personnelle par e-mail. Aucun compte public ne peut s'inscrire.</p>
          <form onSubmit={e => void invite(e)}>
            <label>E-mail du membre<input type="email" required value={inviteEmail} onChange={e => setInviteEmail(e.target.value)} placeholder="membre@exemple.fr"/></label>
            <strong className="aw-label">Projets accessibles à son inscription</strong>
            {projects.map(p => <label className="aw-check" key={p.id}><input type="checkbox" checked={inviteProjects.includes(p.id)} onChange={e => setInviteProjects(old => e.target.checked ? [...old, p.id] : old.filter(id => id !== p.id))}/>{p.name}</label>)}
            <button className="aw-primary" disabled={busy || !inviteEmail || inviteProjects.length === 0}><Mail size={16}/> Envoyer l'invitation</button>
          </form>
        </section>
        <section className="aw-panel"><h2>Annuaire</h2>
          <div className="aw-member-list">{members.map(u => <button key={u.id} className={'aw-member ' + (selectedMember === u.id ? 'picked' : '')} onClick={() => chooseMember(u.id)}>
            <span className="aw-avatar" style={{ backgroundColor: u.poles[0]?.color ?? '#BAA79B' }}>{(u.first_name || u.email).charAt(0).toUpperCase()}</span>
            <span className="aw-member-name"><strong>{[u.first_name,u.last_name].filter(Boolean).join(' ') || u.email}</strong><small>{u.email}</small></span>
            <span className={'aw-state '+u.state}>{u.role === 'superadmin' ? 'Admin' : u.state === 'active' ? 'Actif' : u.state === 'pending' ? 'Invité' : 'Désactivé'}</span>
          </button>)}</div>
        </section>
      </div>
      <section className="aw-panel aw-member-editor">
        <h2>Fiche du membre</h2>
        {!selected ? <p>Sélectionne un membre dans l'annuaire pour gérer ses projets et ses pôles.</p> : selected.role === 'superadmin' ? <>
          <p>Ton compte a automatiquement accès à tous les projets. Tu peux choisir tes pôles et ta couleur d'identification ci-dessous.</p>
          <div className="aw-section"><h3>Mes pôles</h3>
            <p>Le premier pôle dans la liste détermine la couleur affichée avec ton nom.</p>
            {orderedPoles.length > 0 && <ol className="aw-pole-members">{orderedPoles.map((pole,index) => <li key={pole.id}>
              <span className="aw-color" style={{backgroundColor:pole.color}}/>
              <span><strong>{pole.name}</strong><small>{pole.project}{index === 0 ? ' · Couleur principale' : ''}</small></span>
              <button aria-label={'Monter '+pole.name} disabled={busy || index === 0} onClick={() => movePole(index,-1)}><ArrowUp size={15}/></button>
              <button aria-label={'Descendre '+pole.name} disabled={busy || index === orderedPoles.length-1} onClick={() => movePole(index,1)}><ArrowDown size={15}/></button>
              <button aria-label={'Retirer '+pole.name} disabled={busy} onClick={() => setPoles(old => old.filter(id => id !== pole.id))}><X size={16}/></button>
            </li>)}</ol>}
            <label>Ajouter un pôle<select value="" disabled={busy} onChange={e => {const id=Number(e.target.value);if(id && !poles.includes(id))setPoles(old=>[...old,id])}}>
              <option value="">Choisir un pôle…</option>{possiblePoles.filter(p=>!poles.includes(p.id)).map(p=><option key={p.id} value={p.id}>{p.project} — {p.name}</option>)}
            </select></label>
            <button className="aw-secondary" disabled={busy} onClick={() => void perform(() => request(`/api/admin/users/${selected.id}/poles`, {pole_ids:poles}))}><Save size={15}/> Enregistrer mes pôles</button>
          </div>
        </> : <>
          <h3>{[selected.first_name,selected.last_name].filter(Boolean).join(' ') || selected.email}</h3>
          <p>{selected.email} · {selected.state === 'pending' ? 'En attente d’activation' : selected.state === 'disabled' ? 'Compte désactivé' : 'Compte actif'}</p>
          <div className="aw-section">
            <h3>Projets autorisés</h3>
            <p>Un accès à un projet permet de consulter et modifier tous ses pôles.</p>
            {projects.map(project => <label className="aw-check" key={project.id}><input type="checkbox" checked={access.includes(project.id)} onChange={e => {
              const ids = e.target.checked ? [...access,project.id] : access.filter(id => id !== project.id)
              setAccess(ids); setPoles(old => old.filter(id => allPoles.some(p => p.id === id && ids.includes(p.project_id))))
            }}/>{project.name}</label>)}
            <button className="aw-secondary" disabled={busy} onClick={() => void perform(() => request(`/api/admin/users/${selected.id}/access`, {project_ids: access}))}><Save size={15}/> Enregistrer les accès</button>
          </div>
          <div className="aw-section">
            <h3>Pôles d'appartenance</h3>
            <p>La couleur du <strong>premier pôle</strong> reste celle du membre partout dans l'application. Déplace les pôles avec les flèches pour la modifier.</p>
            {orderedPoles.length ? <ol className="aw-pole-members">
              {orderedPoles.map((pole,index) => <li key={pole.id}>
                <span className="aw-color" style={{backgroundColor:pole.color}}/>
                <span><strong>{pole.name}</strong><small>{pole.project}{index === 0 ? ' · Couleur principale' : ''}</small></span>
                <button title="Monter" aria-label={'Monter '+pole.name} disabled={busy || index===0} onClick={() => movePole(index,-1)}><ArrowUp size={15}/></button>
                <button title="Descendre" aria-label={'Descendre '+pole.name} disabled={busy || index===orderedPoles.length-1} onClick={() => movePole(index,1)}><ArrowDown size={15}/></button>
                <button title="Retirer" aria-label={'Retirer '+pole.name} disabled={busy} onClick={() => setPoles(old => old.filter(id => id !== pole.id))}><X size={16}/></button>
              </li>)}
            </ol> : <p>Aucun pôle sélectionné.</p>}
            <label>Ajouter un pôle<select value="" disabled={busy} onChange={e => { const id=Number(e.target.value); if(id && !poles.includes(id)) setPoles(old => [...old,id]) }}>
              <option value="">Choisir un pôle…</option>
              {possiblePoles.filter(p => !poles.includes(p.id)).map(p => <option key={p.id} value={p.id}>{p.project} — {p.name}</option>)}
            </select></label>
            <button className="aw-secondary" disabled={busy || !selected.active} onClick={() => void perform(() => request(`/api/admin/users/${selected.id}/poles`, {pole_ids: poles}))}><Save size={15}/> Enregistrer l'ordre des pôles</button>
            {selected.state === 'pending' && <small>L'affectation des pôles sera disponible après l'activation du compte.</small>}
          </div>
          <div className="aw-section">
            <h3>Statut du compte</h3>
            {selected.active ? <button className="aw-danger" disabled={busy} onClick={() => {
              if (window.confirm(`Désactiver ${selected.email} et révoquer toutes ses sessions ?`))
                void perform(() => request(`/api/admin/users/${selected.id}/disable`, {}))
            }}>Désactiver et déconnecter le membre</button>
            : selected.state === 'disabled' && <button className="aw-secondary" disabled={busy} onClick={() => void perform(() => request(`/api/admin/users/${selected.id}/enable`, {}))}><Check size={15}/> Réactiver le compte</button>}
          </div>
        </>}
      </section>
    </div>  : tab === 'projects' ? <div className="aw-columns">
      <div className="aw-stack">
        <section className="aw-panel"><h2>Nouveau projet</h2><form onSubmit={e => {e.preventDefault();void perform(async () => {await request('/api/admin/projects',{name:newProject});setNewProject('')})}}>
          <label>Nom du projet<input value={newProject} onChange={e => setNewProject(e.target.value)} minLength={2} maxLength={120} required placeholder="Ex. Ramadan 2027"/></label>
          <button className="aw-primary" disabled={busy || newProject.trim().length < 2}><Plus size={16}/> Créer</button>
        </form></section>
        <section className="aw-panel"><h2>Nouveau pôle</h2><form onSubmit={e => {e.preventDefault();void perform(async()=>{await request(`/api/admin/projects/${newPoleProject}/poles`,{name:newPole,color:newPoleColor});setNewPole('')})}}>
          <label>Projet<select required value={newPoleProject} onChange={e => setNewPoleProject(e.target.value)}><option value="">Sélectionner un projet</option>{projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
          <label>Nom du pôle<input required minLength={2} maxLength={120} value={newPole} onChange={e => setNewPole(e.target.value)} placeholder="Ex. Communication"/></label>
          <label>Couleur<input type="color" value={newPoleColor} onChange={e => setNewPoleColor(e.target.value)}/></label>
          <button className="aw-primary" disabled={busy || !newPoleProject || newPole.trim().length < 2}><Plus size={16}/> Ajouter</button>
        </form></section>
      </div>
      <div className="aw-stack">
        <section className="aw-panel"><h2>Modifier un projet</h2>
          <label>Projet<select value={editProjectId ?? ''} onChange={e=>chooseProject(e.target.value ? Number(e.target.value):null)}><option value="">Choisir un projet</option>{projects.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
          {editedProject && <form onSubmit={e=>{e.preventDefault();void perform(()=>request(`/api/admin/projects/${editedProject.id}/edit`,{name:editProjectName,description:editProjectDescription}))}}>
            <label>Nom<input value={editProjectName} required minLength={2} maxLength={120} onChange={e=>setEditProjectName(e.target.value)}/></label>
            <label>Description<textarea maxLength={500} value={editProjectDescription} onChange={e=>setEditProjectDescription(e.target.value)}/></label>
            <button className="aw-secondary" disabled={busy}><Save size={15}/> Enregistrer</button>
            <button type="button" className="aw-danger" disabled={busy || editedProject.poles.length>0} onClick={()=>{ const name=window.prompt('Pour confirmer, recopiez le nom du projet :'); if(name===editedProject.name) void perform(async()=>{await request(`/api/admin/projects/${editedProject.id}/delete`,{name});chooseProject(null)}) }}><Trash2 size={15}/> Supprimer le projet vide</button>
            {editedProject.poles.length>0 && <small>Supprime d'abord les pôles pour pouvoir supprimer le projet.</small>}
          </form>}
        </section>
        <section className="aw-panel"><h2>Modifier un pôle</h2>
          <label>Pôle<select value={editPoleId ?? ''} onChange={e=>choosePole(e.target.value ? Number(e.target.value):null)}><option value="">Choisir un pôle</option>{allPoles.map(p=><option value={p.id} key={p.id}>{p.project} — {p.name}</option>)}</select></label>
          {editedPole && <form onSubmit={e=>{e.preventDefault();void perform(()=>request(`/api/admin/projects/${editedPole.project_id}/poles/${editedPole.id}/edit`,{name:editPoleName,color:editPoleColor,description:editPoleDescription}))}}>
            <label>Nom<input required minLength={2} maxLength={120} value={editPoleName} onChange={e=>setEditPoleName(e.target.value)}/></label>
            <label>Description<textarea maxLength={500} value={editPoleDescription} onChange={e=>setEditPoleDescription(e.target.value)}/></label>
            <label>Couleur<input type="color" value={editPoleColor} onChange={e=>setEditPoleColor(e.target.value)}/></label>
            <button className="aw-secondary" disabled={busy}><Save size={15}/> Enregistrer les modifications</button>
            <button type="button" className="aw-danger" disabled={busy} onClick={()=>{const name=window.prompt('Pour confirmer, recopiez le nom du pôle :');if(name===editedPole.name) void perform(async()=>{await request(`/api/admin/projects/${editedPole.project_id}/poles/${editedPole.id}/delete`,{name});choosePole(null)})}}><Trash2 size={15}/> Supprimer ce pôle</button>
            <small>Cette opération supprime les affectations des membres à ce pôle, mais conserve leurs accès au projet. Elle sera bloquée si des données liées empêchent la suppression.</small>
          </form>}
        </section>
      </div>
    </div> : <AdminTrash/>}
  </main>
}
