/** Per-employee monthly figures required by the specification. */
import { formatMinutes } from '../lib'
import type { Shift, Statistics } from '../types'

export default function StatisticsPanel({
  statistics,
  shifts,
  weeklyLimitMinutes,
  onEmployeePdf,
}: {
  statistics: Statistics
  shifts: Shift[]
  weeklyLimitMinutes: number
  onEmployeePdf?: (employeeId: number) => void
}) {
  const codes = shifts.map((s) => s.code)
  const fairness = statistics.fairness

  return (
    <div className="card shadow-sm">
      <div className="card-header bg-white d-flex flex-wrap justify-content-between align-items-center gap-2">
        <span className="fw-semibold">Statystyki</span>
        <span className="small text-secondary">
          rozrzut - noce: {fairness.nights?.spread ?? 0} &middot; weekendy:{' '}
          {fairness.weekend_shifts?.spread ?? 0} &middot; swieta:{' '}
          {fairness.holiday_shifts?.spread ?? 0} &middot; godziny:{' '}
          {formatMinutes(fairness.minutes?.spread ?? 0)}
        </span>
      </div>
      <div className="table-responsive">
        <table className="table table-sm table-hover align-middle mb-0">
          <thead className="table-light">
            <tr>
              <th>Pracownik</th>
              <th className="text-end">Godziny</th>
              {codes.map((code) => (
                <th key={code} className="text-center">
                  {code}
                </th>
              ))}
              <th className="text-center">So</th>
              <th className="text-center">Nd</th>
              <th className="text-center">Weekendy</th>
              <th className="text-center">Swieta</th>
              <th className="text-center">Wolne</th>
              {onEmployeePdf && <th />}
            </tr>
          </thead>
          <tbody>
            {statistics.employees.map((row) => {
              const exceeded = row.weeks.some((week) => week.limit_exceeded)
              return (
                <tr key={row.employee_id}>
                  <td>{row.employee_name}</td>
                  <td className={`text-end ${exceeded ? 'text-danger fw-semibold' : ''}`}>
                    <span
                      title={row.weeks
                        .map((week) => `${week.week}: ${week.label}`)
                        .join('\n')}
                    >
                      {row.hours_label}
                    </span>
                    <span className="text-secondary small">
                      {' '}
                      / {formatMinutes(weeklyLimitMinutes)} tyg.
                    </span>
                  </td>
                  {codes.map((code) => (
                    <td key={code} className="text-center">
                      {row.shifts[code] ?? 0}
                    </td>
                  ))}
                  <td className="text-center">{row.saturdays}</td>
                  <td className="text-center">{row.sundays}</td>
                  <td className="text-center">{row.weekend_shifts}</td>
                  <td className="text-center">{row.holiday_shifts}</td>
                  <td className="text-center">{row.days_off}</td>
                  {onEmployeePdf && (
                    <td className="text-end">
                      <button
                        className="btn btn-sm btn-outline-secondary"
                        onClick={() => onEmployeePdf(row.employee_id)}
                        title="PDF pracownika"
                        type="button"
                      >
                        <i className="bi bi-file-earmark-pdf" />
                      </button>
                    </td>
                  )}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
