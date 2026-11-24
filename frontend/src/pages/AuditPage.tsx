import { useState } from 'react'

import { useAudit } from '../api/hooks'
import { ErrorBox, Loading, PageHeader } from '../components/common'
import { ACTION_LABEL, formatDateTime } from '../lib'

export default function AuditPage() {
  const [limit, setLimit] = useState(150)
  const [filter, setFilter] = useState('')
  const { data, isLoading, error } = useAudit(limit)

  if (isLoading) return <Loading />
  if (error) return <ErrorBox error={error} />

  const rows = (data ?? []).filter((row) => {
    if (!filter) return true
    const needle = filter.toLowerCase()
    return (
      row.action.toLowerCase().includes(needle) ||
      (row.user_email ?? '').toLowerCase().includes(needle) ||
      (row.entity_type ?? '').toLowerCase().includes(needle)
    )
  })

  return (
    <>
      <PageHeader
        title="Dziennik zdarzeń"
        subtitle="Każda istotna operacja jest rejestrowana wraz z użytkownikiem i czasem."
        actions={
          <>
            <input
              className="form-control"
              style={{ maxWidth: 240 }}
              placeholder="Filtruj (akcja, e-mail...)"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
            <select
              className="form-select"
              style={{ maxWidth: 130 }}
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
            >
              {[50, 150, 300, 500].map((value) => (
                <option key={value} value={value}>
                  {value} wpisów
                </option>
              ))}
            </select>
          </>
        }
      />

      <div className="card shadow-sm">
        <div className="table-responsive" style={{ maxHeight: '70vh' }}>
          <table className="table table-sm table-hover align-middle mb-0 table-sticky-head">
            <thead className="">
              <tr>
                <th style={{ minWidth: 150 }}>Czas</th>
                <th>Użytkownik</th>
                <th>Akcja</th>
                <th>Obiekt</th>
                <th>Szczegóły</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td className="text-nowrap">{formatDateTime(row.timestamp)}</td>
                  <td>{row.user_email ?? '-'}</td>
                  <td>{ACTION_LABEL[row.action] ?? row.action}</td>
                  <td className="small text-secondary">
                    {row.entity_type}
                    {row.entity_id ? ` #${row.entity_id}` : ''}
                  </td>
                  <td className="small text-secondary">
                    <code className="text-secondary">
                      {row.metadata ? JSON.stringify(row.metadata).slice(0, 160) : ''}
                    </code>
                  </td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={5} className="text-center text-secondary py-4">
                    Brak wpisów.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </>
  )
}
