import { useMemo, useState } from 'react'

import dayGridPlugin from '@fullcalendar/daygrid'
import interactionPlugin from '@fullcalendar/interaction'
import FullCalendar from '@fullcalendar/react'

import {
  useAvailability,
  useDeleteAvailability,
  useEmployees,
  useHolidays,
  useSetAvailabilityBulk,
} from '../api/hooks'
import { ColorDot, ErrorBox, Loading, MonthPicker, PageHeader } from '../components/common'
import { useToasts } from '../components/Toasts'
import { AVAILABILITY_LABEL, formatDate, monthLabel, todayParts } from '../lib'
import type { AvailabilityType } from '../types'

const TYPES: AvailabilityType[] = [
  'UNAVAILABLE',
  'PREFERRED_OFF',
  'PREFERRED_DAY',
  'PREFERRED_MORNING',
  'PREFERRED_NIGHT',
]

const TYPE_COLOR: Record<AvailabilityType, string> = {
  AVAILABLE: '#adb5bd',
  UNAVAILABLE: '#dc3545',
  PREFERRED_OFF: '#fd7e14',
  PREFERRED_DAY: '#0d6efd',
  PREFERRED_MORNING: '#198754',
  PREFERRED_NIGHT: '#6f42c1',
}

export default function AvailabilityPage() {
  const initial = todayParts()
  const [year, setYear] = useState(initial.year)
  const [month, setMonth] = useState(initial.month)
  const [employeeId, setEmployeeId] = useState<number | null>(null)
  const [selected, setSelected] = useState<string[]>([])
  const [type, setType] = useState<AvailabilityType>('UNAVAILABLE')

  const toasts = useToasts()
  const { data: employees, isLoading, error } = useEmployees()
  const { data: entries } = useAvailability(employeeId, year, month)
  const { data: holidays } = useHolidays(year)
  const saveBulk = useSetAvailabilityBulk()
  const remove = useDeleteAvailability()

  const active = useMemo(() => (employees ?? []).filter((e) => e.active), [employees])
  const currentId = employeeId ?? active[0]?.id ?? null
  const current = active.find((e) => e.id === currentId) ?? null

  const events = useMemo(() => {
    const own = (entries ?? []).filter((entry) => entry.employee_id === currentId)
    const availabilityEvents = own.map((entry) => ({
      id: String(entry.id),
      title: AVAILABILITY_LABEL[entry.type],
      start: entry.date,
      allDay: true,
      backgroundColor: TYPE_COLOR[entry.type],
      borderColor: TYPE_COLOR[entry.type],
      extendedProps: { availabilityId: entry.id },
    }))
    const holidayEvents = (holidays ?? []).map((holiday) => ({
      id: `h-${holiday.id}`,
      title: holiday.name,
      start: holiday.date,
      allDay: true,
      display: 'background' as const,
      backgroundColor: '#fde2e4',
    }))
    return [...holidayEvents, ...availabilityEvents]
  }, [entries, holidays, currentId])

  if (isLoading) return <Loading />
  if (error) return <ErrorBox error={error} />

  const apply = () => {
    if (!currentId || selected.length === 0) return
    saveBulk.mutate(
      { employee_id: currentId, dates: selected, type },
      {
        onSuccess: () => {
          toasts.success('Zapisano', `${selected.length} dni: ${AVAILABILITY_LABEL[type]}`)
          setSelected([])
        },
        onError: (err) => toasts.error('Nie zapisano', (err as Error).message),
      },
    )
  }

  return (
    <>
      <PageHeader
        title="Dostepnosc i preferencje"
        subtitle="Niedostepnosc jest twardym ograniczeniem. Pozostale typy sa preferencjami (miekkimi)."
        actions={
          <MonthPicker
            year={year}
            month={month}
            onChange={(y, m) => {
              setYear(y)
              setMonth(m)
              setSelected([])
            }}
          />
        }
      />

      <div className="row g-3">
        <div className="col-12 col-lg-4">
          <div className="card shadow-sm mb-3">
            <div className="card-header bg-white fw-semibold">Pracownik</div>
            <div className="card-body">
              <select
                className="form-select"
                value={currentId ?? ''}
                onChange={(e) => {
                  setEmployeeId(Number(e.target.value))
                  setSelected([])
                }}
              >
                {active.map((employee) => (
                  <option key={employee.id} value={employee.id}>
                    {employee.last_name} {employee.first_name}
                  </option>
                ))}
              </select>
              {current && (
                <div className="d-flex align-items-center gap-2 mt-2 small text-secondary">
                  <ColorDot color={current.color} />
                  staz: {current.seniority_label}
                </div>
              )}
            </div>
          </div>

          <div className="card shadow-sm mb-3">
            <div className="card-header bg-white fw-semibold">
              Zaznaczone dni ({selected.length})
            </div>
            <div className="card-body">
              <label className="form-label small">Typ zgloszenia</label>
              <select
                className="form-select mb-2"
                value={type}
                onChange={(e) => setType(e.target.value as AvailabilityType)}
              >
                {TYPES.map((value) => (
                  <option key={value} value={value}>
                    {AVAILABILITY_LABEL[value]}
                  </option>
                ))}
              </select>
              <div className="d-grid gap-2">
                <button
                  className="btn btn-primary"
                  onClick={apply}
                  disabled={selected.length === 0 || saveBulk.isPending}
                  type="button"
                >
                  <i className="bi bi-check2 me-1" /> Zapisz dla zaznaczonych
                </button>
                <button
                  className="btn btn-outline-secondary"
                  onClick={() => setSelected([])}
                  disabled={selected.length === 0}
                  type="button"
                >
                  Wyczysc zaznaczenie
                </button>
              </div>
              <p className="small text-secondary mt-2 mb-0">
                Kliknij dni w kalendarzu lub przeciagnij, aby zaznaczyc zakres.
              </p>
            </div>
          </div>

          <div className="card shadow-sm">
            <div className="card-header bg-white fw-semibold">
              Zgloszenia - {monthLabel(year, month)}
            </div>
            <ul className="list-group list-group-flush" style={{ maxHeight: 320, overflowY: 'auto' }}>
              {(entries ?? [])
                .filter((entry) => entry.employee_id === currentId)
                .map((entry) => (
                  <li
                    key={entry.id}
                    className="list-group-item d-flex justify-content-between align-items-center py-2"
                  >
                    <span className="small">
                      <span
                        className="color-dot me-2"
                        style={{ background: TYPE_COLOR[entry.type] }}
                      />
                      {formatDate(entry.date)} - {AVAILABILITY_LABEL[entry.type]}
                    </span>
                    <button
                      className="btn btn-sm btn-outline-danger"
                      onClick={() =>
                        remove.mutate(entry.id, {
                          onSuccess: () => toasts.success('Usunieto zgloszenie'),
                        })
                      }
                      type="button"
                    >
                      <i className="bi bi-trash" />
                    </button>
                  </li>
                ))}
              {(entries ?? []).filter((entry) => entry.employee_id === currentId).length === 0 && (
                <li className="list-group-item text-secondary small">Brak zgloszen.</li>
              )}
            </ul>
          </div>
        </div>

        <div className="col-12 col-lg-8">
          <div className="card shadow-sm availability-calendar">
            <div className="card-body">
              <FullCalendar
                plugins={[dayGridPlugin, interactionPlugin]}
                initialView="dayGridMonth"
                locale="pl"
                firstDay={1}
                height="auto"
                headerToolbar={false}
                initialDate={`${year}-${String(month).padStart(2, '0')}-01`}
                key={`${year}-${month}`}
                events={events}
                selectable
                selectMirror={false}
                dayCellClassNames={(arg) =>
                  selected.includes(toIso(arg.date)) ? ['selected-day'] : []
                }
                select={(info) => {
                  const days: string[] = []
                  const cursor = new Date(info.start)
                  while (cursor < info.end) {
                    days.push(toIso(cursor))
                    cursor.setDate(cursor.getDate() + 1)
                  }
                  setSelected((current) => {
                    const set = new Set(current)
                    const allSelected = days.every((day) => set.has(day))
                    days.forEach((day) => (allSelected ? set.delete(day) : set.add(day)))
                    return [...set].sort()
                  })
                }}
                eventClick={(info) => {
                  const id = info.event.extendedProps.availabilityId as number | undefined
                  if (id) {
                    remove.mutate(id, { onSuccess: () => toasts.success('Usunieto zgloszenie') })
                  }
                }}
              />
            </div>
          </div>
        </div>
      </div>
    </>
  )
}

/** Local (not UTC) ISO date - FullCalendar hands us local Date objects. */
function toIso(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}
