import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import {
  DndContext, DragOverlay, PointerSensor, TouchSensor, KeyboardSensor,
  closestCorners, useDroppable, useSensor, useSensors,
  type DragEndEvent, type DragStartEvent
} from '@dnd-kit/core'
import { SortableContext, useSortable, sortableKeyboardCoordinates, verticalListSortingStrategy } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { CalendarDays, Check, ChevronDown, GripVertical, Plus, Search, Trash2, Users, X } from 'lucide-react'
import './kanban.css'
import { CardTemplateContent, listTemplates, type Template as LibraryTemplate } from './TemplatesV5'
import CollaborationV6 from './CollaborationV6'
import { FollowCardV7, CardRemindersV7 } from './NotificationsV7'

type Status = 'todo' | 'progress' | 'done'
type Template = 'free' | 'speaker' | 'no_speaker'
type Member = { id: number; first_name: string; last_name: string; color: string | null }
type Card = {
  id: number; title: string; description: string; status: Status; position: number;
  start_date: string | null; due_date: string | null; template_key: Template; template_id: number | null; cover_attachment_id: number | null;
  created_by: number; author_first_name?: string; author_last_name?: string;
  assignees: Member[];
}
type Filter = { q: string; dateField: 'start_date' | 'due_date'; from: string; to: string; sort: 'manual' | 'az' | 'start' | 'due' }
type Viewer = { id: number; role: string; first_name: string; email: string }
type Props = { poleId: string; projectId: string; viewer: Viewer }
const statuses: { id: Status; name: string; color: string }[] = [
  { id: 'todo', name: 'À faire', color: '#ca985a' },
  { id: 'progress', name: 'En cours', color: '#699ab7' },
  { id: 'done', name: 'Terminé', color: '#76a087' },
]
const emptyFilter = (): Filter => ({ q: '', dateField: 'due_date', from: '', to: '', sort: 'manual' })
const formatDate = (value: string | null) => value ? new Date(value + 'T12:00:00').toLocaleDateString('fr-FR') : ''
const fullName = (m: Member) => (m.first_name + ' ' + m.last_name).trim() || 'Membre'
async function api<T>(path: string, method: 'GET' | 'POST' | 'PATCH' | 'PUT' = 'GET', body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method, credentials: 'same-origin',
    headers: method === 'GET' ? undefined : { 'Content-Type': 'application/json', 'X-Orga-Request': '1' },
    body: body === undefined ? undefined : JSON.stringify(body)
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Opération impossible')
  return data as T
}

function CardFace({ card, onClick, dragging = false }: { card: Card; onClick?: () => void; dragging?: boolean }) {
  return <div className={'kb-card-face' + (dragging ? ' kb-floating' : '')}>
    {card.cover_attachment_id && <img className="co-cover-mini" loading="lazy" src={'/api/cards/' + card.id + '/attachments/' + card.cover_attachment_id} alt="" />}
    {onClick ? <button type="button" className="kb-card-main" onClick={onClick}>
      <strong>{card.title}</strong>
      <span className="kb-card-meta">
        {card.due_date && <span><CalendarDays size={13}/> {formatDate(card.due_date)}</span>}
        <span>{card.template_key !== 'free' ? 'Modèle événement' : 'Carte libre'}</span>
      </span>
    </button> : <div className="kb-card-main"><strong>{card.title}</strong></div>}
    {!!card.assignees.length && <div className="kb-people" aria-label="Responsables">{card.assignees.slice(0,4).map(m =>
      <span key={m.id} className="kb-person" title={fullName(m)} style={{ borderColor: m.color || '#c4b2a5' }}>{m.first_name.slice(0,1).toUpperCase()}{m.last_name.slice(0,1).toUpperCase()}</span>
    )}{card.assignees.length > 4 && <small>+{card.assignees.length - 4}</small>}</div>}
  </div>
}

function SortableCard({ card, onOpen }: { card: Card; onOpen: (card: Card) => void }) {
  const { setNodeRef, attributes, listeners, transform, transition, isDragging } = useSortable({ id: 'card-' + card.id })
  return <div ref={setNodeRef} className={'kb-sortable' + (isDragging ? ' kb-ghost' : '')} style={{ transform: CSS.Transform.toString(transform), transition }}
    {...attributes} {...listeners} title="Glisser la carte pour la déplacer (appui prolongé sur mobile)">
    <div className="kb-grab" aria-hidden="true"><GripVertical size={18}/></div>
    <CardFace card={card} onClick={() => onOpen(card)} />
  </div>
}

function Column({ status, cards, filters, changeFilter, onOpen, onAdd } : {
  status: typeof statuses[number]; cards: Card[]; filters: Filter;
  changeFilter: (key: keyof Filter, value: string) => void;
  onOpen: (card: Card) => void; onAdd: () => void
}) {
  const { setNodeRef, isOver } = useDroppable({ id: 'col-' + status.id })
  return <section ref={setNodeRef} className={'kb-column' + (isOver ? ' kb-over' : '')} aria-label={status.name}>
    <div className="kb-column-head"><span className="kb-status-dot" style={{ background: status.color }}/><strong>{status.name}</strong><span className="kb-count">{cards.length}</span></div>
    <div className="kb-filter-row"><Search size={14}/><input type="search" aria-label={'Filtrer ' + status.name + ' par titre'} placeholder="Filtrer par titre" value={filters.q} onChange={e => changeFilter('q', e.target.value)}/></div>
    <details className="kb-filters">
      <summary>Dates et tri <ChevronDown size={13}/></summary>
      <label>Type de date<select value={filters.dateField} onChange={e => changeFilter('dateField', e.target.value)}><option value="start_date">Début</option><option value="due_date">Échéance</option></select></label>
      <div className="kb-date-range">
        <label>Du<input aria-label="Date à partir de" type="date" value={filters.from} onChange={e => changeFilter('from', e.target.value)}/></label>
        <label>Au<input aria-label="Date jusqu'à" type="date" value={filters.to} onChange={e => changeFilter('to', e.target.value)}/></label>
      </div>
      <label>Ordre<select value={filters.sort} onChange={e => changeFilter('sort', e.target.value)}>
        <option value="manual">Ordre manuel</option><option value="az">Titre A–Z</option><option value="start">Date de début</option><option value="due">Échéance</option>
      </select></label>
    </details>
    <SortableContext id={'items-' + status.id} items={cards.map(c => 'card-' + c.id)} strategy={verticalListSortingStrategy}>
      <div className="kb-column-items">{cards.map(card => <SortableCard key={card.id} card={card} onOpen={onOpen}/>)}
        {!cards.length && <p className="kb-empty">Aucune carte visible</p>}
      </div>
    </SortableContext>
    <button className="kb-add" type="button" onClick={onAdd}><Plus size={16}/> Ajouter une carte</button>
  </section>
}

export default function KanbanBoard({ poleId, projectId, viewer }: Props) {
  const [cards, setCards] = useState<Card[]>([])
  const [members, setMembers] = useState<Member[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [opened, setOpened] = useState<Card | null>(null)
  const [draft, setDraft] = useState({ title: '', description: '', start_date: '', due_date: '' })
  const [createFor, setCreateFor] = useState<Status | null>(null)
  const [newTitle, setNewTitle] = useState('')
  const [newTemplate, setNewTemplate] = useState<string>('free')
  const [templates, setTemplates] = useState<LibraryTemplate[]>([])
  const [busy, setBusy] = useState(false)
  const [dragId, setDragId] = useState<number | null>(null)
  const [filters, setFilters] = useState<Record<Status, Filter>>({ todo: emptyFilter(), progress: emptyFilter(), done: emptyFilter() })

  useEffect(() => { void listTemplates().then(setTemplates).catch(() => setError('Bibliothèque de modèles indisponible')) }, [])
  const load = useCallback(async () => {
    const result = await api<{ cards: Card[] }>('/api/poles/' + poleId + '/cards')
    setCards(result.cards)
    return result.cards
  }, [poleId])
  useEffect(() => {
    let active = true
    setLoading(true); setError(''); setOpened(null); setFilters({ todo: emptyFilter(), progress: emptyFilter(), done: emptyFilter() })
    Promise.all([api<{ cards: Card[] }>('/api/poles/' + poleId + '/cards'), api<{ members: Member[] }>('/api/projects/' + projectId + '/card-members')])
      .then(([result, people]) => { if (active) {
          setCards(result.cards);setMembers(people.members)
          const query=new URLSearchParams(window.location.search)
          if(query.get('pole')===poleId && query.has('card')){
            const card=result.cards.find(c=>c.id===Number(query.get('card')))
            if(card){
              setOpened(card)
              setDraft({title:card.title,description:card.description||'',
                start_date:card.start_date||'',due_date:card.due_date||''})
            }
            window.history.replaceState({},'',window.location.pathname)
          }
        } })
      .catch(e => { if (active) setError(e instanceof Error ? e.message : 'Erreur de chargement') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [poleId, projectId])

  const visible = useMemo(() => {
    const out: Record<Status, Card[]> = { todo: [], progress: [], done: [] }
    for (const s of statuses) {
      const f = filters[s.id]
      const items = cards.filter(c => {
        if (c.status !== s.id || !c.title.toLocaleLowerCase('fr').includes(f.q.toLocaleLowerCase('fr'))) return false
        const d = c[f.dateField]
        return (!f.from || (!!d && d >= f.from)) && (!f.to || (!!d && d <= f.to))
      })
      items.sort((a,b) => f.sort === 'az' ? a.title.localeCompare(b.title,'fr') :
        f.sort === 'start' ? (a.start_date || '9999').localeCompare(b.start_date || '9999') :
        f.sort === 'due' ? (a.due_date || '9999').localeCompare(b.due_date || '9999') :
        a.position - b.position || a.id - b.id)
      out[s.id] = items
    }
    return out
  }, [cards, filters])

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 300, tolerance: 8 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  )
  function startDrag(event: DragStartEvent) {
    const card = cards.find(c => 'card-' + c.id === String(event.active.id))
    setDragId(card?.id ?? null)
  }
  async function endDrag(event: DragEndEvent) {
    setDragId(null)
    if (!event.over) return
    const source = cards.find(c => 'card-' + c.id === String(event.active.id))
    if (!source) return
    const overId = String(event.over.id)
    const target = cards.find(c => 'card-' + c.id === overId)
    const targetStatus = target?.status || statuses.find(s => 'col-' + s.id === overId)?.id
    if (!targetStatus || (target?.id === source.id)) return
    const beforeId = target?.id ?? null
    const original = cards
    setCards(old => {
      const rest = old.filter(c => c.id !== source.id)
      const moving = { ...source, status: targetStatus }
      if (beforeId) {
        const index = rest.findIndex(c => c.id === beforeId)
        rest.splice(index < 0 ? rest.length : index, 0, moving)
      } else rest.push(moving)
      return rest.map((c,i) => ({ ...c, position: i }))
    })
    try { await api('/api/cards/' + source.id + '/move', 'POST', { status: targetStatus, before_id: beforeId }); await load() }
    catch (e) { setCards(original); setError(e instanceof Error ? e.message : 'Déplacement impossible') }
  }
  function editFilter(status: Status, key: keyof Filter, value: string) {
    setFilters(previous => ({ ...previous, [status]: { ...previous[status], [key]: value } }))
  }
  function openCard(c: Card) {
    setOpened(c)
    setDraft({ title: c.title, description: c.description || '', start_date: c.start_date || '', due_date: c.due_date || '' })
  }
  async function createCard(e: FormEvent) {
    e.preventDefault()
    if (!createFor || !newTitle.trim()) return
    setBusy(true); setError('')
    try {
      const selected = templates.find(t => String(t.id) === newTemplate)
      await api('/api/poles/' + poleId + '/cards','POST',{
        title: newTitle.trim(),status:createFor,
        template_key: selected?.slug === 'speaker' || selected?.slug === 'no_speaker' ? selected.slug : 'free',
        template_id: selected?.id ?? null
      })
      await load(); setCreateFor(null); setNewTitle(''); setNewTemplate('free')
    } catch (e) { setError(e instanceof Error ? e.message : 'Création impossible') }
    finally { setBusy(false) }
  }
  async function saveCard(e: FormEvent) {
    e.preventDefault()
    if (!opened) return
    setBusy(true); setError('')
    try {
      await api('/api/cards/' + opened.id, 'PATCH', {
        title: draft.title.trim(), description: draft.description,
        start_date: draft.start_date || null, due_date: draft.due_date || null
      })
      await load(); setOpened(previous => previous ? {...previous,...draft,start_date:draft.start_date || null,due_date:draft.due_date || null} : null)
    } catch (e) { setError(e instanceof Error ? e.message : 'Enregistrement impossible') }
    finally { setBusy(false) }
  }
  async function assign(userId: number, checked: boolean) {
    if (!opened) return
    const current = opened.assignees.map(m => m.id)
    const ids = checked ? [...current, userId] : current.filter(id => id !== userId)
    setBusy(true); setError('')
    try {
      const next = await api<Card>('/api/cards/' + opened.id + '/assignees', 'PUT', { user_ids: ids })
      setOpened(c => c ? { ...c, assignees: next.assignees } : null)
      await load()
    } catch (e) { setError(e instanceof Error ? e.message : 'Attribution impossible') }
    finally { setBusy(false) }
  }
  async function trash() {
    if (!opened || !window.confirm('Placer cette carte dans la corbeille ?')) return
    setBusy(true); setError('')
    try { await api('/api/cards/' + opened.id + '/trash','POST',{}); setOpened(null); await load() }
    catch (e) { setError(e instanceof Error ? e.message : 'Suppression impossible') }
    finally { setBusy(false) }
  }
  const active = cards.find(c => c.id === dragId)
  return <div className="kb-root">
    {error && <p className="kb-error" role="alert">{error} <button onClick={() => setError('')} aria-label="Masquer">×</button></p>}
    {loading ? <p className="kb-loading">Chargement des cartes…</p> :
      <DndContext sensors={sensors} collisionDetection={closestCorners} onDragStart={startDrag} onDragEnd={endDrag} onDragCancel={() => setDragId(null)}>
        <div className="kb-grid">{statuses.map(s =>
          <Column key={s.id} status={s} cards={visible[s.id]} filters={filters[s.id]}
            changeFilter={(key,value) => editFilter(s.id,key,value)} onOpen={openCard} onAdd={() => { setCreateFor(s.id); setNewTitle(''); setNewTemplate('free') }}/>)}</div>
        <DragOverlay>{active ? <div className="kb-drag-overlay"><CardFace card={active} dragging /></div> : null}</DragOverlay>
      </DndContext>}
    <p className="kb-hint">Déplacez les cartes avec la poignée <GripVertical size={14}/> (appui prolongé sur téléphone). Les filtres masquent uniquement l'affichage.</p>
    {createFor && <div className="overlay" role="presentation" onClick={() => setCreateFor(null)}>
      <section className="detail-modal kb-modal" role="dialog" aria-modal="true" aria-label="Nouvelle carte" onClick={e => e.stopPropagation()}>
        <div className="modal-top"><strong>Créer une carte</strong><button className="icon-button" onClick={() => setCreateFor(null)} aria-label="Fermer"><X size={19}/></button></div>
        <form onSubmit={createCard} className="kb-form">
          <label>Type de carte<select value={newTemplate} onChange={e => setNewTemplate(e.target.value)}>
            <option value="free">Saisie libre</option>{templates.map(t => <option key={t.id} value={String(t.id)}>{t.name}{t.official ? ' — officiel' : ''}</option>)}
          </select></label>
          <label>Titre (obligatoire)<input required maxLength={180} autoFocus placeholder="Ex. Conférence du vendredi" value={newTitle} onChange={e => setNewTitle(e.target.value)}/></label>
          <p>Tous les autres champs pourront être complétés après la création. Le modèle sera copié dans la carte, avec ses champs facultatifs et checklists.</p>
          <button className="primary-button" disabled={busy || !newTitle.trim()}><Plus size={15}/> Créer la carte</button>
        </form>
      </section></div>}
    {opened && <div className="overlay" role="presentation" onClick={() => setOpened(null)}>
      <section className="detail-modal kb-modal kb-detail" role="dialog" aria-modal="true" aria-label={opened.title} onClick={e => e.stopPropagation()}>
        <div className="modal-top"><span className="kb-tag">{opened.template_id ? (templates.find(t => t.id === opened.template_id)?.name || 'Carte avec modèle') : 'Carte libre'}</span><button className="icon-button" onClick={() => setOpened(null)} aria-label="Fermer"><X size={20}/></button></div>
        <form className="kb-form" onSubmit={saveCard}>
          <label>Titre<input required maxLength={180} value={draft.title} onChange={e => setDraft(d => ({ ...d, title: e.target.value }))}/></label>
          <label>Description<textarea rows={5} maxLength={20000} placeholder="À compléter au fur et à mesure…" value={draft.description} onChange={e => setDraft(d => ({ ...d, description: e.target.value }))}/></label>
          <div className="kb-date-range"><label>Début<input type="date" value={draft.start_date} onChange={e => setDraft(d => ({ ...d, start_date: e.target.value }))}/></label>
            <label>Échéance<input type="date" value={draft.due_date} onChange={e => setDraft(d => ({ ...d, due_date: e.target.value }))}/></label></div>
          <button className="primary-button" disabled={busy || !draft.title.trim()}><Check size={16}/> Enregistrer</button>
        </form>
        <CardTemplateContent cardId={opened.id}/>
        <FollowCardV7 cardId={opened.id}/>
        <CardRemindersV7 cardId={opened.id}/>
        <CollaborationV6 cardId={opened.id} projectId={Number(projectId)} viewer={viewer} onChanged={async () => { const latest=await load(); setOpened(previous => previous ? latest.find(c=>c.id===previous.id) ?? previous : null) }}/>
        <div className="kb-assign"><h3><Users size={17}/> Responsables</h3><div className="kb-member-list">{members.map(m =>
          <label key={m.id}><input type="checkbox" disabled={busy} checked={opened.assignees.some(a => a.id === m.id)} onChange={e => void assign(m.id,e.target.checked)}/><span className="kb-person-tag" style={{ borderColor: m.color || '#c4b2a5' }}>{fullName(m)}</span></label>)}
          {!members.length && <p>Aucun membre disponible.</p>}</div></div>
        <div className="kb-detail-foot"><span>Créée par {opened.author_first_name || 'un membre'} {opened.author_last_name || ''}</span>
          {(viewer.role === 'superadmin' || viewer.id === opened.created_by) && <button className="kb-trash" onClick={() => void trash()} disabled={busy}><Trash2 size={15}/> Mettre à la corbeille</button>}</div>
      </section></div>}
  </div>
}
