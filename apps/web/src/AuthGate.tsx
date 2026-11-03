import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { KeyRound, LogOut, ShieldCheck } from 'lucide-react'
import AdminWorkspace from './AdminWorkspace'
import App from './App'

type Pole = { id: number; project_id: number; name: string; color: string; description: string; project?: string }
type Project = { id: number; name: string; description: string; poles: Pole[] }
type User = { id: number; email: string; first_name: string; last_name: string; role: 'superadmin' | 'member' }
type Profile = { user: User; projects: Project[]; poles: Pole[] }
async function api<T>(path:string,body?:unknown):Promise<T> {
  const res=await fetch(path,{credentials:'same-origin',method:body===undefined?'GET':'POST',
    headers:body===undefined?undefined:{'Content-Type':'application/json','X-Orga-Request':'1'},
    body:body===undefined?undefined:JSON.stringify(body)})
  const data=await res.json().catch(()=>({}))
  if(!res.ok)throw new Error(typeof data.detail==='string'?data.detail:'Opération impossible')
  return data as T
}

function PasswordPair({password,setPassword,confirm,setConfirm}:{password:string;setPassword:(s:string)=>void;confirm:string;setConfirm:(s:string)=>void}){
  return <>
    <label>Choisir un mot de passe (12 caractères minimum)
      <input type="password" autoComplete="new-password" minLength={12} maxLength={128}
        required value={password} onChange={e=>setPassword(e.target.value)}/>
    </label>
    <label>Confirmer le mot de passe
      <input type="password" autoComplete="new-password" minLength={12} maxLength={128}
        required value={confirm} onChange={e=>setConfirm(e.target.value)}/>
    </label>
  </>
}

function Activate({token,onComplete}:{token:string;onComplete:()=>void}){
  const [info,setInfo]=useState<{email:string;poles:Pole[]}|null>(null)
  const [first,setFirst]=useState(''),[last,setLast]=useState(''),[pole,setPole]=useState('')
  const [password,setPassword]=useState(''),[confirm,setConfirm]=useState('')
  const [error,setError]=useState(''),[busy,setBusy]=useState(false)
  useEffect(()=>{void api<{email:string;poles:Pole[]}>('/api/auth/invitation',{token})
    .then(setInfo).catch(e=>setError(e instanceof Error?e.message:'Lien invalide'))},[token])
  async function activate(e:FormEvent){
    e.preventDefault()
    if(password!==confirm){setError('Les mots de passe sont différents.');return}
    setBusy(true);setError('')
    try{
      await api('/api/auth/activate',{token,first_name:first,last_name:last,
        pole_id:pole?Number(pole):null,password})
      window.history.replaceState({},'','/');onComplete()
    }catch(e){setError(e instanceof Error?e.message:'Activation impossible')}
    finally{setBusy(false)}
  }
  return <main className="auth-background"><div className="auth-box">
    <img src="/logo-bde.png" alt="Logo du BDE Alfiya"/>
    <h1>Bienvenue à Orga Alfiya</h1><p>Activez votre compte grâce à votre invitation personnelle.</p>
    {error&&<p className="auth-error" role="alert">{error}</p>}
    {info?<form onSubmit={activate}>
      <label>Identifiant<input value={info.email} disabled/></label>
      <label>Prénom<input required maxLength={80} value={first} onChange={e=>setFirst(e.target.value)}/></label>
      <label>Nom<input required maxLength={80} value={last} onChange={e=>setLast(e.target.value)}/></label>
      {info.poles.length>0?<label>Premier pôle (détermine votre couleur)
        <select required value={pole} onChange={e=>setPole(e.target.value)}><option value="">Choisir un pôle</option>
          {info.poles.map(p=><option key={p.id} value={p.id}>{p.project} — {p.name}</option>)}
        </select></label>:<p className="auth-hint">Aucun pôle encore configuré sur vos projets.</p>}
      <PasswordPair password={password} setPassword={setPassword} confirm={confirm} setConfirm={setConfirm}/>
      <button disabled={busy||(info.poles.length>0&&!pole)||password.length<12||password!==confirm}>Activer mon compte</button>
      <small>Cette invitation est personnelle, à usage unique et valable 7 jours.</small>
    </form>:!error&&<p>Vérification de l'invitation…</p>}
  </div></main>
}

function Reset({token,onComplete}:{token:string;onComplete:()=>void}){
  const [password,setPassword]=useState(''),[confirm,setConfirm]=useState('')
  const [busy,setBusy]=useState(false),[error,setError]=useState('')
  async function submit(e:FormEvent){
    e.preventDefault()
    if(password!==confirm){setError('Les mots de passe sont différents.');return}
    setBusy(true);setError('')
    try{await api('/api/auth/reset-password',{token,password});window.history.replaceState({},'','/');onComplete()}
    catch(e){setError(e instanceof Error?e.message:'Lien de réinitialisation invalide')}
    finally{setBusy(false)}
  }
  return <main className="auth-background"><div className="auth-box">
    <img src="/logo-bde.png" alt="Logo du BDE Alfiya"/>
    <h1>Réinitialiser mon mot de passe</h1>
    <p>Ce lien personnel a été fourni par le super-administrateur et est valable 30 minutes.</p>
    {error&&<p className="auth-error" role="alert">{error}</p>}
    <form onSubmit={submit}><PasswordPair password={password} setPassword={setPassword} confirm={confirm} setConfirm={setConfirm}/>
      <button disabled={busy||password.length<12||password!==confirm}>Définir mon mot de passe</button>
    </form>
  </div></main>
}

function SignIn({onComplete}:{onComplete:()=>void}){
  const [email,setEmail]=useState(''),[password,setPassword]=useState('')
  const [error,setError]=useState(''),[busy,setBusy]=useState(false)
  async function login(e:FormEvent){
    e.preventDefault();setBusy(true);setError('')
    try{await api('/api/auth/login',{email,password});onComplete()}
    catch(e){setError(e instanceof Error?e.message:'Connexion impossible')}
    finally{setBusy(false)}
  }
  return <main className="auth-background"><div className="auth-box">
    <img src="/logo-bde.png" alt="Logo du BDE Alfiya"/>
    <h1>Orga Alfiya</h1><p>Connectez-vous à votre espace privé du BDE.</p>
    {error&&<p className="auth-error" role="alert">{error}</p>}
    <form onSubmit={login}>
      <label>Identifiant (adresse e-mail)
        <input type="email" autoComplete="username" required value={email}
          placeholder="votre@email.fr" onChange={e=>setEmail(e.target.value)}/></label>
      <label>Mot de passe
        <input type="password" autoComplete="current-password" required value={password}
          onChange={e=>setPassword(e.target.value)}/></label>
      <button disabled={busy}>Se connecter</button>
    </form>
    <small>Aucun e-mail automatique. Votre session reste ouverte sur cet appareil.
      Mot de passe oublié ? Demandez un lien privé à l'administrateur.</small>
  </div></main>
}

function ChangePassword({onClose}:{onClose:()=>void}){
  const [current,setCurrent]=useState(''),[next,setNext]=useState(''),[confirm,setConfirm]=useState('')
  const [message,setMessage]=useState(''),[busy,setBusy]=useState(false)
  async function submit(e:FormEvent){
    e.preventDefault()
    if(next!==confirm){setMessage('Les mots de passe sont différents.');return}
    setBusy(true);setMessage('')
    try{await api('/api/auth/change-password',{current_password:current,new_password:next});
      setMessage('Mot de passe modifié. Les autres sessions ont été révoquées.');setCurrent('');setNext('');setConfirm('')}
    catch(e){setMessage(e instanceof Error?e.message:'Modification impossible')}
    finally{setBusy(false)}
  }
  return <div className="overlay" onClick={onClose}>
    <section className="detail-modal" role="dialog" aria-label="Modifier mon mot de passe" aria-modal="true" onClick={e=>e.stopPropagation()}>
      <div className="modal-top"><strong>Modifier mon mot de passe</strong>
        <button className="icon-button" onClick={onClose} aria-label="Fermer">×</button></div>
      <form className="kb-form" onSubmit={submit}>
        <label>Mot de passe actuel<input type="password" required value={current} onChange={e=>setCurrent(e.target.value)}/></label>
        <label>Nouveau mot de passe<input type="password" minLength={12} maxLength={128} required value={next} onChange={e=>setNext(e.target.value)}/></label>
        <label>Confirmer<input type="password" minLength={12} maxLength={128} required value={confirm} onChange={e=>setConfirm(e.target.value)}/></label>
        <button className="primary-button" disabled={busy||next!==confirm}>Changer le mot de passe</button>
        {message&&<p role="status">{message}</p>}
      </form>
    </section>
  </div>
}

export default function AuthGate(){
  const [profile,setProfile]=useState<Profile|null>(null)
  const [loading,setLoading]=useState(true),[adminOpen,setAdminOpen]=useState(false)
  const [passwordOpen,setPasswordOpen]=useState(false),[revision,setRevision]=useState(0)
  const refresh=useCallback(()=>setRevision(n=>n+1),[])
  const hash=window.location.hash
  const inviteToken=hash.startsWith('#invite=')?hash.substring(8):null
  const resetToken=hash.startsWith('#reset=')?hash.substring(7):null
  useEffect(()=>{setLoading(true)
    void api<Profile>('/api/auth/me').then(setProfile).catch(()=>setProfile(null)).finally(()=>setLoading(false))
  },[revision])
  async function signOut(){
    try{
      if('serviceWorker' in navigator){
        const reg=await navigator.serviceWorker.getRegistration('/')
        const sub=await reg?.pushManager.getSubscription()
        if(sub){
          await fetch('/api/notifications/push-subscriptions',{method:'DELETE',credentials:'same-origin',
            headers:{'Content-Type':'application/json','X-Orga-Request':'1'},
            body:JSON.stringify({endpoint:sub.endpoint})})
          await sub.unsubscribe()
        }
      }
    }catch{/* la déconnexion reste disponible */}
    await api('/api/auth/logout',{})
    setAdminOpen(false);setPasswordOpen(false);setProfile(null)
  }
  if(loading)return <main className="auth-background"><p>Chargement d'Orga Alfiya…</p></main>
  if(inviteToken)return <Activate token={inviteToken} onComplete={refresh}/>
  if(resetToken)return <Reset token={resetToken} onComplete={refresh}/>
  if(!profile)return <SignIn onComplete={refresh}/>
  return <>
    {adminOpen&&profile.user.role==='superadmin'
      ? <AdminWorkspace back={()=>{setAdminOpen(false);refresh()}}/>
      : <App viewer={{...profile.user,primaryColor:profile.poles[0]?.color}} onAdmin={()=>setAdminOpen(true)}/>}
    <div className="auth-session-actions">
      <span>{profile.user.first_name||profile.user.email}</span>
      {profile.user.role==='superadmin'&&!adminOpen&&
        <button onClick={()=>setAdminOpen(true)}><ShieldCheck size={16}/> Administration</button>}
      <button onClick={()=>setPasswordOpen(true)}><KeyRound size={15}/> Mot de passe</button>
      <button onClick={()=>void signOut()}><LogOut size={16}/> Déconnexion</button>
    </div>
    {passwordOpen&&<ChangePassword onClose={()=>setPasswordOpen(false)}/>}
  </>
}
