import { useEffect, useState } from 'react'
import {
  ArrowRight, Bell, CalendarDays, Check, ChevronRight,
  Clock3, FileText, FolderKanban, LayoutGrid, LockKeyhole,
  MessageCircle, Plus, Search, Settings2, ShieldCheck, Users, X,
} from 'lucide-react'

type Pole = { id: string; name: string; color: string; description: string }
type Project = { id: string; name: string; description: string; poles: Pole[] }
type Status = 'todo' | 'progress' | 'done'
type DemoCard = { id: number; title: string; pole: string; status: Status; date?: string; initials: string; checklist: string }

const seedCards: DemoCard[] = []

const states: { id: Status; name: string; dot: string }[] = [
  { id: 'todo', name: 'À faire', dot: '#cf9a5a' },
  { id: 'progress', name: 'En cours', dot: '#6c98b4' },
  { id: 'done', name: 'Terminé', dot: '#729c81' },
]

function App({viewer}: {viewer: {first_name: string; email: string}}) {
  const [projects, setProjects] = useState<Project[]>([])
  useEffect(() => { fetch('/api/workspace', {credentials:'same-origin'}).then(r => r.ok ? r.json() : Promise.reject()).then(data => setProjects(data.projects.map((p: any) => ({...p,id:String(p.id),poles:p.poles.map((po: any)=>({...po,id:String(po.id)}))})))).catch(()=>setProjects([])) }, [])
  const [projectId, setProjectId] = useState<string | null>(null)
  const [poleId, setPoleId] = useState<string | null>(null)
  const [opened, setOpened] = useState<DemoCard | null>(null)
  const [search, setSearch] = useState('')
  const [apiStatus, setApiStatus] = useState<'loading' | 'online' | 'offline'>('loading')

  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/health', { signal: controller.signal })
      .then(response => setApiStatus(response.ok ? 'online' : 'offline'))
      .catch(() => { if (!controller.signal.aborted) setApiStatus('offline') })
    return () => controller.abort()
  }, [])

  const currentProject = projects.find(p => p.id === projectId) ?? null
  const currentPole = currentProject?.poles.find(p => p.id === poleId) ?? null
  const goHome = () => { setProjectId(null); setPoleId(null); setOpened(null); setSearch('') }
  const goProject = (id: string) => { setProjectId(id); setPoleId(null); setOpened(null); setSearch('') }
  const goPole = (id: string) => { setPoleId(id); setOpened(null); setSearch('') }

  return (
    <div className="app-shell">
      <header className="topbar">
        <button className="brand" onClick={goHome} aria-label="Retour à l'accueil">
          <img src="/logo-bde.png" alt="Logo du Bureau des étudiants de l’Institut Alfiya" />
          <span><strong>Orga Alfiya</strong><small>Bureau des étudiants</small></span>
        </button>
        <div className="topbar-actions">
          <span className={`service ${apiStatus}`} title="État de connexion à l'API"><span className="status-dot" />{apiStatus === 'online' ? 'API connectée' : apiStatus === 'offline' ? 'API indisponible' : 'Connexion…'}</span>
          <button className="icon-button" aria-label="Notifications (bloc suivant)" disabled><Bell size={19}/></button>
          <span className="user-avatar" title={viewer.email}>{(viewer.first_name || viewer.email)[0].toUpperCase()}</span>
        </div>
      </header>

      <div className="main-layout">
        <aside className="sidebar" aria-label="Navigation">
          <div className="side-label">ESPACE DE TRAVAIL</div>
          <button className={`side-link ${!currentProject ? 'active' : ''}`} onClick={goHome}><LayoutGrid size={18}/> Mes projets</button>
          <div className="side-label side-label-projects">MES PROJETS</div>
          {projects.map(project => (
            <button key={project.id} className={`side-link ${project.id === projectId ? 'active' : ''}`} onClick={() => goProject(project.id)}><FolderKanban size={18}/><span>{project.name}</span></button>
          ))}
          <div className="sidebar-bottom"><ShieldCheck size={17}/><span>Accès et comptes au bloc 2</span></div>
        </aside>

        <main className="content">
          <div className="demo-strip"><span className="demo-pill">TABLEAU EN PRÉPARATION</span> Les projets et pôles sont enregistrés. Le tableau Kanban sera activé au bloc 4.</div>
          {!currentProject && (
            <>
              <div className="breadcrumbs"><span>Accueil</span></div>
              <section className="page-title"><div><p className="eyebrow">BIENVENUE SUR ORGA ALFIYA</p><h1>Mes projets</h1><p>Retrouvez les espaces de travail de votre BDE, au même endroit.</p></div><div className="title-decor"><img src="/logo-bde.png" alt=""/></div></section>
              <section className="section-heading"><div><h2>Espaces de travail</h2><p>Choisissez un projet pour découvrir ses pôles.</p></div><span className="count-chip">{projects.length} projets</span></section>
              <div className="project-grid">
                {projects.map((p, index) => <button className="project-card" key={p.id} onClick={() => goProject(p.id)}>
                  <div className={`project-illustration project-art-${index}`}><FolderKanban size={30}/><span className="art-circle one"/><span className="art-circle two"/></div>
                  <div className="project-card-content"><div className="project-row"><h3>{p.name}</h3><ChevronRight size={19}/></div><p>{p.description}</p><div className="project-meta"><Users size={15}/>{p.poles.length} pôles</div></div>
                </button>)}
              </div>
            </>
          )}

          {currentProject && !currentPole && (
            <>
              <nav className="breadcrumbs"><button onClick={goHome}>Mes projets</button><ChevronRight size={14}/><span>{currentProject.name}</span></nav>
              <section className="page-title compact"><div><p className="eyebrow">PROJET</p><h1>{currentProject.name}</h1><p>{currentProject.description}</p></div><span className="round-symbol"><FolderKanban size={28}/></span></section>
              <section className="section-heading"><div><h2>Choisir un pôle</h2><p>Accédez au tableau des activités de chaque équipe.</p></div><span className="count-chip">{currentProject.poles.length} pôles</span></section>
              <div className="pole-grid">
                {currentProject.poles.map(p => <button className="pole-card" key={p.id} onClick={() => goPole(p.id)}><span className="pole-band" style={{ backgroundColor: p.color }}/><div><span className="pole-icon" style={{ color: p.color, backgroundColor: `${p.color}19` }}><Users size={22}/></span><h3>{p.name}</h3><p>{p.description}</p><span className="open-pole">Ouvrir le tableau <ArrowRight size={15}/></span></div></button>)}
              </div>
            </>
          )}

          {currentProject && currentPole && (
            <>
              <nav className="breadcrumbs"><button onClick={goHome}>Mes projets</button><ChevronRight size={14}/><button onClick={() => goProject(currentProject.id)}>{currentProject.name}</button><ChevronRight size={14}/><span>{currentPole.name}</span></nav>
              <section className="board-heading"><div><p className="eyebrow">TABLEAU DE PÔLE</p><div className="board-title"><span className="pole-dot-large" style={{ backgroundColor: currentPole.color }}/><h1>{currentPole.name}</h1></div><p>{currentPole.description}</p></div><button className="quiet-button" disabled title="Disponible dans les prochains blocs"><Settings2 size={17}/> Filtres avancés à venir</button></section>
              <div className="board-search"><Search size={18}/><input type="search" aria-label="Rechercher une carte" placeholder="Rechercher une carte par titre…" value={search} onChange={event => setSearch(event.target.value)} /></div>
              <div className="board-columns">
                {states.map(state => {
                  const cards = seedCards.filter(card => card.pole === currentPole.id && card.status === state.id && card.title.toLowerCase().includes(search.toLowerCase()))
                  return <section key={state.id} className="kanban-column"><div className="column-heading"><span className="column-dot" style={{backgroundColor: state.dot}}/><strong>{state.name}</strong><span className="column-count">{cards.length}</span></div>
                    <div className="column-cards">{cards.map(card => <button key={card.id} className="task-card" onClick={() => setOpened(card)}><span className="task-name">{card.title}</span><div className="task-meta"><span>{card.date && <><CalendarDays size={13}/>{card.date}</>}</span><span><span className="task-check"><Check size={12}/>{card.checklist}</span><span className="mini-avatar">{card.initials}</span></span></div></button>)}{cards.length === 0 && <div className="empty-column">Aucune carte</div>}</div>
                    <button className="add-card" disabled title="La création de carte arrive au bloc Kanban"><Plus size={17}/> Ajouter une carte</button>
                  </section>
                })}
              </div>
              <p className="board-note"><LockKeyhole size={15}/> Le glisser-déposer souris et tactile, les filtres complets et la sauvegarde arriveront avec le véritable tableau Kanban.</p>
            </>
          )}
        </main>
      </div>

      {opened && <div className="overlay" role="presentation" onClick={() => setOpened(null)}><section className="detail-modal" role="dialog" aria-modal="true" aria-label={opened.title} onClick={event => event.stopPropagation()}><div className="modal-top"><span className="demo-pill">APERÇU D'UNE CARTE</span><button className="icon-button" onClick={() => setOpened(null)} aria-label="Fermer"><X size={20}/></button></div><h2>{opened.title}</h2><p>Les champs seront modifiables au sein de la carte une fois les modèles et l'API métier implémentés.</p><div className="modal-info"><span><CalendarDays size={17}/> {opened.date ?? 'Date non définie'}</span><span><Check size={17}/> Checklist {opened.checklist}</span><span><MessageCircle size={17}/> Commentaires à venir</span><span><FileText size={17}/> Documents à venir</span><span><Clock3 size={17}/> Historique à venir</span></div><button className="primary-button" onClick={() => setOpened(null)}>Fermer l'aperçu</button></section></div>}
    </div>
  )
}

export default App
