import { useEffect } from 'react'
import { Navigate, NavLink, Route, Routes, useNavigate } from 'react-router-dom'

import { UNAUTHORIZED_EVENT } from './api/client'
import { useAuthStatus, useLogout } from './api/hooks'
import { Loading } from './components/common'
import { type ThemePreference, useTheme } from './theme'
import AvailabilityPage from './pages/AvailabilityPage'
import AuditPage from './pages/AuditPage'
import DashboardPage from './pages/DashboardPage'
import EmployeesPage from './pages/EmployeesPage'
import HistoryPage from './pages/HistoryPage'
import HolidaysPage from './pages/HolidaysPage'
import LoginPage from './pages/LoginPage'
import ManualPage from './pages/ManualPage'
import SchedulePage from './pages/SchedulePage'
import SettingsPage from './pages/SettingsPage'
import UsersPage from './pages/UsersPage'

interface NavItem {
  to: string
  label: string
  icon: string
  adminOnly?: boolean
}

const NAV: { section: string; items: NavItem[] }[] = [
  {
    section: 'Planowanie',
    items: [
      { to: '/', label: 'Pulpit', icon: 'bi-grid-1x2' },
      { to: '/grafik', label: 'Grafik', icon: 'bi-calendar3' },
      { to: '/reczne', label: 'Ręczne układanie', icon: 'bi-pencil-square' },
      { to: '/dostepnosc', label: 'Dostępność', icon: 'bi-calendar-check' },
      { to: '/historia', label: 'Historia grafików', icon: 'bi-clock-history' },
    ],
  },
  {
    section: 'Oddział',
    items: [
      { to: '/pracownicy', label: 'Pracownicy', icon: 'bi-people' },
      { to: '/swieta', label: 'Święta', icon: 'bi-stars' },
      { to: '/ustawienia', label: 'Ustawienia', icon: 'bi-sliders' },
    ],
  },
  {
    section: 'Administracja',
    items: [
      { to: '/uzytkownicy', label: 'Użytkownicy', icon: 'bi-shield-lock', adminOnly: true },
      { to: '/audyt', label: 'Dziennik zdarzeń', icon: 'bi-journal-text', adminOnly: true },
    ],
  },
]

const ROLE_NAME: Record<string, string> = {
  ADMIN: 'Administrator',
  MANAGER: 'Kierownik',
}

const THEMES: { value: ThemePreference; icon: string; label: string }[] = [
  { value: 'auto', icon: 'bi-circle-half', label: 'Jak w systemie' },
  { value: 'light', icon: 'bi-sun', label: 'Jasny' },
  { value: 'dark', icon: 'bi-moon-stars', label: 'Ciemny' },
]

function initials(name: string): string {
  const parts = name.replace(/@.*/, '').split(/[\s._-]+/).filter(Boolean)
  return ((parts[0]?.[0] ?? '?') + (parts[1]?.[0] ?? '')).toUpperCase()
}

export default function App() {
  const { data, isLoading } = useAuthStatus()
  const navigate = useNavigate()
  const logout = useLogout()
  const [theme, setTheme] = useTheme()

  useEffect(() => {
    const handler = () => navigate('/login', { replace: true })
    window.addEventListener(UNAUTHORIZED_EVENT, handler)
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, handler)
  }, [navigate])

  if (isLoading) {
    return (
      <div className="container py-5">
        <Loading label="Sprawdzanie sesji..." />
      </div>
    )
  }

  if (!data?.authenticated) {
    return (
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    )
  }

  const user = data.user!
  const isAdmin = user.role === 'ADMIN'
  const displayName = user.name || user.email

  return (
    <div className="app-shell">
      <aside className="app-sidebar p-3">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            <i className="bi bi-calendar2-heart" />
          </span>
          <div>
            <div className="brand-name">Grafiki</div>
            <div className="brand-sub">oddział szpitalny</div>
          </div>
        </div>

        <nav aria-label="Nawigacja główna">
          {NAV.map((group) => {
            const items = group.items.filter((item) => !item.adminOnly || isAdmin)
            if (items.length === 0) return null
            return (
              <div key={group.section}>
                <div className="nav-section">{group.section}</div>
                <div className="nav flex-column gap-1">
                  {items.map((item) => (
                    <NavLink key={item.to} to={item.to} end={item.to === '/'} className="nav-link">
                      <i className={`bi ${item.icon}`} aria-hidden="true" />
                      <span>{item.label}</span>
                    </NavLink>
                  ))}
                </div>
              </div>
            )
          })}
        </nav>

        <div className="sidebar-footer">
          <div className="btn-group w-100 mb-3 theme-switch" role="group" aria-label="Wygląd">
            {THEMES.map((option) => (
              <button
                key={option.value}
                type="button"
                className={`btn btn-sm ${
                  theme === option.value ? 'btn-primary' : 'btn-outline-secondary'
                }`}
                onClick={() => setTheme(option.value)}
                title={`Wygląd: ${option.label}`}
                aria-label={`Wygląd: ${option.label}`}
                aria-pressed={theme === option.value}
              >
                <i className={`bi ${option.icon}`} aria-hidden="true" />
              </button>
            ))}
          </div>

          <div className="d-flex align-items-center gap-2 mb-2 px-1">
            <span className="avatar" aria-hidden="true">
              {initials(displayName)}
            </span>
            <div className="small lh-sm" style={{ minWidth: 0 }}>
              <div className="fw-semibold text-truncate" title={user.email}>
                {displayName}
              </div>
              <div className="text-secondary">{ROLE_NAME[user.role] ?? user.role}</div>
            </div>
          </div>
          <button
            className="btn btn-sm btn-outline-secondary w-100"
            onClick={() => logout.mutate()}
            disabled={logout.isPending}
            type="button"
          >
            <i className="bi bi-box-arrow-right me-1" aria-hidden="true" />
            Wyloguj
          </button>
        </div>
      </aside>

      <main className="app-main">
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/grafik" element={<SchedulePage />} />
          <Route path="/reczne" element={<ManualPage />} />
          <Route path="/pracownicy" element={<EmployeesPage />} />
          <Route path="/dostepnosc" element={<AvailabilityPage />} />
          <Route path="/swieta" element={<HolidaysPage />} />
          <Route path="/historia" element={<HistoryPage />} />
          <Route path="/ustawienia" element={<SettingsPage />} />
          <Route
            path="/uzytkownicy"
            element={isAdmin ? <UsersPage /> : <Navigate to="/" replace />}
          />
          <Route path="/audyt" element={isAdmin ? <AuditPage /> : <Navigate to="/" replace />} />
          <Route path="/login" element={<Navigate to="/" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  )
}
