import React from 'react'
import ReactDOM from 'react-dom/client'
import AuthGate from './AuthGate'
import './styles.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode><AuthGate /></React.StrictMode>,
)

// Service worker de la PWA (aucune mise en cache des documents privés).
if ('serviceWorker' in navigator && window.location.protocol === 'https:') {
  void navigator.serviceWorker.register('/sw.js').catch(() => undefined)
}
