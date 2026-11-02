import { useCallback, useEffect, useState } from 'react'
import { RotateCcw, Trash2 } from 'lucide-react'

type DeletedCard = { id: number; title: string; deleted_at: string; pole_name: string; project_name: string }

async function request(path: string, method = 'GET') {
  const response = await fetch(path, { method, credentials: 'same-origin', headers: method === 'GET' ? undefined : { 'X-Orga-Request': '1' } })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Une erreur est survenue')
  return data
}

export default function AdminTrash() {
  const [items, setItems] = useState<DeletedCard[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const refresh = useCallback(() => { request('/api/admin/cards/trash').then(data => setItems(data.cards)).catch(e => setError(e.message)) }, [])
  useEffect(() => { refresh() }, [refresh])

  async function act(card: DeletedCard, action: 'restore' | 'delete') {
    if (action === 'delete' && !window.confirm('Supprimer définitivement « ' + card.title + ' » ? Cette opération est irréversible.')) return
    setError(''); setBusy(true)
    try {
      await request(action === 'restore' ? '/api/admin/cards/' + card.id + '/restore' : '/api/admin/cards/' + card.id,
        action === 'restore' ? 'POST' : 'DELETE')
      refresh()
    } catch (e) { setError(e instanceof Error ? e.message : 'Opération impossible') }
    finally { setBusy(false) }
  }

  return <section className="aw-panel">
    <h2>Corbeille des cartes</h2>
    <p>Seul le super-administrateur peut restaurer ou supprimer définitivement les cartes.</p>
    {error && <p className="auth-error" role="alert">{error}</p>}
    {!items.length && <p>Aucune carte dans la corbeille.</p>}
    {items.map(card => <div className="auth-user" key={card.id} style={{gap:14}}>
      <div style={{flex:1,minWidth:0}}>
        <strong>{card.title}</strong><small>{card.project_name} · {card.pole_name} · {new Date(card.deleted_at).toLocaleDateString('fr-FR')}</small>
      </div>
      <button className="aw-secondary" disabled={busy} onClick={() => void act(card,'restore')}><RotateCcw size={15}/> Restaurer</button>
      <button className="aw-danger" disabled={busy} onClick={() => void act(card,'delete')}><Trash2 size={15}/> Supprimer</button>
    </div>)}
  </section>
}
