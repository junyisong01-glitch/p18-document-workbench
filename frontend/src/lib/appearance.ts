import { useSyncExternalStore } from 'react'

export type Appearance = 'blue' | 'charcoal'
const storageKey = 'p18.appearance'
const changeEvent = 'p18-appearance-change'
function readPreference(): Appearance {
  try { return localStorage.getItem(storageKey) === 'charcoal' ? 'charcoal' : 'blue' }
  catch { return 'blue' }
}
let current = readPreference()
function apply() {
  document.documentElement.classList.toggle('charcoal-theme', current === 'charcoal')
}
export function initializeAppearance() { apply() }
export function setAppearance(next: Appearance) {
  current = next
  try { localStorage.setItem(storageKey, next) } catch { /* Keep this tab usable without storage. */ }
  apply()
  window.dispatchEvent(new Event(changeEvent))
}
function subscribe(callback: () => void) {
  function sync(event: StorageEvent) {
    if (event.key !== storageKey && event.key !== null) return
    current = readPreference()
    apply()
    callback()
  }
  window.addEventListener(changeEvent, callback)
  window.addEventListener('storage', sync)
  return () => {
    window.removeEventListener(changeEvent, callback)
    window.removeEventListener('storage', sync)
  }
}
export function useAppearance() {
  return useSyncExternalStore(subscribe, () => current, () => 'blue' as Appearance)
}
