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

  return (
    <>
      <PageHeader
        title="Uzytkownicy"
        subtitle="Konta powstaja automatycznie przy pierwszym logowaniu przez Google. Hasla nie sa przechowywane."
      />

      <div className="card shadow-sm">
        <div className="table-responsive">
          <table className="table table-hover align-middle mb-0">
            <thead className="table-light">
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
                            onError: (err) => toasts.error('Blad', (err as Error).message),
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
                              onError: (err) => toasts.error('Blad', (err as Error).message),
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
