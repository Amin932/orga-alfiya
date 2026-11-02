import { useEffect, useState } from 'react'
import { ArrowRight, Bell, ChevronRight, FolderKanban, LayoutGrid, ShieldCheck, Users } from 'lucide-react'
import KanbanBoard from './KanbanBoard'

type Pole = { id: number; project_id: number; name: string; color: string; description: string }
type Project = { id: number; name: string; description: string; poles: Pole[] }
type Viewer = { id: number; role: string; first_name: string; email: string; primaryColor?: string }

export default function App({ viewer, onAdmin }: { viewer: Viewer; onAdmin?: () => void }) {
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [projectId, setProjectId] = useState<number | null>(null)
  const [poleId, setPoleId] = useState<number | null>(null)
  useEffect(() => {
    let active = true
    fetch('/api/workspace', { credentials: 'same-origin' })
      .then(async response => {
        if (!response.ok) throw new Error('Impossible de charger vos projets')
        return response.json() as Promise<{ projects: Project[] }>
      })
      .then(data => { if (active) setProjects(data.projects) })
      .catch(e => { if (active) setError(e instanceof Error ? e.message : 'Erreur de chargement') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])
  const project = projects.find(p => p.id === projectId) ?? null
  const pole = project?.poles.find(p => p.id === poleId) ?? null
  function home() { setProjectId(null); setPoleId(null) }
  function enterProject(id: number) { setProjectId(id); setPoleId(null) }

  return <div className="app-shell">
    <header className="topbar">
      <button className="brand" onClick={home} aria-label="Retour à l'accueil">
        <img src="/logo-bde.png" alt="Logo du BDE Alfiya"/>
        <span><strong>Orga Alfiya</strong><small>Bureau des étudiants</small></span>
      </button>
      <div className="topbar-actions">
        <span className="service online"><span className="status-dot"/> Espace membres</span>
        <button className="icon-button" disabled title="Notifications au bloc 7" aria-label="Notifications à venir"><Bell size={18}/></button>
        {onAdmin && <button className="icon-button" onClick={onAdmin} aria-label="Administration"><ShieldCheck size={19}/></button>}
        <span className="user-avatar" style={{ backgroundColor: viewer.primaryColor ?? undefined }} title={viewer.email}>{(viewer.first_name || viewer.email)[0].toUpperCase()}</span>
      </div>
    </header>
    <div className="main-layout">
      <aside className="sidebar" aria-label="Navigation">
        <div className="side-label">ESPACE DE TRAVAIL</div>
        <button className={'side-link' + (!project ? ' active' : '')} onClick={home}><LayoutGrid size={18}/> Mes projets</button>
        <div className="side-label side-label-projects">MES PROJETS</div>
        {projects.map(p => <button key={p.id} className={'side-link' + (p.id === projectId ? ' active' : '')} onClick={() => enterProject(p.id)}><FolderKanban size={18}/><span>{p.name}</span></button>)}
        <div className="sidebar-bottom"><ShieldCheck size={17}/> Projets autorisés uniquement</div>
      </aside>
      <main className="content">
        {error && <p role="alert" className="kb-error">{error}</p>}
        {loading ? <p>Chargement de vos projets…</p> : !project ? <>
          <div className="breadcrumbs">Accueil</div>
          <section className="page-title"><div><p className="eyebrow">BIENVENUE SUR ORGA ALFIYA</p><h1>Mes projets</h1><p>Organisez simplement les événements de votre BDE.</p></div><div className="title-decor"><img src="/logo-bde.png" alt=""/></div></section>
          <section className="section-heading"><div><h2>Espaces de travail</h2><p>Choisissez un projet pour retrouver ses pôles.</p></div><span className="count-chip">{projects.length} projets</span></section>
          <div className="project-grid">{projects.map((p,index) => <button key={p.id} className="project-card" onClick={() => enterProject(p.id)}>
            <div className={'project-illustration project-art-' + index}><FolderKanban size={33}/><span className="art-circle one"/><span className="art-circle two"/></div>
            <div className="project-card-content"><div className="project-row"><h3>{p.name}</h3><ChevronRight size={19}/></div><p>{p.description}</p><div className="project-meta"><Users size={15}/>{p.poles.length} pôles</div></div>
          </button>)}</div>
          {!projects.length && <p>Vous n'avez pas encore accès à un projet. Contactez le super-administrateur.</p>}
        </> : !pole ? <>
          <nav className="breadcrumbs"><button onClick={home}>Mes projets</button><ChevronRight size={14}/><span>{project.name}</span></nav>
          <section className="page-title compact"><div><p className="eyebrow">PROJET</p><h1>{project.name}</h1><p>{project.description}</p></div><span className="round-symbol"><FolderKanban size={28}/></span></section>
          <section className="section-heading"><div><h2>Choisir un pôle</h2><p>Ouvrez le tableau des missions et des événements.</p></div><span className="count-chip">{project.poles.length} pôles</span></section>
          <div className="pole-grid">{project.poles.map(p => <button key={p.id} className="pole-card" onClick={() => setPoleId(p.id)}>
            <span className="pole-band" style={{ backgroundColor: p.color }}/><div><span className="pole-icon" style={{ color:p.color,backgroundColor:p.color+'19' }}><Users size={22}/></span><h3>{p.name}</h3><p>{p.description}</p><span className="open-pole">Ouvrir le tableau <ArrowRight size={15}/></span></div>
          </button>)}</div>
          {!project.poles.length && <p>Les pôles seront ajoutés par le super-administrateur.</p>}
        </> : <>
          <nav className="breadcrumbs"><button onClick={home}>Mes projets</button><ChevronRight size={14}/><button onClick={() => enterProject(project.id)}>{project.name}</button><ChevronRight size={14}/><span>{pole.name}</span></nav>
          <section className="board-heading"><div><p className="eyebrow">TABLEAU DE PÔLE</p><div className="board-title"><span className="pole-dot-large" style={{ backgroundColor:pole.color }}/><h1>{pole.name}</h1></div><p>{pole.description}</p></div></section>
          <KanbanBoard key={pole.id} poleId={String(pole.id)} projectId={String(project.id)} viewer={viewer}/>
        </>}
      </main>
    </div>
  </div>
}
