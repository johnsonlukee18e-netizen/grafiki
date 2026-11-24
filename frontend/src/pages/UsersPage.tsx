import { useAuthStatus, useSaveUser, useUsers } from '../api/hooks'
import { ErrorBox, Loading, PageHeader } from '../components/common'
import { useToasts } from '../components/Toasts'
import { formatDateTime } from '../lib'

export default function UsersPage() {
  const { data, isLoading, error } = useUsers()
  const { data: auth } = useAuthStatus()
  const save = useSaveUser()
  const toasts = useToasts()

  if (isLoading) return <Loading />
  if (error) return <ErrorBox error={error} />

  const meId = auth?.user?.id
  // Accounts that authenticated with Google but were never granted access.
  const pending = (data ?? []).filter((u) => !u.is_active)

  return (
    <>
      <PageHeader
        title="Użytkownicy"
        subtitle="Konta powstają automatycznie przy pierwszym logowaniu przez Google, ale bez dostępu - to Ty go przyznajesz przełącznikiem Aktywne. Hasła nie są przechowywane."
      />

      {pending.length > 0 && (
        <div className="alert alert-warning d-flex align-items-start gap-2" role="alert">
          <i className="bi bi-person-exclamation fs-5" />
          <div>
            <strong>
              {pending.length === 1
                ? 'Jedno konto czeka na zatwierdzenie'
                : `Konta czekające na zatwierdzenie: ${pending.length}`}
            </strong>
            <div className="small">
              {pending.map((u) => u.email).join(', ')} - dopoki przelacznik
              <em> Aktywne</em> jest wyłączony, te osoby nie widzą żadnych danych.
              Włącz go tylko dla osób, które rzeczywiście mają pracować z grafikiem.
            </div>
          </div>
        </div>
      )}

      <div className="card shadow-sm">
        <div className="table-responsive">
          <table className="table table-hover align-middle mb-0">
            <thead className="">
              <tr>
                <th>E-mail</th>
                <th>Nazwa</th>
                <th>Rola</th>
                <th>Aktywne</th>
                <th>Ostatnie logowanie</th>
              </tr>
            </thead>
            <tbody>
              {(data ?? []).map((user) => (
                <tr key={user.id}>
                  <td>
                    {user.email}
                    {user.id === meId && (
                      <span className="badge text-bg-primary ms-2">to Ty</span>
                    )}
                    {!user.is_active && (
                      <span className="badge text-bg-warning ms-2">brak dostępu</span>
                    )}
                  </td>
                  <td>{user.name ?? '-'}</td>
                  <td>
                    <select
                      className="form-select form-select-sm"
                      style={{ maxWidth: 140 }}
                      value={user.role}
                      disabled={user.id === meId}
                      onChange={(e) =>
                        save.mutate(
                          { id: user.id, role: e.target.value },
                          {
                            onSuccess: () => toasts.success('Rola zmieniona'),
                            onError: (err) => toasts.error('Błąd', (err as Error).message),
                          },
                        )
                      }
                    >
                      <option value="ADMIN">ADMIN</option>
                      <option value="MANAGER">MANAGER</option>
                    </select>
                  </td>
                  <td>
                    <div className="form-check form-switch">
                      <input
                        className="form-check-input"
                        type="checkbox"
                        checked={user.is_active}
                        disabled={user.id === meId}
                        onChange={(e) =>
                          save.mutate(
                            { id: user.id, is_active: e.target.checked },
                            {
                              onSuccess: () => toasts.success('Zapisano'),
                              onError: (err) => toasts.error('Błąd', (err as Error).message),
                            },
                          )
                        }
                      />
                    </div>
                  </td>
                  <td>{formatDateTime(user.last_login_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  )
}
