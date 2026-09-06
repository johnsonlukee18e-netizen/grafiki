import { useState } from 'react'

import { useCreateHoliday, useDeleteHoliday, useHolidays } from '../api/hooks'
import { ErrorBox, Loading, PageHeader } from '../components/common'
import { useToasts } from '../components/Toasts'
import { WEEKDAYS_PL, formatDate, todayParts } from '../lib'

export default function HolidaysPage() {
  const [year, setYear] = useState(todayParts().year)
  const { data, isLoading, error } = useHolidays(year)
  const create = useCreateHoliday()
  const remove = useDeleteHoliday()
  const toasts = useToasts()
  const [form, setForm] = useState({ date: `${year}-01-01`, name: '' })

  if (isLoading) return <Loading />
  if (error) return <ErrorBox error={error} />

  const years = Array.from({ length: 7 }, (_, i) => todayParts().year - 2 + i)

  return (
    <>
      <PageHeader
        title="Swieta"
        subtitle="Swieta ustawowo wolne od pracy w Polsce sa wyliczane automatycznie dla dowolnego roku."
        actions={
          <select
            className="form-select"
            style={{ maxWidth: 120 }}
            value={year}
            onChange={(e) => setYear(Number(e.target.value))}
          >
            {years.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        }
      />

      <div className="row g-3">
        <div className="col-12 col-lg-7">
          <div className="card shadow-sm">
            <div className="table-responsive">
              <table className="table table-hover align-middle mb-0">
                <thead className="table-light">
                  <tr>
                    <th>Data</th>
                    <th>Dzien</th>
                    <th>Nazwa</th>
                    <th>Zrodlo</th>
                    <th className="text-end" />
                  </tr>
                </thead>
                <tbody>
                  {(data ?? []).map((holiday) => {
                    const weekday = new Date(`${holiday.date}T00:00:00`).getDay()
                    return (
                      <tr key={holiday.id}>
                        <td>{formatDate(holiday.date)}</td>
                        <td>{WEEKDAYS_PL[(weekday + 6) % 7]}</td>
                        <td>{holiday.name}</td>
                        <td>
                          {holiday.is_custom ? (
                            <span className="badge text-bg-info">wlasne</span>
                          ) : (
                            <span className="badge text-bg-secondary">ustawowe</span>
                          )}
                        </td>
                        <td className="text-end">
                          {holiday.is_custom && (
                            <button
                              className="btn btn-sm btn-outline-danger"
                              onClick={() =>
                                remove.mutate(holiday.id, {
                                  onSuccess: () => toasts.success('Usunieto'),
                                  onError: (err) => toasts.error('Blad', (err as Error).message),
                                })
                              }
                              type="button"
                            >
                              <i className="bi bi-trash" />
                            </button>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <div className="col-12 col-lg-5">
          <div className="card shadow-sm">
            <div className="card-header bg-white fw-semibold">Dodaj dzien wolny (ADMIN)</div>
            <div className="card-body">
              <div className="mb-2">
                <label className="form-label">Data</label>
                <input
                  type="date"
                  className="form-control"
                  value={form.date}
                  onChange={(e) => setForm({ ...form, date: e.target.value })}
                />
              </div>
              <div className="mb-3">
                <label className="form-label">Nazwa</label>
                <input
                  className="form-control"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="np. Dzien wolny oddzialu"
                />
              </div>
              <button
                className="btn btn-primary w-100"
                disabled={!form.name.trim() || create.isPending}
                onClick={() =>
                  create.mutate(form, {
                    onSuccess: () => {
                      toasts.success('Dodano dzien wolny')
                      setForm({ date: form.date, name: '' })
                    },
                    onError: (err) => toasts.error('Nie dodano', (err as Error).message),
                  })
                }
                type="button"
              >
                Dodaj
              </button>
              <p className="small text-secondary mt-2 mb-0">
                Swiat ustawowych nie mozna usunac - wynikaja z przepisow.
              </p>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
