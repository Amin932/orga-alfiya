import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { LogOut, ShieldCheck } from 'lucide-react'
import AdminWorkspace from './AdminWorkspace'
import App from './App'

type Pole = { id: number; project_id: number; name: string; color: string; description: string; project?: string }
type Project = { id: number; name: string; description: string; poles: Pole[] }
type User = { id: number; email: string; first_name: string; last_name: string; role: 'superadmin' | 'member' }
type Profile = { user: User; projects: Project[]; poles: Pole[] }

async function api<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, { credentials: 'same-origin', method: body === undefined ? 'GET' : 'POST',
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json', 'X-Orga-Request': '1' },
    body: body === undefined ? undefined : JSON.stringify(body) })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Opération impossible')
  return data as T
}

function Activate({ token, onComplete }: { token: string; onComplete: () => void }) {
  const [info, setInfo] = useState<{ email: string; poles: Pole[] } | null>(null)
  const [first, setFirst] = useState(''); const [last, setLast] = useState(''); const [pole, setPole] = useState('')
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false)
  useEffect(() => { api<{ email: string; poles: Pole[] }>('/api/auth/invitation', { token }).then(setInfo).catch(e => setError(e.message)) }, [token])
  async function activate(e: FormEvent) { e.preventDefault(); setBusy(true); setError('')
    try { await api('/api/auth/activate', { token, first_name: first, last_name: last, pole_id: pole ? Number(pole) : null }); window.history.replaceState({}, '', '/'); onComplete() }
    catch (e) { setError(e instanceof Error ? e.message : 'Erreur') } finally { setBusy(false) }
  }
  return <main className="auth-background"><div className="auth-box"><img src="/logo-bde.png" alt="Logo du BDE Alfiya"/><h1>Bienvenue à Orga Alfiya</h1><p>Activez votre compte personnel.</p>
    {error && <p className="auth-error" role="alert">{error}</p>}{info ? <form onSubmit={activate}>
      <label>E-mail<input value={info.email} disabled/></label><label>Prénom<input required maxLength={80} value={first} onChange={e => setFirst(e.target.value)}/></label>
      <label>Nom<input required maxLength={80} value={last} onChange={e => setLast(e.target.value)}/></label>
      {info.poles.length > 0 ? <label>Premier pôle (détermine votre couleur)<select required value={pole} onChange={e => setPole(e.target.value)}><option value="">Choisir un pôle</option>{info.poles.map(p => <option value={p.id} key={p.id}>{p.project} — {p.name}</option>)}</select></label> : <p className="auth-hint">Aucun pôle n'a encore été configuré sur vos projets. L'administrateur pourra vous en attribuer un.</p>}
      <button disabled={busy || (info.poles.length > 0 && !pole)}>Activer mon compte</button></form> : !error && <p>Vérification de votre invitation…</p>}
  </div></main>
}

function SignIn({ loginToken, onComplete }: { loginToken: string | null; onComplete: () => void }) {
  const [email, setEmail] = useState(''); const [message, setMessage] = useState(''); const [busy, setBusy] = useState(false)
  useEffect(() => { if (!loginToken) return; api('/api/auth/login', { token: loginToken }).then(() => { window.history.replaceState({}, '', '/'); onComplete() }).catch(e => setMessage(e.message)) }, [loginToken, onComplete])
  async function request(e: FormEvent) { e.preventDefault(); setBusy(true); try { const r = await api<{ message: string }>('/api/auth/request-link', { email }); setMessage(r.message) } catch (e) { setMessage(e instanceof Error ? e.message : 'Erreur') } finally { setBusy(false) } }
  return <main className="auth-background"><div className="auth-box"><img src="/logo-bde.png" alt="Logo du BDE Alfiya"/><h1>Orga Alfiya</h1><p>Connectez-vous à votre espace du BDE.</p>
    {loginToken ? <p role="status">Connexion en cours… {message}</p> : <form onSubmit={request}><label>Adresse e-mail<input type="email" autoComplete="email" required placeholder="votre@email.fr" value={email} onChange={e => setEmail(e.target.value)}/></label><button disabled={busy}>Recevoir mon lien de connexion</button>{message && <p className="auth-message" role="status">{message}</p>}</form>}
    <small>Seuls les membres invités peuvent accéder à Orga Alfiya. Votre session reste active sur cet appareil.</small>
  </div></main>
}

export default function AuthGate() {
  const [profile, setProfile] = useState<Profile | null>(null)
  const [loading, setLoading] = useState(true)
  const [adminOpen, setAdminOpen] = useState(false)
  const [revision, setRevision] = useState(0)
  const refresh = useCallback(() => { setRevision(n => n + 1) }, [])
  const hash = window.location.hash
  const inviteToken = hash.startsWith('#invite=') ? hash.substring(8) : null
  const loginToken = hash.startsWith('#login=') ? hash.substring(7) : null
  useEffect(() => { api<Profile>('/api/auth/me').then(setProfile).catch(() => setProfile(null)).finally(() => setLoading(false)) }, [revision])
  async function signOut() { await api('/api/auth/logout', {}); setAdminOpen(false); setProfile(null) }
  if (loading) return <main className="auth-background"><p>Chargement d'Orga Alfiya…</p></main>
  if (inviteToken) return <Activate token={inviteToken} onComplete={refresh}/>
  if (!profile) return <SignIn loginToken={loginToken} onComplete={refresh}/>
  return <>{adminOpen && profile.user.role === 'superadmin' ? <AdminWorkspace back={() => { setAdminOpen(false); refresh() }}/> : <App viewer={{ ...profile.user, primaryColor: profile.poles[0]?.color }} onAdmin={() => setAdminOpen(true)}/>}<div className="auth-session-actions"><span>{profile.user.first_name || profile.user.email}</span>{profile.user.role === 'superadmin' && !adminOpen && <button onClick={() => setAdminOpen(true)}><ShieldCheck size={16}/> Administration</button>}<button onClick={() => void signOut()}><LogOut size={16}/> Déconnexion</button></div></>
}
