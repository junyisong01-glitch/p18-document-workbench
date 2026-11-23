import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'
import './index.css'
import App from './App.tsx'
import './lexiang-preview.css'
import './charcoal-theme.css'
import './appearance.css'
import { initializeAppearance } from './lib/appearance'

document.documentElement.classList.add('lexiang-preview')
initializeAppearance()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
)
