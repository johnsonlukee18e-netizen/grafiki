import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { useDashboard } from '../api/hooks'
import { ErrorBox, Loading, MonthPicker, PageHeader, StatusBadge } from '../components/common'
import { formatDateTime, monthLabel, todayParts } from '../lib'

export default function DashboardPage() {
  const initial = todayParts()
  const [year, setYear] = useState(initial.year)
  const [month, setMonth] = useState(initial.month)
  const { data, isLoading, error } = useDashboard(year, month)
  const navigate = useNavigate()

  if (isLoading) return <Loading />
  if (error) return <ErrorBox error={error} />
  if (!data) return null

  const current = data.current

  return (
    <>
      <PageHeader
        title="Pulpit"
        subtitle={`${data.facility_name} · ${data.department_name}`}
        actions={
          <MonthPicker
            year={year}
            month={month}
            onChange={(y, m) => {
              setYear(y)
              setMonth(m)
            }}
          />
        }
      />

      <div className="row g-3 mb-3">
        <div className="col-12 col-lg-7">
          <div className="card h-100 shadow-sm">
            <div className="card-body">
              <div className="d-flex justify-content-between align-items-start">
                <div>
                  <div className="text-secondary small text-uppercase">Aktualny grafik</div>
                  <div className="h4 mb-1">{monthLabel(year, month)}</div>
                </div>
                {current ? (
                  <div className="text-end">
                    <StatusBadge status={current.schedule.status} />
                    <div className="small text-secondary mt-1">
                      wersja v{current.schedule.version}
                    </div>
                  </div>
                ) : (
                  <span className="badge text-bg-secondary">Brak grafiku</span>
                )}
              </div>

              {current ? (
                <>
                  <div className="row text-center mt-3 g-2">
                    <Metric label="Zmiany" value={current.assignments} />
                    <Metric
                      label="Błędy"
                      value={current.errors}
                      variant={current.errors ? 'danger' : 'success'}
                    />
                    <Metric
                      label="Ostrzeżenia"
                      value={current.warnings}
                      variant={current.warnings ? 'warning' : 'success'}
                    />
                    <Metric label="Pracownicy" value={data.employees_active} />
                  </div>
                  <div className="small text-secondary mt-3">
                    Wygenerowano: {formatDateTime(current.schedule.generated_at)}
                    {current.schedule.approved_at && (
                      <> &middot; zatwierdzono: {formatDateTime(current.schedule.approved_at)}</>
                    )}
                  </div>
                </>
              ) : (
                <p className="text-secondary mt-3 mb-0">
                  Ten miesiąc nie ma jeszcze grafiku. Użyj przycisku
                  <strong> Generuj grafik</strong>, aby go ułożyć.
                </p>
              )}
            </div>
          </div>
        </div>

        <div className="col-12 col-lg-5">
          <div className="card h-100 shadow-sm">
            <div className="card-body">
              <div className="text-secondary small text-uppercase mb-2">Kontrola grafiku</div>
              {current?.checks?.length ? (
                <div>
                  {current.checks
                    .filter((row) => row.kind === 'hard')
                    .map((row) => (
                      <div className="check-row" key={row.code}>
                        <span>{row.label}</span>
                        <span
                          className={`badge text-bg-${
                            row.status === 'OK' ? 'success' : 'danger'
                          }`}
                        >
                          {row.status === 'OK' ? 'OK' : `${row.count} bł.`}
                        </span>
                      </div>
                    ))}
                </div>
              ) : (
                <p className="text-secondary small mb-0">
                  Brak wyników walidacji - wygeneruj lub zwaliduj grafik.
                </p>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="d-flex flex-wrap gap-2 mb-4">
        <button className="btn btn-primary" onClick={() => navigate('/grafik')} type="button">
          <i className="bi bi-calendar3 me-1" /> Otwórz grafik
        </button>
        <button
          className="btn btn-outline-primary"
          onClick={() => navigate('/grafik?generate=1')}
          type="button"
        >
          <i className="bi bi-cpu me-1" /> Generuj grafik
        </button>
        <button
          className="btn btn-outline-secondary"
          onClick={() => navigate('/pracownicy')}
          type="button"
        >
          <i className="bi bi-people me-1" /> Pracownicy
        </button>
        <button
          className="btn btn-outline-secondary"
          onClick={() => navigate('/dostepnosc')}
          type="button"
        >
          <i className="bi bi-calendar-check me-1" /> Dostępność
        </button>
      </div>

      <div className="row g-3">
        <div className="col-12 col-lg-6">
          <div className="card shadow-sm h-100">
            <div className="card-header fw-semibold">Ostatnie grafiki</div>
            <ul className="list-group list-group-flush">
              {data.recent_schedules.length === 0 && (
                <li className="list-group-item text-secondary small">Brak grafików.</li>
              )}
              {data.recent_schedules.map((schedule) => (
                <li
                  key={schedule.id}
                  className="list-group-item d-flex justify-content-between align-items-center"
                >
                  <button
                    className="btn btn-link p-0 text-decoration-none"
                    onClick={() => {
                      setYear(schedule.year)
                      setMonth(schedule.month)
                    }}
                    type="button"
                  >
                    {monthLabel(schedule.year, schedule.month)}
                  </button>
                  <span className="d-flex align-items-center gap-2">
                    <span className="small text-secondary">v{schedule.version}</span>
                    <StatusBadge status={schedule.status} />
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>

        <div className="col-12 col-lg-6">
          <div className="card shadow-sm h-100">
            <div className="card-header fw-semibold">Zmiany na oddziale</div>
            <div className="table-responsive">
              <table className="table table-sm mb-0">
                <thead>
                  <tr>
                    <th>Kod</th>
                    <th>Nazwa</th>
                    <th>Godziny</th>
                    <th className="text-end">Min. obsada</th>
                  </tr>
                </thead>
                <tbody>
                  {data.shifts.map((shift) => (
                    <tr key={shift.id}>
                      <td>
                        <span className={`badge shift-${shift.code}`}>{shift.code}</span>
                      </td>
                      <td>{shift.name}</td>
                      <td>
                        {shift.start_time.slice(0, 5)}-{shift.end_time.slice(0, 5)}
                      </td>
                      <td className="text-end">{shift.minimum_staff}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}

function Metric({
  label,
  value,
  variant = 'secondary',
}: {
  label: string
  value: number
  variant?: string
}) {
  return (
    <div className="col-6 col-md-3">
      <div className="metric h-100">
        <div className={`metric-value text-${variant}`}>{value}</div>
        <div className="small text-secondary">{label}</div>
      </div>
    </div>
  )
}
