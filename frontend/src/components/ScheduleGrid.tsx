/**
 * The month grid: employees x days.
 *
 * Drag & drop moves a shift between days/employees; every drop goes through
 * the backend, which re-validates and refuses anything that would break a
 * hard constraint. Nothing is changed optimistically, so a refused move
 * simply leaves the grid as it was.
 */
import { useMemo, useState } from 'react'

import { AVAILABILITY_LABEL, WEEKDAYS_PL, formatMinutes, shiftAllowedOn } from '../lib'
import type { Assignment, Availability, DayInfo, Employee, Shift } from '../types'


export interface CellTarget {
  employee: Employee
  day: DayInfo
  assignment: Assignment | null
}

interface Props {
  days: DayInfo[]
  employees: Employee[]
  shifts: Shift[]
  assignments: Assignment[]
  availability: Availability[]
  editable: boolean
  onCellClick: (target: CellTarget) => void
  onMove: (assignment: Assignment, employee: Employee, day: DayInfo) => void
  highlight?: { employeeId: number | null; date: string | null }
  /** Suggested shift per empty cell (`employeeId|date` -> code), shown faded. */
  ghosts?: Map<string, string>
}

const OFF = 'W'

export default function ScheduleGrid({
  days,
  employees,
  shifts,
  assignments,
  availability,
  editable,
  onCellClick,
  onMove,
  highlight,
  ghosts,
}: Props) {
  const today = useMemo(() => {
    const now = new Date()
    const pad = (value: number) => String(value).padStart(2, '0')
    return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
  }, [])
  const [dragged, setDragged] = useState<Assignment | null>(null)
  const [over, setOver] = useState<string | null>(null)

  const byCell = useMemo(() => {
    const map = new Map<string, Assignment>()
    for (const a of assignments) map.set(`${a.employee_id}|${a.work_date}`, a)
    return map
  }, [assignments])

  const availabilityByCell = useMemo(() => {
    const map = new Map<string, Availability>()
    for (const a of availability) map.set(`${a.employee_id}|${a.date}`, a)
    return map
  }, [availability])

  const minutesByShift = useMemo(() => {
    const map = new Map<string, number>()
    for (const s of shifts) map.set(s.code, s.duration_minutes)
    return map
  }, [shifts])

  const { coverage, nurseCoverage } = useMemo(() => {
    const nurses = new Set(employees.filter((e) => e.role === 'NURSE').map((e) => e.id))
    const all = new Map<string, number>()
    const onlyNurses = new Map<string, number>()
    for (const a of assignments) {
      const key = `${a.work_date}|${a.shift_code}`
      all.set(key, (all.get(key) ?? 0) + 1)
      if (nurses.has(a.employee_id)) onlyNurses.set(key, (onlyNurses.get(key) ?? 0) + 1)
    }
    return { coverage: all, nurseCoverage: onlyNurses }
  }, [assignments, employees])

  return (
    <div className="schedule-scroll">
      <table className="schedule-table w-100">
        <thead>
          <tr>
            <th className="name-cell">Pracownik</th>
            {days.map((day) => (
              <th
                key={day.date}
                className={
                  [
                    day.is_holiday ? 'holiday' : day.is_weekend ? 'weekend' : '',
                    day.date === today ? 'today' : '',
                  ]
                    .filter(Boolean)
                    .join(' ') || undefined
                }
                title={day.holiday_name ?? (day.date === today ? 'Dziś' : undefined)}
              >
                <div className="day-num">{Number(day.date.slice(8, 10))}</div>
                <div className="day-name">{WEEKDAYS_PL[day.weekday]}</div>
              </th>
            ))}
            <th style={{ minWidth: 60 }}>Godz.</th>
          </tr>
        </thead>
        <tbody>
          {employees.map((employee) => {
            let minutes = 0
            return (
              <tr key={employee.id}>
                <td className="name-cell">
                  <span className={`color-bar color-${employee.color}`} />
                  <span title={`${employee.full_name} - staż ${employee.seniority_label}`}>
                    {employee.last_name} {employee.first_name}
                  </span>
                  {!employee.active && (
                    <span className="badge text-bg-secondary ms-1">nieaktywny</span>
                  )}
                </td>

                {days.map((day) => {
                  const key = `${employee.id}|${day.date}`
                  const assignment = byCell.get(key) ?? null
                  const declared = availabilityByCell.get(key)
                  if (assignment) minutes += minutesByShift.get(assignment.shift_code) ?? 0

                  const classes = ['day-cell']
                  if (day.is_holiday) classes.push('holiday')
                  else if (day.is_weekend) classes.push('weekend')
                  if (declared?.type === 'UNAVAILABLE') classes.push('unavailable-cell')
                  else if (declared && declared.type !== 'AVAILABLE') classes.push('preferred-cell')
                  if (over === key) classes.push('drag-over')
                  if (dragged?.id === assignment?.id && dragged) classes.push('dragging')
                  if (
                    highlight?.date === day.date &&
                    (highlight.employeeId === null || highlight.employeeId === employee.id)
                  ) {
                    classes.push('table-warning')
                  }

                  const title = [
                    `${employee.full_name} - ${day.date}`,
                    day.holiday_name ? `Święto: ${day.holiday_name}` : null,
                    declared && declared.type !== 'AVAILABLE'
                      ? `Prośba: ${AVAILABILITY_LABEL[declared.type] ?? declared.type}${
                          declared.note ? ` (${declared.note})` : ''
                        }`
                      : null,
                    !assignment && ghosts?.get(key) ? `Sugestia: ${ghosts.get(key)}` : null,
                    assignment?.manually_modified ? 'Zmiana edytowana ręcznie' : null,
                  ]
                    .filter(Boolean)
                    .join('\n')

                  return (
                    <td
                      key={day.date}
                      className={classes.join(' ')}
                      title={title}
                      onClick={() => onCellClick({ employee, day, assignment })}
                      onDragOver={(event) => {
                        if (!editable || !dragged) return
                        event.preventDefault()
                        setOver(key)
                      }}
                      onDragLeave={() => setOver((current) => (current === key ? null : current))}
                      onDrop={(event) => {
                        event.preventDefault()
                        setOver(null)
                        if (!editable || !dragged) return
                        if (
                          dragged.employee_id === employee.id &&
                          dragged.work_date === day.date
                        ) {
                          return
                        }
                        onMove(dragged, employee, day)
                        setDragged(null)
                      }}
                    >
                      {assignment ? (
                        <span
                          className={`shift-chip shift-${assignment.shift_code} ${
                            assignment.manually_modified ? 'manual' : ''
                          }`}
                          draggable={editable}
                          onDragStart={(event) => {
                            if (!editable) return
                            setDragged(assignment)
                            event.dataTransfer.effectAllowed = 'move'
                            event.dataTransfer.setData('text/plain', String(assignment.id))
                          }}
                          onDragEnd={() => {
                            setDragged(null)
                            setOver(null)
                          }}
                        >
                          {assignment.shift_code}
                        </span>
                      ) : ghosts?.get(key) ? (
                        <span className={`shift-chip shift-${ghosts.get(key)} ghost`}>
                          {ghosts.get(key)}
                        </span>
                      ) : (
                        <span className={`shift-chip shift-${OFF}`}>{OFF}</span>
                      )}
                    </td>
                  )
                })}

                <td className="fw-semibold px-2">{formatMinutes(minutes)}</td>
              </tr>
            )
          })}

          {shifts.map((shift, index) => (
            <tr className={`coverage-row${index === 0 ? ' first' : ''}`} key={`coverage-${shift.code}`}>
              <td className="name-cell">
                Obsada {shift.code}{' '}
                <span className="text-secondary">
                  (min {shift.minimum_staff}
                  {shift.minimum_nurses > 0 && `, w tym ${shift.minimum_nurses} piel.`})
                </span>
              </td>
              {days.map((day) => {
                if (!shiftAllowedOn(shift, day)) {
                  return (
                    <td key={day.date} title={`${shift.name}: tylko w dni robocze`}>
                      -
                    </td>
                  )
                }
                const key = `${day.date}|${shift.code}`
                const count = coverage.get(key) ?? 0
                const nurses = nurseCoverage.get(key) ?? 0
                const short =
                  count < shift.minimum_staff || nurses < (shift.minimum_nurses ?? 0)
                return (
                  <td
                    key={day.date}
                    className={short ? 'short' : undefined}
                    title={`${count} os., w tym ${nurses} pielęgniarek`}
                  >
                    {count}
                    {shift.minimum_nurses > 0 && (
                      <div className="coverage-nurses">{nurses}P</div>
                    )}
                  </td>
                )
              })}
              <td />
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
