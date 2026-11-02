/* Orga Alfiya — service worker minimal pour notifications, sans cache des données privées. */
self.addEventListener('install',()=>self.skipWaiting());
self.addEventListener('activate',event=>event.waitUntil(self.clients.claim()));
self.addEventListener('push',event=>{
  let data={title:'Orga Alfiya',body:'Vous avez une nouvelle notification.',url:'/'};
  try{if(event.data) data={...data,...event.data.json()}}catch{/* default */}
  const target=new URL(data.url||'/',self.location.origin);
  const url=target.origin===self.location.origin?target.href:self.location.origin+'/';
  event.waitUntil(self.registration.showNotification(data.title,{
    body:data.body,icon:'/logo-bde.png',badge:'/logo-bde.png',
    tag:'orga-'+Date.now(),data:{url}
  }));
});
self.addEventListener('notificationclick',event=>{
  event.notification.close();
  const raw=event.notification.data?.url||'/';
  const target=new URL(raw,self.location.origin);
  const url=target.origin===self.location.origin?target.href:self.location.origin+'/';
  event.waitUntil((async()=>{
    const windows=await self.clients.matchAll({type:'window',includeUncontrolled:true});
    for(const client of windows){if(client.url.startsWith(self.location.origin)){
      await client.navigate(url);return client.focus();
    }}
    return self.clients.openWindow(url);
  })());
});
