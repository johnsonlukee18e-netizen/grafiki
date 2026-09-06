import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { ApiError, downloadFile } from '../api/client'
import {
  useApprove,
  useAvailability,
  useCreateAssignment,
  useDeleteAssignment,
  useGenerate,
  useSchedule,
  useSettings,
  useUpdateAssignment,
  useValidate,
} from '../api/hooks'
import ScheduleGrid, { type CellTarget } from '../components/ScheduleGrid'
import StatisticsPanel from '../components/StatisticsPanel'
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
import { formatDate, monthLabel, todayParts } from '../lib'
import type { Assignment, DayInfo, Employee, SolverResult, Violation } from '../types'

export default function SchedulePage() {
  const initial = todayParts()
  const [params, setParams] = useSearchParams()
  const [year, setYear] = useState(Number(params.get('year')) || initial.year)
  const [month, setMonth] = useState(Number(params.get('month')) || initial.month)
  const [cell, setCell] = useState<CellTarget | null>(null)
  const [solverReport, setSolverReport] = useState<SolverResult | null>(null)
  const [highlight, setHighlight] = useState<{ employeeId: number | null; date: string | null }>({
    employeeId: null,
    date: null,
  })

  const toasts = useToasts()
  const { data, isLoading, error } = useSchedule(year, month)
  const { data: availability } = useAvailability(null, year, month)
  const { data: settings } = useSettings()

  const generate = useGenerate()
  const validate = useValidate()
  const approve = useApprove()
  const createAssignment = useCreateAssignment()
  const updateAssignment = useUpdateAssignment()
  const deleteAssignment = useDeleteAssignment()

  const schedule = data?.schedule ?? null
  const editable = Boolean(schedule) && schedule?.status !== 'APPROVED' && schedule?.status !== 'ARCHIVED'
  const busy =
    generate.isPending ||
    validate.isPending ||
    approve.isPending ||
    createAssignment.isPending ||
    updateAssignment.isPending ||
    deleteAssignment.isPending

  useEffect(() => {
    if (params.get('generate') === '1' && !generate.isPending) {
      params.delete('generate')
      setParams(params, { replace: true })
      runGenerate()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params])

  const validation = data?.validation ?? null

  function reportBlocked(err: unknown, fallback: string) {
    if (err instanceof ApiError) {
      const violations = err.violations
      toasts.error(
        'Nie mozna wykonac operacji',
        err.message,
        violations.map((v) => v.message),
      )
      return
    }
    toasts.error('Blad', fallback)
  }

  function runGenerate() {
    generate.mutate(
      { year, month },
      {
        onSuccess: (response) => {
          setSolverReport(response.solver)
          if (response.success) {
            const valid = response.validation?.valid
            toasts.success(
              'Grafik wygenerowany',
              `${response.solver.message} Walidacja: ${valid ? 'bez bledow' : 'wykryto bledy'}.`,
            )
          }
        },
        onError: (err) => reportBlocked(err, 'Nie udalo sie wygenerowac grafiku.'),
      },
    )
  }

  function handleMove(assignment: Assignment, employee: Employee, day: DayInfo) {
    updateAssignment.mutate(
      { id: assignment.id, employee_id: employee.id, work_date: day.date },
      {
        onSuccess: (response) => {
          if (response.new_warnings.length) {
            toasts.warning(
              'Zmiana zapisana z ostrzezeniem',
              'Twarde ograniczenia sa spelnione, ale pogorszyly sie preferencje:',
              response.new_warnings.map((w) => w.message),
            )
          } else {
            toasts.success('Zmiana przeniesiona', `${employee.full_name}, ${formatDate(day.date)}`)
          }
        },
        onError: (err) => reportBlocked(err, 'Nie udalo sie przeniesc zmiany.'),
      },
    )
  }

  function setShift(code: string | null) {
    if (!cell || !schedule) return
    const { employee, day, assignment } = cell
    const done = () => setCell(null)

    const onSuccess = (response: { new_warnings: Violation[] }) => {
      done()
      if (response.new_warnings.length) {
        toasts.warning(
          'Zapisano z ostrzezeniem',
          'Operacja jest dozwolona, ale pogarsza miekkie kryteria:',
          response.new_warnings.map((w) => w.message),
        )
      } else {
        toasts.success('Grafik zaktualizowany')
      }
    }
    const onError = (err: unknown) => reportBlocked(err, 'Operacja nie powiodla sie.')

    if (code === null) {
      if (!assignment) return done()
      deleteAssignment.mutate(assignment.id, { onSuccess, onError })
      return
    }
    if (assignment) {
      updateAssignment.mutate({ id: assignment.id, shift_code: code }, { onSuccess, onError })
      return
    }
    createAssignment.mutate(
      {
        schedule_id: schedule.id,
        employee_id: employee.id,
        work_date: day.date,
        shift_code: code,
      },
      { onSuccess, onError },
    )
  }

  const legend = useMemo(() => data?.shifts ?? [], [data])

  if (isLoading) return <Loading />
  if (error) return <ErrorBox error={error} />
  if (!data) return null

  return (
    <>
      <PageHeader
        title={`Grafik - ${monthLabel(year, month)}`}
        subtitle={
          schedule ? (
            <span className="d-flex align-items-center gap-2">
              <StatusBadge status={schedule.status} />
              <span>wersja v{schedule.version}</span>
              {schedule.solver_status && <span>&middot; solver: {schedule.solver_status}</span>}
            </span>
          ) : (
            'Ten miesiac nie ma jeszcze grafiku.'
          )
        }
        actions={
          <>
            <MonthPicker
              year={year}
              month={month}
              onChange={(y, m) => {
                setYear(y)
                setMonth(m)
                setHighlight({ employeeId: null, date: null })
              }}
            />
            <button className="btn btn-primary" onClick={runGenerate} disabled={busy} type="button">
              {generate.isPending ? (
                <span className="spinner-border spinner-border-sm me-1" />
              ) : (
                <i className="bi bi-cpu me-1" />
              )}
              Generuj grafik
            </button>
            {schedule && (
              <>
                <button
                  className="btn btn-outline-secondary"
                  onClick={() =>
                    validate.mutate(schedule.id, {
                      onSuccess: (response) =>
                        toasts.success(
                          'Walidacja zakonczona',
                          response.validation.valid
                            ? 'Grafik spelnia wszystkie twarde ograniczenia.'
                            : `Wykryto ${response.validation.errors.length} bledow.`,
                        ),
                    })
                  }
                  disabled={busy}
                  type="button"
                >
                  <i className="bi bi-check2-square me-1" /> Waliduj
                </button>
                {schedule.status === 'APPROVED' ? (
                  <button
                    className="btn btn-outline-warning"
                    onClick={() =>
                      approve.mutate(
                        { id: schedule.id, undo: true },
                        { onSuccess: () => toasts.success('Cofnieto zatwierdzenie') },
                      )
                    }
                    disabled={busy}
                    type="button"
                  >
                    <i className="bi bi-unlock me-1" /> Cofnij zatwierdzenie
                  </button>
                ) : (
                  <button
                    className="btn btn-success"
                    onClick={() =>
                      approve.mutate(
                        { id: schedule.id },
                        {
                          onSuccess: () => toasts.success('Grafik zatwierdzony'),
                          onError: (err) =>
                            reportBlocked(err, 'Nie udalo sie zatwierdzic grafiku.'),
                        },
                      )
                    }
                    disabled={busy}
                    type="button"
                  >
                    <i className="bi bi-check-lg me-1" /> Zatwierdz
                  </button>
                )}
                <button
                  className="btn btn-outline-dark"
                  onClick={() =>
                    downloadFile(
                      `/api/schedules/${schedule.id}/pdf`,
                      `grafik_${year}_${String(month).padStart(2, '0')}.pdf`,
                    ).catch(() => toasts.error('Blad', 'Nie udalo sie pobrac PDF.'))
                  }
                  type="button"
                >
                  <i className="bi bi-file-earmark-pdf me-1" /> Eksport PDF
                </button>
              </>
            )}
          </>
        }
      />

      {solverReport && !solverReport.success && (
        <div className="alert alert-danger" role="alert">
          <h6 className="alert-heading">
            <i className="bi bi-exclamation-octagon me-2" />
            {solverReport.message}
          </h6>
          {solverReport.diagnostics.length > 0 && (
            <>
              <div className="fw-semibold small mt-2">Mozliwe przyczyny:</div>
              <ul className="mb-2 small">
                {solverReport.diagnostics.slice(0, 8).map((item, index) => (
                  <li key={index}>{item.message}</li>
                ))}
              </ul>
            </>
          )}
          {solverReport.suggestions.length > 0 && (
            <>
              <div className="fw-semibold small">Sugestie:</div>
              <ul className="mb-0 small">
                {solverReport.suggestions.map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
            </>
          )}
          <button
            className="btn btn-sm btn-outline-danger mt-2"
            onClick={() => setSolverReport(null)}
            type="button"
          >
            Zamknij
          </button>
        </div>
      )}

      {solverReport?.success && !solverReport.is_optimal && (
        <div className="alert alert-info d-flex justify-content-between align-items-start" role="alert">
          <div>
            <i className="bi bi-info-circle me-2" />
            {solverReport.message}
          </div>
          <button className="btn-close" onClick={() => setSolverReport(null)} type="button" />
        </div>
      )}

      {schedule?.status === 'APPROVED' && (
        <div className="alert alert-dark py-2" role="alert">
          <i className="bi bi-lock me-2" />
          Grafik jest zatwierdzony i zablokowany do edycji. Aby wprowadzic zmiany, cofnij
          zatwierdzenie.
        </div>
      )}

      {data.employees.length === 0 ? (
        <EmptyState icon="bi-people" title="Brak aktywnych pracownikow">
          Dodaj pracownikow w panelu PRACOWNICY, aby moc wygenerowac grafik.
        </EmptyState>
      ) : (
        <>
          <ScheduleGrid
            days={data.days}
            employees={data.employees}
            shifts={data.shifts}
            assignments={data.assignments}
            availability={availability ?? []}
            editable={editable && !busy}
            onCellClick={(target) => editable && setCell(target)}
            onMove={handleMove}
            highlight={highlight}
          />

          <div className="d-flex flex-wrap gap-3 small text-secondary mt-2 mb-4">
            {legend.map((shift) => (
              <span key={shift.code}>
                <span className={`legend-swatch shift-${shift.code}`} />
                <strong>{shift.code}</strong> = {shift.start_time.slice(0, 5)}-
                {shift.end_time.slice(0, 5)}
              </span>
            ))}
            <span>
              <span className="legend-swatch shift-W" />
              <strong>W</strong> = wolne
            </span>
            <span>
              <span className="legend-swatch" style={{ background: 'var(--nurse-weekend)' }} />
              weekend
            </span>
            <span>
              <span className="legend-swatch" style={{ background: 'var(--nurse-holiday)' }} />
              swieto
            </span>
            <span>
              <span className="legend-swatch unavailable-cell" />
              niedostepnosc
            </span>
            {editable && <span className="ms-auto">Przeciagnij zmiane, aby ja przeniesc.</span>}
          </div>

          <div className="row g-3">
            <div className="col-12 col-xl-4">
              <ValidationPanel
                validation={validation}
                onLocate={(violation) =>
                  setHighlight({ employeeId: violation.employee_id, date: violation.date })
                }
              />
            </div>
            <div className="col-12 col-xl-8">
              {validation?.statistics ? (
                <StatisticsPanel
                  statistics={validation.statistics}
                  shifts={data.shifts}
                  weeklyLimitMinutes={settings?.weekly_minutes_limit ?? 2275}
                  onEmployeePdf={
                    schedule
                      ? (employeeId) =>
                          downloadFile(
                            `/api/schedules/${schedule.id}/employee/${employeeId}/pdf`,
                            `grafik_${year}_${String(month).padStart(2, '0')}_${employeeId}.pdf`,
                          ).catch(() => toasts.error('Blad', 'Nie udalo sie pobrac PDF.'))
                      : undefined
                  }
                />
              ) : (
                <div className="card shadow-sm">
                  <div className="card-body text-secondary small">
                    Statystyki pojawia sie po wygenerowaniu lub walidacji grafiku.
                  </div>
                </div>
              )}
            </div>
          </div>
        </>
      )}

      {cell && (
        <Modal
          title={`${cell.employee.full_name} - ${formatDate(cell.day.date)}`}
          onClose={() => setCell(null)}
          footer={
            <>
              <button
                className="btn btn-outline-secondary"
                onClick={() => setCell(null)}
                type="button"
              >
                Anuluj
              </button>
              {cell.assignment && (
                <button className="btn btn-outline-danger" onClick={() => setShift(null)} type="button">
                  <i className="bi bi-x-lg me-1" /> Ustaw wolne (W)
                </button>
              )}
            </>
          }
        >
          {cell.day.is_holiday && (
            <div className="alert alert-warning py-2 small">
              <i className="bi bi-stars me-1" />
              {cell.day.holiday_name}
            </div>
          )}
          <p className="text-secondary small">Wybierz zmiane dla tego dnia:</p>
          <div className="d-grid gap-2">
            {data.shifts.map((shift) => (
              <button
                key={shift.code}
                className={`btn ${
                  cell.assignment?.shift_code === shift.code ? 'btn-primary' : 'btn-outline-primary'
                } text-start`}
                onClick={() => setShift(shift.code)}
                disabled={busy}
                type="button"
              >
                <strong className="me-2">{shift.code}</strong>
                {shift.name} ({shift.start_time.slice(0, 5)}-{shift.end_time.slice(0, 5)})
              </button>
            ))}
          </div>
        </Modal>
      )}
    </>
  )
}
