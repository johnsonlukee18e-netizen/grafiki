/**
 * Light / dark appearance.
 *
 * The app follows the system setting by default ("auto"). A person can pin
 * light or dark for this browser; the choice is a per-device convenience kept
 * in localStorage. Bootstrap 5.3 reads `data-bs-theme` on <html>.
 */
import { useEffect, useState } from 'react'

export type ThemePreference = 'auto' | 'light' | 'dark'

const KEY = 'grafiki.theme'
const media = () => window.matchMedia('(prefers-color-scheme: dark)')

export function readPreference(): ThemePreference {
  try {
    const value = localStorage.getItem(KEY)
    if (value === 'light' || value === 'dark' || value === 'auto') return value
  } catch {
    /* storage blocked - fall back to the system setting */
  }
  return 'auto'
}

export function applyTheme(preference: ThemePreference): void {
  const dark = preference === 'dark' || (preference === 'auto' && media().matches)
  document.documentElement.setAttribute('data-bs-theme', dark ? 'dark' : 'light')
}

export function useTheme(): [ThemePreference, (next: ThemePreference) => void] {
  const [preference, setPreference] = useState<ThemePreference>(readPreference)

  useEffect(() => {
    applyTheme(preference)
    if (preference !== 'auto') return
    const query = media()
    const onChange = () => applyTheme('auto')
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [preference])

  const update = (next: ThemePreference) => {
    try {
      localStorage.setItem(KEY, next)
    } catch {
      /* not persisted - still applied for this visit */
    }
    setPreference(next)
  }
  return [preference, update]
}
