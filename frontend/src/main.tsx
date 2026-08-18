import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.tsx'
import './index.css'
import './i18n' // French by default, English hand-written beside it

// After a deployment, a tab left open may ask for a chunk whose hash has changed.
// Reload once (guarded against a loop) rather than show an application error.
window.addEventListener('vite:preloadError', () => {
  const KEY = 'chunk-reload-ts'
  const last = Number(sessionStorage.getItem(KEY) || '0')
  if (Date.now() - last > 10000) {
    sessionStorage.setItem(KEY, String(Date.now()))
    window.location.reload()
  }
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
