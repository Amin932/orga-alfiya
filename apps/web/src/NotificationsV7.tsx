import { useEffect, useState } from 'react'
import { Bell, BellOff, CheckCheck, Settings2, Smartphone, X } from 'lucide-react'
import './notifications-v7.css'

type Notification = {
  id:number; event_type:string; title:string; message:string;
  card_id:number|null; project_id:number|null; pole_id:number|null;
  created_at:string; read_at:string|null
}
type Prefs = { push_enabled:boolean; events:Record<string,boolean> }
const eventLabels:Record<string,string> = {
  assignment:'Attributions de missions',handoff:'Nouvelles missions reçues par Communication',mention:'Mentions dans les commentaires',
  comment:'Commentaires des cartes suivies',completed:'Cartes terminées',
  reminder:'Rappels d’échéance (J-3, J-1, J0)',overdue:'Retards (J+1)',
  project_access:'Accès aux projets',critical:'Alertes importantes'
}
const api = async <T,>(path:string,method:'GET'|'POST'|'PUT'|'DELETE'='GET',body?:unknown):Promise<T> => {
  const r = await fetch(path,{method,credentials:'same-origin',
    headers:method==='GET'?undefined:{'Content-Type':'application/json','X-Orga-Request':'1'},
    body:body===undefined?undefined:JSON.stringify(body)})
  const data=await r.json().catch(()=>({}))
  if(!r.ok)throw new Error(typeof data.detail==='string'?data.detail:'Opération impossible')
  return data as T
}
function decodePublicKey(encoded:string):Uint8Array {
  const standard=encoded.replace(/-/g,'+').replace(/_/g,'/')
  const raw=atob(standard+'='.repeat((4-standard.length%4)%4))
  return Uint8Array.from(raw, c=>c.charCodeAt(0))
}
export default function NotificationsV7() {
  const [open,setOpen]=useState(false)
  const [settings,setSettings]=useState(false)
  const [items,setItems]=useState<Notification[]>([])
  const [unread,setUnread]=useState(0)
  const [prefs,setPrefs]=useState<Prefs|null>(null)
  const [pushKey,setPushKey]=useState<string|null>(null)
  const [busy,setBusy]=useState(false)
  const [message,setMessage]=useState('')
  const refresh=async()=>{
    const box=await api<{notifications:Notification[];unread:number}>('/api/notifications')
    setItems(box.notifications);setUnread(box.unread)
  }
  useEffect(()=>{
    let mounted=true
    const check=async()=>{
      try {
        const r=await api<{notifications:Notification[];unread:number}>('/api/notifications')
        if(mounted){setItems(r.notifications);setUnread(r.unread)}
      } catch {/* session may have expired */}
    }
    void check()
    const interval=window.setInterval(()=>void check(),30000)
    return ()=>{mounted=false;window.clearInterval(interval)}
  },[])
  async function openPanel(){
    setOpen(!open);setSettings(false);setMessage('')
    if(!open) await refresh().catch(()=>setMessage('Notifications indisponibles'))
  }
  async function openSettings(){
    setSettings(true);setMessage('')
    try {
      const [p,k] = await Promise.all([
        api<Prefs>('/api/notifications/preferences'),
        api<{key:string|null}>('/api/notifications/push-public-key')])
      setPrefs(p);setPushKey(k.key)
    } catch(e){setMessage(e instanceof Error?e.message:'Erreur')}
  }
  async function savePreferences(){
    if(!prefs)return
    setBusy(true);setMessage('')
    try{await api('/api/notifications/preferences','PUT',prefs);setMessage('Préférences sauvegardées.')}
    catch(e){setMessage(e instanceof Error?e.message:'Enregistrement impossible')}
    finally{setBusy(false)}
  }
  async function enablePush(){
    setBusy(true);setMessage('')
    try{
      if(!pushKey)throw new Error('La clé push doit être configurée sur le NAS.')
      if(!('serviceWorker' in navigator) || !('PushManager' in window))
        throw new Error('Notifications push non prises en charge par ce navigateur.')
      const permission=await Notification.requestPermission()
      if(permission!=='granted')throw new Error('Autorisation push refusée.')
      const registration=await navigator.serviceWorker.register('/sw.js')
      const ready=await navigator.serviceWorker.ready
      const current=await ready.pushManager.getSubscription()
      const bytes=decodePublicKey(pushKey)
      const keyBuffer=new ArrayBuffer(bytes.length)
      new Uint8Array(keyBuffer).set(bytes)
      const subscription=current || await ready.pushManager.subscribe({userVisibleOnly:true,
        applicationServerKey:keyBuffer})
      const serialized=subscription.toJSON()
      if(!serialized.endpoint || !serialized.keys?.p256dh || !serialized.keys.auth)
        throw new Error('Abonnement push incomplet.')
      await api('/api/notifications/push-subscriptions','POST',{
        endpoint:serialized.endpoint,p256dh:serialized.keys.p256dh,auth:serialized.keys.auth})
      if(prefs)setPrefs({...prefs,push_enabled:true})
      setMessage('Cet appareil est maintenant abonné aux notifications push.')
      void registration
    }catch(e){setMessage(e instanceof Error?e.message:'Activation impossible')}
    finally{setBusy(false)}
  }
  async function unsubscribe(){
    setBusy(true);setMessage('')
    try {
      await api('/api/notifications/push-subscriptions','DELETE',{})
      if('serviceWorker' in navigator){
        const ready=await navigator.serviceWorker.ready
        await (await ready.pushManager.getSubscription())?.unsubscribe()
      }
      setMessage('Abonnements push du compte supprimés.')
    }catch(e){setMessage(e instanceof Error?e.message:'Désactivation impossible')}
    finally{setBusy(false)}
  }
  async function markOne(n:Notification){
    try{await api('/api/notifications/'+n.id+'/read','POST',{})}catch{/* navigation allowed */}
    if(n.card_id&&n.project_id&&n.pole_id){
      window.location.assign('/?project='+n.project_id+'&pole='+n.pole_id+'&card='+n.card_id)
    }else{await refresh().catch(()=>undefined)}
  }
  async function markAll(){
    await api('/api/notifications/read-all','POST',{})
    await refresh()
  }
  return <div className="nt-shell">
    <button type="button" className="icon-button nt-trigger" onClick={()=>void openPanel()} aria-label={'Notifications, '+unread+' non lues'} aria-expanded={open}>
      <Bell size={19}/>{unread>0&&<span className="nt-count">{unread>99?'99+':unread}</span>}
    </button>
    {open&&<div className="nt-panel">
      <div className="nt-heading"><strong>{settings?'Préférences de notifications':'Mes notifications'}</strong>
        <button className="nt-plain" onClick={()=>{setOpen(false);setSettings(false)}} aria-label="Fermer"><X size={18}/></button></div>
      {message&&<p className="nt-message" role="status">{message}</p>}
      {!settings ? <>
        <div className="nt-tools"><button onClick={()=>void openSettings()}><Settings2 size={14}/> Préférences</button>
          <button onClick={()=>void markAll().catch(()=>setMessage('Impossible de marquer les notifications.'))}><CheckCheck size={14}/> Tout lire</button></div>
        <div className="nt-list">
          {items.map(n=><button key={n.id} className={'nt-item'+(!n.read_at?' unread':'')} onClick={()=>void markOne(n)}>
            <strong>{n.title}</strong><span>{n.message}</span>
            <small>{new Date(n.created_at).toLocaleString('fr-FR',{dateStyle:'short',timeStyle:'short'})}</small>
          </button>)}
          {!items.length&&<p className="nt-empty">Aucune notification pour le moment.</p>}
        </div>
      </>:<>
        {prefs ? <div className="nt-preferences">
          <label><input type="checkbox" checked={prefs.push_enabled} onChange={e=>setPrefs({...prefs,push_enabled:e.target.checked})}/> Autoriser les notifications push</label>
          <h4>Événements à suivre</h4>
          {Object.entries(eventLabels).map(([key,label])=><label key={key}>
            <input type="checkbox" checked={prefs.events[key]??true} onChange={e=>setPrefs({...prefs,events:{...prefs.events,[key]:e.target.checked}})}/>{label}</label>)}
          <div className="nt-setting-actions">
            <button disabled={busy} onClick={()=>void savePreferences()}><Settings2 size={14}/> Enregistrer</button>
            <button disabled={busy||!pushKey} onClick={()=>void enablePush()} title={!pushKey?'Configurer VAPID sur le NAS':'Autoriser cet appareil'}><Smartphone size={14}/> Activer le push sur cet appareil</button>
            <button disabled={busy} onClick={()=>void unsubscribe()}><BellOff size={14}/> Retirer les appareils push</button>
            <button className="nt-back" onClick={()=>setSettings(false)}>Retour aux notifications</button>
          </div>
          <small>Les alertes dans l'application restent consultables. Le push est facultatif. Les push nécessitent HTTPS et un navigateur compatible.</small>
        </div>:<p>Chargement…</p>}
      </>}
    </div>}
  </div>
}

export function FollowCardV7({cardId}:{cardId:number}){
  const [followed,setFollowed]=useState(false)
  const [busy,setBusy]=useState(false)
  useEffect(()=>{let mounted=true
    void api<{followed:boolean}>('/api/cards/'+cardId+'/follow').then(r=>{if(mounted)setFollowed(r.followed)}).catch(()=>undefined)
    return ()=>{mounted=false}
  },[cardId])
  async function toggle(){
    setBusy(true)
    try{const r=await api<{followed:boolean}>('/api/cards/'+cardId+'/follow','PUT',{follow:!followed});setFollowed(r.followed)}
    finally{setBusy(false)}
  }
  return <button className="nt-follow" disabled={busy} onClick={()=>void toggle().catch(()=>undefined)}>
    {followed?<Bell size={15}/>:<BellOff size={15}/>}
    {followed?'Abonné aux commentaires':'Suivre les commentaires'}
  </button>
}


export function CardRemindersV7({cardId}:{cardId:number}){
  const [days,setDays]=useState<number[]>([3,1,0])
  const [overdue,setOverdue]=useState(true)
  const [busy,setBusy]=useState(false)
  const [message,setMessage]=useState('')
  useEffect(()=>{let active=true
    void api<{days_before:number[];overdue_next_day:boolean}>('/api/cards/'+cardId+'/reminders')
      .then(r=>{if(active){setDays(r.days_before);setOverdue(r.overdue_next_day)}})
      .catch(()=>{if(active)setMessage('Impossible de lire les rappels.')})
    return ()=>{active=false}
  },[cardId])
  async function save(){
    setBusy(true);setMessage('')
    try{
      await api('/api/cards/'+cardId+'/reminders','PUT',{days_before:days,overdue_next_day:overdue})
      setMessage('Rappels sauvegardés.')
    }catch(e){setMessage(e instanceof Error?e.message:'Erreur de sauvegarde')}
    finally{setBusy(false)}
  }
  return <section className="nt-reminders">
    <strong>Rappels de la carte</strong>
    <p>Activés lorsqu’une date d’échéance est renseignée. Aucun rappel pour les cartes terminées.</p>
    <div>{[7,3,1,0].map(d=><label key={d}><input type="checkbox" checked={days.includes(d)}
      onChange={e=>setDays(old=>e.target.checked?[...old,d].sort((a,b)=>b-a):old.filter(x=>x!==d))}/>
      {d===0?'Le jour J':'J-'+d}</label>)}
      <label><input type="checkbox" checked={overdue} onChange={e=>setOverdue(e.target.checked)}/>
        J+1 si en retard (une seule fois)</label></div>
    <button type="button" onClick={()=>void save()} disabled={busy}>Enregistrer les rappels</button>
    {message&&<small role="status">{message}</small>}
  </section>
}
