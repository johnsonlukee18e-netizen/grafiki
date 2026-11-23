import { useEffect } from 'react'
import { Navigate, NavLink, Route, Routes, useNavigate } from 'react-router-dom'

import { UNAUTHORIZED_EVENT } from './api/client'
import { useAuthStatus, useLogout } from './api/hooks'
import { Loading } from './components/common'
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

const NAV: NavItem[] = [
  { to: '/', label: 'Dashboard', icon: 'bi-speedometer2' },
  { to: '/grafik', label: 'Grafik', icon: 'bi-calendar3' },
  { to: '/reczne', label: 'Reczne ukladanie', icon: 'bi-pencil-square' },
  { to: '/pracownicy', label: 'Pracownicy', icon: 'bi-people' },
  { to: '/dostepnosc', label: 'Dostepnosc', icon: 'bi-calendar-check' },
  { to: '/swieta', label: 'Swieta', icon: 'bi-stars' },
  { to: '/historia', label: 'Historia grafikow', icon: 'bi-clock-history' },
  { to: '/ustawienia', label: 'Ustawienia', icon: 'bi-gear' },
  { to: '/uzytkownicy', label: 'Uzytkownicy', icon: 'bi-shield-lock', adminOnly: true },
  { to: '/audyt', label: 'Dziennik zdarzen', icon: 'bi-journal-text', adminOnly: true },
]

export default function App() {
  const { data, isLoading } = useAuthStatus()
  const navigate = useNavigate()
  const logout = useLogout()

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
  const visible = NAV.filter((item) => !item.adminOnly || isAdmin)

  return (
    <div className="app-shell">
      <aside className="app-sidebar p-3">
        <div className="d-flex align-items-center gap-2 mb-4 px-1">
          <i className="bi bi-hospital fs-4 text-primary" />
          <div>
            <div className="fw-semibold text-white lh-1">Grafiki</div>
            <div className="small text-secondary">oddzial szpitalny</div>
          </div>
        </div>

        <nav className="nav nav-pills flex-column gap-1">
          {visible.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.to === '/'} className="nav-link">
              <i className={`bi ${item.icon}`} />
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>

        <hr className="text-secondary" />

        <div className="px-1 small">
          <div className="text-white text-truncate" title={user.email}>
            {user.name || user.email}
          </div>
          <div className="text-secondary mb-2">{user.role}</div>
          <button
            className="btn btn-sm btn-outline-light w-100"
            onClick={() => logout.mutate()}
            disabled={logout.isPending}
            type="button"
          >
            <i className="bi bi-box-arrow-right me-1" />
            Wyloguj
          </button>
        </div>
      </aside>

      <main className="app-main p-3 p-lg-4">
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
