import { useState } from 'react'

import { useDeactivateEmployee, useEmployees, useSaveEmployee } from '../api/hooks'
import type { EmployeePayload } from '../api/hooks'
import { ColorDot, ErrorBox, Loading, Modal, PageHeader } from '../components/common'
import { useToasts } from '../components/Toasts'
import { COLOR_LABEL, ROLE_LABEL, formatDate } from '../lib'
import type { Employee } from '../types'

const EMPTY: EmployeePayload = {
  first_name: '',
  last_name: '',
  role: 'NURSE',
  employment_date: new Date().toISOString().slice(0, 10),
  active: true,
}

export default function EmployeesPage() {
  const { data, isLoading, error } = useEmployees()
  const save = useSaveEmployee()
  const deactivate = useDeactivateEmployee()
  const toasts = useToasts()

  const [editing, setEditing] = useState<{ id?: number; data: EmployeePayload } | null>(null)
  const [showInactive, setShowInactive] = useState(true)

  if (isLoading) return <Loading />
  if (error) return <ErrorBox error={error} />

  const employees = (data ?? []).filter((e) => showInactive || e.active)

  const submit = () => {
    if (!editing) return
    if (!editing.data.first_name.trim() || !editing.data.last_name.trim()) {
      toasts.error('Uzupełnij dane', 'Imię i nazwisko są wymagane.')
      return
    }
    save.mutate(editing, {
      onSuccess: () => {
        toasts.success(editing.id ? 'Dane zapisane' : 'Pracownik dodany')
        setEditing(null)
      },
      onError: (err) => toasts.error('Nie zapisano', (err as Error).message),
    })
  }

  return (
    <>
      <PageHeader
        title="Pracownicy"
        subtitle="Kolor wynika automatycznie ze stażu pracy i roli - nie można go ustawić ręcznie."
        actions={
          <>
            <div className="form-check form-switch align-self-center me-2">
              <input
                className="form-check-input"
                type="checkbox"
                id="showInactive"
                checked={showInactive}
                onChange={(e) => setShowInactive(e.target.checked)}
              />
              <label className="form-check-label small" htmlFor="showInactive">
                Pokaż nieaktywnych
              </label>
            </div>
            <button
              className="btn btn-primary"
              onClick={() => setEditing({ data: { ...EMPTY } })}
              type="button"
            >
              <i className="bi bi-plus-lg me-1" /> Dodaj pracownika
            </button>
          </>
        }
      />

      <div className="card shadow-sm">
        <div className="table-responsive">
          <table className="table table-hover align-middle mb-0">
            <thead className="">
              <tr>
                <th style={{ width: 50 }}>Kolor</th>
                <th>Imię</th>
                <th>Nazwisko</th>
                <th>Rola</th>
                <th>Zatrudniony</th>
                <th>Staż</th>
                <th>Aktywny</th>
                <th className="text-end">Akcje</th>
              </tr>
            </thead>
            <tbody>
              {employees.map((employee) => (
                <tr key={employee.id} className={employee.active ? '' : 'opacity-50'}>
                  <td>
                    <ColorDot color={employee.color} />
                  </td>
                  <td>{employee.first_name}</td>
                  <td className="fw-semibold">{employee.last_name}</td>
                  <td>{ROLE_LABEL[employee.role]}</td>
                  <td>{formatDate(employee.employment_date)}</td>
                  <td>{employee.seniority_label}</td>
                  <td>
                    {employee.active ? (
                      <span className="badge text-bg-success">tak</span>
                    ) : (
                      <span className="badge text-bg-secondary">nie</span>
                    )}
                  </td>
                  <td className="text-end">
                    <button
                      className="btn btn-sm btn-outline-secondary me-1"
                      onClick={() => setEditing({ id: employee.id, data: toPayload(employee) })}
                      type="button"
                    >
                      <i className="bi bi-pencil" />
                    </button>
                    {employee.active && (
                      <button
                        className="btn btn-sm btn-outline-danger"
                        title="Dezaktywuj"
                        onClick={() =>
                          deactivate.mutate(employee.id, {
                            onSuccess: () => toasts.success('Pracownik dezaktywowany'),
                            onError: (err) => toasts.error('Błąd', (err as Error).message),
                          })
                        }
                        type="button"
                      >
                        <i className="bi bi-person-dash" />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {employees.length === 0 && (
                <tr>
                  <td colSpan={8} className="text-center text-secondary py-4">
                    Brak pracowników.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="d-flex flex-wrap gap-3 small text-secondary mt-3">
        {(['RED', 'YELLOW', 'GREEN', 'PURPLE'] as const).map((color) => (
          <span key={color} className="d-flex align-items-center gap-1">
            <ColorDot color={color} />
            {COLOR_LABEL[color]}
          </span>
        ))}
      </div>

      {editing && (
        <Modal
          title={editing.id ? 'Edycja pracownika' : 'Nowy pracownik'}
          onClose={() => setEditing(null)}
          footer={
            <>
              <button className="btn btn-outline-secondary" onClick={() => setEditing(null)} type="button">
                Anuluj
              </button>
              <button className="btn btn-primary" onClick={submit} disabled={save.isPending} type="button">
                Zapisz
              </button>
            </>
          }
        >
          <div className="row g-3">
            <div className="col-6">
              <label className="form-label">Imię</label>
              <input
                className="form-control"
                value={editing.data.first_name}
                onChange={(e) =>
                  setEditing({ ...editing, data: { ...editing.data, first_name: e.target.value } })
                }
              />
            </div>
            <div className="col-6">
              <label className="form-label">Nazwisko</label>
              <input
                className="form-control"
                value={editing.data.last_name}
                onChange={(e) =>
                  setEditing({ ...editing, data: { ...editing.data, last_name: e.target.value } })
                }
              />
            </div>
            <div className="col-6">
              <label className="form-label">Rola</label>
              <select
                className="form-select"
                value={editing.data.role}
                onChange={(e) =>
                  setEditing({ ...editing, data: { ...editing.data, role: e.target.value } })
                }
              >
                <option value="NURSE">Pielęgniarka</option>
                <option value="CARE_WORKER">Opiekunka</option>
              </select>
            </div>
            <div className="col-6">
              <label className="form-label">Data zatrudnienia</label>
              <input
                type="date"
                className="form-control"
                value={editing.data.employment_date}
                onChange={(e) =>
                  setEditing({
                    ...editing,
                    data: { ...editing.data, employment_date: e.target.value },
                  })
                }
              />
            </div>
            <div className="col-12">
              <div className="form-check form-switch">
                <input
                  className="form-check-input"
                  type="checkbox"
                  id="activeSwitch"
                  checked={editing.data.active}
                  onChange={(e) =>
                    setEditing({ ...editing, data: { ...editing.data, active: e.target.checked } })
                  }
                />
                <label className="form-check-label" htmlFor="activeSwitch">
                  Pracownik aktywny (uwzględniany w grafiku)
                </label>
              </div>
            </div>
          </div>
        </Modal>
      )}
    </>
  )
}

function toPayload(employee: Employee): EmployeePayload {
  return {
    first_name: employee.first_name,
    last_name: employee.last_name,
    role: employee.role,
    employment_date: employee.employment_date,
    active: employee.active,
  }
}
