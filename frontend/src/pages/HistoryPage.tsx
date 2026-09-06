import { useState } from 'react'

import { useHistory, useSchedules } from '../api/hooks'
import { ErrorBox, Loading, PageHeader, StatusBadge } from '../components/common'
import { formatDateTime, monthLabel } from '../lib'

export default function HistoryPage() {
  const { data: schedules, isLoading, error } = useSchedules()
  const [selected, setSelected] = useState<number | undefined>(undefined)
  const list = schedules ?? []
  const current = selected ?? list[0]?.id
  const { data: versions } = useHistory(current)

  if (isLoading) return <Loading />
  if (error) return <ErrorBox error={error} />

  const schedule = list.find((item) => item.id === current)

  return (
    <>
      <PageHeader
        title="Historia grafikow"
        subtitle="Kazda generacja i kazda reczna korekta zapisuje nowa wersje. Nic nie jest usuwane."
      />

      <div className="row g-3">
        <div className="col-12 col-lg-4">
          <div className="card shadow-sm">
            <div className="card-header bg-white fw-semibold">Grafiki</div>
            <ul className="list-group list-group-flush">
              {list.map((item) => (
                <li
                  key={item.id}
                  className={`list-group-item d-flex justify-content-between align-items-center ${
                    item.id === current ? 'active' : ''
                  }`}
                  role="button"
                  onClick={() => setSelected(item.id)}
                >
                  <span>{monthLabel(item.year, item.month)}</span>
                  <span className="d-flex gap-2 align-items-center">
                    <span className="small">v{item.version}</span>
                    {item.id !== current && <StatusBadge status={item.status} />}
                  </span>
                </li>
              ))}
              {list.length === 0 && (
                <li className="list-group-item text-secondary small">Brak grafikow.</li>
              )}
            </ul>
          </div>
        </div>

        <div className="col-12 col-lg-8">
          <div className="card shadow-sm">
            <div className="card-header bg-white fw-semibold">
              {schedule ? `Wersje - ${monthLabel(schedule.year, schedule.month)}` : 'Wersje'}
            </div>
            <div className="table-responsive">
              <table className="table table-sm align-middle mb-0">
                <thead className="table-light">
                  <tr>
                    <th>Wersja</th>
                    <th>Powod</th>
                    <th>Status przy zapisie</th>
                    <th>Data</th>
                  </tr>
                </thead>
                <tbody>
                  {(versions ?? []).map((version) => (
                    <tr key={version.id}>
                      <td className="fw-semibold">v{version.version}</td>
                      <td>{version.reason}</td>
                      <td>
                        <StatusBadge status={version.status} />
                      </td>
                      <td>{formatDateTime(version.created_at)}</td>
                    </tr>
                  ))}
                  {(versions ?? []).length === 0 && (
                    <tr>
                      <td colSpan={4} className="text-secondary small py-3">
                        Ten grafik nie ma jeszcze zapisanych wersji historycznych.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
