/**
 * RECZNE UKLADANIE - the manager builds the month by hand.
 *
 * Nothing is generated and nothing is blocked while working: every click is
 * saved as a draft. The rules are checked only when the manager presses
 * "Wyslij do sprawdzenia"; the errors to fix are then listed and highlighted.
 * Employees' requests are offered as suggestions that can be accepted with
 * one click (one by one or all at once) and changed again at any time.
 */
import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { ApiError } from '../api/client'
import {
  type CellChange,
  useApprove,
  useAvailability,
  useSchedule,
  useSetCells,
  useStartManual,
  useValidate,
} from '../api/hooks'
import ScheduleGrid, { type CellTarget } from '../components/ScheduleGrid'
import ValidationPanel from '../components/ValidationPanel'
import {
  EmptyState,
  ErrorBox,
  Loading,
  Modal,
  MonthPicker,
  PageHeader,
  StatusBadge,
} from '../components/common'
import { useToasts } from '../components/Toasts'
import { AVAILABILITY_LABEL, formatDate, monthLabel, shiftAllowedOn, todayParts } from '../lib'
import type {
  Assignment,
  Availability,
  DayInfo,
  Employee,
  ScheduleDetail,
  Shift,
} from '../types'

/** Request type -> the shift code it asks for. */
const PREFERENCE_SHIFT: Record<string, string> = {
  PREFERRED_DAY: 'D',
  PREFERRED_MORNING: 'R',
  PREFERRED_NIGHT: 'N',
}

const OFF = 'W'

interface Suggestion {
  key: string
  employee: Employee
  day: DayInfo
  request: Availability
  /** Shift to set, or null = make the day free. */
  target: string | null
  current: string | null
  text: string
}

/** Requests that the current draft does not honour yet, as one-click fixes. */
function buildSuggestions(data: ScheduleDetail, requests: Availability[]): Suggestion[] {
  const cells = new Map(data.assignments.map((a) => [`${a.employee_id}|${a.work_date}`, a]))
  const employees = new Map(data.employees.map((e) => [e.id, e]))
  const days = new Map(data.days.map((d) => [d.date, d]))
  const shifts = new Map(data.shifts.map((s) => [s.code, s]))
  const out: Suggestion[] = []

  for (const request of requests) {
    const employee = employees.get(request.employee_id)
    const day = days.get(request.date)
    if (!employee || !day || !employee.active) continue
    const key = `${employee.id}|${day.date}`
    const current = cells.get(key)?.shift_code ?? null
    const label = AVAILABILITY_LABEL[request.type] ?? request.type

    if (request.type === 'UNAVAILABLE' || request.type === 'PREFERRED_OFF') {
      if (current === null) continue
      out.push({
        key,
        employee,
        day,
        request,
        target: null,
        current,
        text:
          request.type === 'UNAVAILABLE'
            ? `zglosil(a) niedostepnosc, a ma ${current} - ustaw wolne`
            : `prosi o wolne, a ma ${current} - ustaw wolne`,
      })
      continue
    }

    const wanted = PREFERENCE_SHIFT[request.type]
    const shift = wanted ? shifts.get(wanted) : undefined
    if (!shift || current === wanted || !shiftAllowedOn(shift, day)) continue
    out.push({
      key,
      employee,
      day,
      request,
      target: wanted,
      current,
      text: `${label.toLowerCase()} - ustaw ${wanted}${current ? ` zamiast ${current}` : ''}`,
    })
  }
  return out.sort((a, b) => a.day.date.localeCompare(b.day.date))
}

export default function ManualPage() {
  const initial = todayParts()
  const [params] = useSearchParams()
  const [year, setYear] = useState(Number(params.get('year')) || initial.year)
  const [month, setMonth] = useState(Number(params.get('month')) || initial.month)
  const [brush, setBrush] = useState<string | null>(null)
  const [cell, setCell] = useState<CellTarget | null>(null)
  const [highlight, setHighlight] = useState<{ employeeId: number | null; date: string | null }>({
    employeeId: null,
    date: null,
  })
  const [checked, setChecked] = useState(false)

  const toasts = useToasts()
  const { data, isLoading, error } = useSchedule(year, month)
  const { data: availability } = useAvailability(null, year, month)
  const start = useStartManual()
  const setCells = useSetCells()
  const validate = useValidate()
  const approve = useApprove()

  const schedule = data?.schedule ?? null
  const manual = schedule?.mode === 'MANUAL'
  const locked = schedule?.status === 'APPROVED' || schedule?.status === 'ARCHIVED'
  const editable = manual && !locked
  const busy = setCells.isPending || validate.isPending || approve.isPending || start.isPending

  const requests = useMemo(
    () => (availability ?? []).filter((a) => a.type !== 'AVAILABLE'),
    [availability],
  )
  const suggestions = useMemo(
    () => (data && manual ? buildSuggestions(data, requests) : []),
    [data, manual, requests],
  )
  const ghosts = useMemo(() => {
    const map = new Map<string, string>()
    for (const s of suggestions) if (s.target && !s.current) map.set(s.key, s.target)
    return map
  }, [suggestions])

  function changeMonth(y: number, m: number) {
    setYear(y)
    setMonth(m)
    setChecked(false)
    setCell(null)
    setHighlight({ employeeId: null, date: null })
  }

  function save(cells: CellChange[], done?: string) {
    if (!schedule) return
    setCells.mutate(
      { id: schedule.id, cells },
      {
        onSuccess: () => {
          setChecked(false)
          setCell(null)
          if (done) toasts.success(done)
        },
        onError: (err) =>
          toasts.error(
            'Nie udalo sie zapisac',
            err instanceof ApiError ? err.message : 'Sprobuj ponownie.',
          ),
      },
    )
  }

  /** Front-end guard for the one rule that is known up front. */
  function blocked(code: string | null, day: DayInfo): boolean {
    const shift = data?.shifts.find((s) => s.code === code)
    if (shift && !shiftAllowedOn(shift, day)) {
      toasts.warning(
        `${shift.name} tylko w dni robocze`,
        `${formatDate(day.date)} to ${day.is_holiday ? `swieto (${day.holiday_name})` : 'weekend'}.`,
      )
      return true
    }
    return false
  }

  function onCellClick(target: CellTarget) {
    if (!editable) return
    if (brush === null) {
      setCell(target)
      return
    }
    const code = brush === OFF ? null : brush
    if ((target.assignment?.shift_code ?? null) === code) return
    if (blocked(code, target.day)) return
    save([{ employee_id: target.employee.id, date: target.day.date, shift_code: code }])
  }

  function onMove(assignment: Assignment, employee: Employee, day: DayInfo) {
    if (blocked(assignment.shift_code, day)) return
    save([
      { employee_id: assignment.employee_id, date: assignment.work_date, shift_code: null },
      { employee_id: employee.id, date: day.date, shift_code: assignment.shift_code },
    ])
  }

  function accept(items: Suggestion[]) {
    if (!items.length) return
    save(
      items.map((s) => ({ employee_id: s.employee.id, date: s.day.date, shift_code: s.target })),
      items.length === 1 ? 'Sugestia zaakceptowana' : `Zaakceptowano ${items.length} sugestii`,
    )
  }

  function sendForChecking() {
    if (!schedule) return
    validate.mutate(schedule.id, {
      onSuccess: (response) => {
        setChecked(true)
        const errors = response.validation.errors.length
        if (errors === 0) {
          toasts.success(
            'Grafik sprawdzony',
            'Wszystkie twarde reguly sa spelnione - mozesz go zatwierdzic.',
          )
        } else {
          toasts.warning(
            'Grafik wymaga poprawek',
            `Do poprawy: ${errors}. Kliknij blad w panelu kontroli, aby pokazac go w siatce.`,
          )
        }
      },
      onError: (err) =>
        toasts.error(
          'Nie udalo sie sprawdzic grafiku',
          err instanceof ApiError ? err.message : undefined,
        ),
    })
  }

  if (isLoading) return <Loading />
  if (error) return <ErrorBox error={error} />
  if (!data) return null

  const header = (
    <PageHeader
      title={`Reczne ukladanie - ${monthLabel(year, month)}`}
      subtitle={
        schedule ? (
          <span className="d-flex align-items-center gap-2">
            <StatusBadge status={schedule.status} />
            <span>wersja v{schedule.version}</span>
            <span>&middot; {data.assignments.length} zmian w grafiku</span>
          </span>
        ) : (
          'Ten miesiac nie ma jeszcze grafiku.'
        )
      }
      actions={
        <>
          <MonthPicker year={year} month={month} onChange={changeMonth} />
          {manual && (
            <>
              <button
                className="btn btn-primary"
                onClick={sendForChecking}
                disabled={busy || locked}
                type="button"
              >
                {validate.isPending ? (
                  <span className="spinner-border spinner-border-sm me-1" />
                ) : (
                  <i className="bi bi-send-check me-1" />
                )}
                Wyslij do sprawdzenia
              </button>
              {schedule?.status === 'VALID' && (
                <button
                  className="btn btn-success"
                  onClick={() =>
                    approve.mutate(
                      { id: schedule.id },
                      {
                        onSuccess: () => toasts.success('Grafik zatwierdzony'),
                        onError: (err) =>
                          toasts.error(
                            'Nie mozna zatwierdzic',
                            err instanceof ApiError ? err.message : undefined,
                            err instanceof ApiError ? err.violations.map((v) => v.message) : [],
                          ),
                      },
                    )
                  }
                  disabled={busy}
                  type="button"
                >
                  <i className="bi bi-check-lg me-1" /> Zatwierdz
                </button>
              )}
            </>
          )}
          <Link className="btn btn-outline-secondary" to={`/grafik?year=${year}&month=${month}`}>
            <i className="bi bi-calendar3 me-1" /> Widok grafiku
          </Link>
        </>
      }
    />
  )

  if (data.employees.length === 0) {
    return (
      <>
        {header}
        <EmptyState icon="bi-people" title="Brak aktywnych pracownikow">
          Dodaj pracownikow w panelu PRACOWNICY, aby moc ulozyc grafik.
        </EmptyState>
      </>
    )
  }

  if (!manual) {
    const hasRoster = data.assignments.length > 0
    return (
      <>
        {header}
        <div className="card shadow-sm">
          <div className="card-body">
            <h5 className="card-title">
              <i className="bi bi-pencil-square me-2" />
              Uloz grafik recznie
            </h5>
            <p className="mb-2">
              W tym trybie system <strong>nie generuje</strong> grafiku. Ukladasz go sam, klikajac
              w siatke - nic nie jest blokowane w trakcie pracy. Gdy skonczysz, wysylasz grafik do
              sprawdzenia i dostajesz liste rzeczy do poprawienia.
            </p>
            <p className="small text-secondary">
              Prosby pracownikow (preferowane zmiany, wolne, niedostepnosc) pojawiaja sie jako
              sugestie - mozesz je zaakceptowac jednym kliknieciem i zmienic pozniej.
            </p>
            {locked ? (
              <div className="alert alert-dark py-2 small mb-0">
                <i className="bi bi-lock me-1" />
                Grafik jest zatwierdzony. Cofnij zatwierdzenie w widoku grafiku, aby go zmieniac.
              </div>
            ) : (
              <button
                className="btn btn-primary"
                onClick={() =>
                  start.mutate(
                    { year, month },
                    {
                      onError: (err) =>
                        toasts.error(
                          'Nie udalo sie rozpoczac',
                          err instanceof ApiError ? err.message : undefined,
                        ),
                    },
                  )
                }
                disabled={busy}
                type="button"
              >
                <i className="bi bi-pencil me-1" />
                {hasRoster
                  ? `Ukladaj recznie, zaczynajac od obecnego grafiku (${data.assignments.length} zmian)`
                  : 'Rozpocznij reczne ukladanie'}
              </button>
            )}
          </div>
        </div>
      </>
    )
  }

  const showValidation = checked || schedule?.status === 'VALID' || schedule?.status === 'INVALID'
  const validation = showValidation ? data.validation : null
  const errorCount = validation?.errors.length ?? 0

  return (
    <>
      {header}

      {locked ? (
        <div className="alert alert-dark py-2" role="alert">
          <i className="bi bi-lock me-2" />
          Grafik jest zatwierdzony. Aby go zmienic, cofnij zatwierdzenie w widoku grafiku.
        </div>
      ) : schedule?.status === 'DRAFT' ? (
        <div className="alert alert-info py-2 small" role="alert">
          <i className="bi bi-info-circle me-2" />
          Ukladasz grafik recznie - zmiany zapisuja sie od razu jako szkic i nie sa sprawdzane w
          trakcie. Gdy skonczysz, kliknij <strong>Wyslij do sprawdzenia</strong>.
        </div>
      ) : schedule?.status === 'INVALID' ? (
        <div className="alert alert-warning py-2" role="alert">
          <i className="bi bi-exclamation-triangle me-2" />
          Do poprawy: <strong>{errorCount}</strong>. Kliknij blad w panelu kontroli, aby zaznaczyc
          go w siatce, popraw i wyslij grafik ponownie.
        </div>
      ) : schedule?.status === 'VALID' ? (
        <div className="alert alert-success py-2" role="alert">
          <i className="bi bi-check-circle me-2" />
          Grafik spelnia wszystkie twarde reguly. Mozesz go zatwierdzic albo dalej poprawiac.
        </div>
      ) : null}

      {editable && (
        <div className="d-flex flex-wrap align-items-center gap-2 mb-2">
          <span className="small text-secondary me-1">Pedzel:</span>
          <button
            className={`btn btn-sm brush-btn ${brush === null ? 'btn-dark active' : 'btn-outline-dark'}`}
            onClick={() => setBrush(null)}
            type="button"
            title="Klikniecie komorki otwiera okno wyboru"
          >
            <i className="bi bi-hand-index me-1" /> Wybor
          </button>
          {data.shifts.map((shift: Shift) => (
            <button
              key={shift.code}
              className={`btn btn-sm brush-btn shift-${shift.code} ${brush === shift.code ? 'active' : ''}`}
              onClick={() => setBrush(shift.code)}
              type="button"
              title={`${shift.name} ${shift.start_time.slice(0, 5)}-${shift.end_time.slice(0, 5)}`}
            >
              <strong>{shift.code}</strong> {shift.name}
            </button>
          ))}
          <button
            className={`btn btn-sm brush-btn shift-${OFF} ${brush === OFF ? 'active' : ''}`}
            onClick={() => setBrush(OFF)}
            type="button"
          >
            <strong>W</strong> wolne
          </button>
          <span className="small text-secondary ms-2">
            {brush === null
              ? 'Kliknij komorke, aby wybrac zmiane.'
              : `Kazde klikniecie wpisuje ${brush}. Mozesz tez przeciagac zmiany.`}
          </span>
        </div>
      )}

      <ScheduleGrid
        days={data.days}
        employees={data.employees}
        shifts={data.shifts}
        assignments={data.assignments}
        availability={availability ?? []}
        editable={editable && !busy}
        onCellClick={onCellClick}
        onMove={onMove}
        highlight={highlight}
        ghosts={editable ? ghosts : undefined}
      />
      <div className="small text-secondary mt-1 mb-3">
        <span className="me-3">
          <span className="legend-swatch preferred-dot" /> kropka = prosba pracownika (najedz, aby
          zobaczyc)
        </span>
        <span className="me-3">polprzezroczysta zmiana = sugestia z prosby</span>
        <span>Ranek (R) tylko w dni robocze - nie w weekendy i swieta.</span>
      </div>

      <div className="row g-3">
        <div className="col-12 col-xl-5">
          <div className="card shadow-sm h-100">
            <div className="card-header bg-white fw-semibold d-flex justify-content-between align-items-center">
              <span>
                <i className="bi bi-lightbulb me-1" />
                Sugestie z prosb ({suggestions.length})
              </span>
              {editable && suggestions.length > 1 && (
                <button
                  className="btn btn-sm btn-outline-success"
                  onClick={() => accept(suggestions)}
                  disabled={busy}
                  type="button"
                >
                  Akceptuj wszystkie
                </button>
              )}
            </div>
            {suggestions.length === 0 ? (
              <div className="card-body small text-secondary">
                Wszystkie prosby pracownikow sa uwzglednione w grafiku.
              </div>
            ) : (
              <ul className="list-group list-group-flush suggestion-list">
                {suggestions.map((s) => (
                  <li
                    key={s.key}
                    className="list-group-item d-flex justify-content-between align-items-center gap-2"
                    onMouseEnter={() => setHighlight({ employeeId: s.employee.id, date: s.day.date })}
                  >
                    <div className="small">
                      <div className="fw-semibold">
                        {s.employee.full_name} &middot; {formatDate(s.day.date)}
                      </div>
                      <div className="text-secondary">
                        {s.text}
                        {s.request.note ? ` (${s.request.note})` : ''}
                      </div>
                    </div>
                    {editable && (
                      <button
                        className="btn btn-sm btn-outline-primary text-nowrap"
                        onClick={() => accept([s])}
                        disabled={busy}
                        type="button"
                      >
                        Akceptuj
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
        <div className="col-12 col-xl-7">
          {validation ? (
            <ValidationPanel
              validation={validation}
              onLocate={(violation) =>
                setHighlight({ employeeId: violation.employee_id, date: violation.date })
              }
            />
          ) : (
            <div className="card shadow-sm h-100">
              <div className="card-header bg-white fw-semibold">Kontrola grafiku</div>
              <div className="card-body small text-secondary">
                Reguly zostana sprawdzone po kliknieciu <strong>Wyslij do sprawdzenia</strong>.
                Zobaczysz tu liste rzeczy do poprawienia.
              </div>
            </div>
          )}
        </div>
      </div>

      {cell && (
        <CellModal
          target={cell}
          shifts={data.shifts}
          request={requests.find(
            (r) => r.employee_id === cell.employee.id && r.date === cell.day.date,
          )}
          suggestion={suggestions.find((s) => s.key === `${cell.employee.id}|${cell.day.date}`)}
          busy={busy}
          onClose={() => setCell(null)}
          onPick={(code) => {
            if (blocked(code, cell.day)) return
            save([{ employee_id: cell.employee.id, date: cell.day.date, shift_code: code }])
          }}
          onAccept={(s) => accept([s])}
        />
      )}
    </>
  )
}

function CellModal({
  target,
  shifts,
  request,
  suggestion,
  busy,
  onClose,
  onPick,
  onAccept,
}: {
  target: CellTarget
  shifts: Shift[]
  request: Availability | undefined
  suggestion: Suggestion | undefined
  busy: boolean
  onClose: () => void
  onPick: (code: string | null) => void
  onAccept: (s: Suggestion) => void
}) {
  const current = target.assignment?.shift_code ?? null
  return (
    <Modal
      title={`${target.employee.full_name} - ${formatDate(target.day.date)}`}
      onClose={onClose}
      footer={
        <button className="btn btn-outline-secondary" onClick={onClose} type="button">
          Zamknij
        </button>
      }
    >
      {target.day.is_holiday && (
        <div className="alert alert-warning py-2 small">
          <i className="bi bi-stars me-1" />
          {target.day.holiday_name}
        </div>
      )}
      {request && (
        <div className="alert alert-light border py-2 small d-flex justify-content-between align-items-center gap-2">
          <span>
            <i className="bi bi-chat-left-text me-1" />
            Prosba: <strong>{AVAILABILITY_LABEL[request.type] ?? request.type}</strong>
            {request.note ? ` - ${request.note}` : ''}
          </span>
          {suggestion && (
            <button
              className="btn btn-sm btn-success text-nowrap"
              onClick={() => onAccept(suggestion)}
              disabled={busy}
              type="button"
            >
              Akceptuj sugestie
            </button>
          )}
        </div>
      )}
      <div className="d-grid gap-2">
        {shifts.map((shift) => {
          const allowed = shiftAllowedOn(shift, target.day)
          return (
            <button
              key={shift.code}
              className={`btn ${current === shift.code ? 'btn-primary' : 'btn-outline-primary'} text-start`}
              onClick={() => onPick(shift.code)}
              disabled={busy || !allowed}
              title={allowed ? undefined : 'Tylko w dni robocze'}
              type="button"
            >
              <strong className="me-2">{shift.code}</strong>
              {shift.name} ({shift.start_time.slice(0, 5)}-{shift.end_time.slice(0, 5)})
              {!allowed && <span className="small ms-2">- nie w weekend / swieto</span>}
            </button>
          )
        })}
        <button
          className={`btn ${current === null ? 'btn-secondary' : 'btn-outline-secondary'} text-start`}
          onClick={() => onPick(null)}
          disabled={busy}
          type="button"
        >
          <strong className="me-2">W</strong>
          Wolne
        </button>
      </div>
    </Modal>
  )
}
