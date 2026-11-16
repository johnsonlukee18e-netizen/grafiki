import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { ApiError } from '../api/client'
import {
  useHistory,
  useHistoryVersion,
  useRestoreVersion,
  useSchedule,
  useSchedules,
} from '../api/hooks'
import ScheduleGrid from '../components/ScheduleGrid'
import { ErrorBox, Loading, Modal, PageHeader, StatusBadge } from '../components/common'
import { useToasts } from '../components/Toasts'
import { formatDateTime, monthLabel } from '../lib'
import type { Assignment, Schedule, ScheduleVersion } from '../types'

export default function HistoryPage() {
  const { data: schedules, isLoading, error } = useSchedules()
  const [selected, setSelected] = useState<number | undefined>(undefined)
  const [preview, setPreview] = useState<ScheduleVersion | null>(null)

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
        subtitle="Kazda generacja i kazda reczna korekta zapisuje nowa wersje. Nic nie jest usuwane - starsza wersje mozna podejrzec i przywrocic."
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
            <div className="card-header bg-white fw-semibold d-flex justify-content-between">
              <span>
                {schedule ? `Wersje - ${monthLabel(schedule.year, schedule.month)}` : 'Wersje'}
              </span>
              {schedule && (
                <span className="fw-normal small text-secondary">
                  biezaca: v{schedule.version}
                </span>
              )}
            </div>
            <div className="table-responsive">
              <table className="table table-sm align-middle mb-0">
                <thead className="table-light">
                  <tr>
                    <th>Wersja</th>
                    <th>Powod zmiany</th>
                    <th>Status</th>
                    <th>Data</th>
                    <th />
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
                      <td className="text-end">
                        <button
                          className="btn btn-sm btn-outline-primary"
                          onClick={() => setPreview(version)}
                          type="button"
                        >
                          <i className="bi bi-eye me-1" />
                          Podglad
                        </button>
                      </td>
                    </tr>
                  ))}
                  {(versions ?? []).length === 0 && (
                    <tr>
                      <td colSpan={5} className="text-secondary small py-3">
                        Ten grafik nie ma jeszcze zapisanych wersji historycznych.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            <div className="card-footer bg-white small text-secondary">
              Wersja vN to stan grafiku zapisany tuz przed zmiana opisana w kolumnie &quot;Powod
              zmiany&quot;.
            </div>
          </div>
        </div>
      </div>

      {preview && schedule && (
        <VersionPreview schedule={schedule} version={preview} onClose={() => setPreview(null)} />
      )}
    </>
  )
}

function VersionPreview({
  schedule,
  version,
  onClose,
}: {
  schedule: Schedule
  version: ScheduleVersion
  onClose: () => void
}) {
  const toasts = useToasts()
  const navigate = useNavigate()
  const [confirming, setConfirming] = useState(false)
  const { data: detail, isLoading, error } = useHistoryVersion(schedule.id, version.version)
  const { data: month } = useSchedule(schedule.year, schedule.month)
  const restore = useRestoreVersion()

  const assignments: Assignment[] = useMemo(() => {
    const shiftIds = new Map((month?.shifts ?? []).map((s) => [s.code, s.id]))
    return (detail?.snapshot.assignments ?? []).map((item, index) => ({
      id: -(index + 1),
      schedule_id: schedule.id,
      employee_id: item.employee_id,
      shift_id: shiftIds.get(item.shift_code) ?? 0,
      shift_code: item.shift_code,
      work_date: item.date,
      start_datetime: '',
      end_datetime: '',
      manually_modified: item.manually_modified,
    }))
  }, [detail, month, schedule.id])

  const locked = schedule.status === 'APPROVED' || schedule.status === 'ARCHIVED'

  function runRestore() {
    restore.mutate(
      { id: schedule.id, version: version.version },
      {
        onSuccess: (response) => {
          const title = `Przywrocono wersje v${version.version}`
          if (response.validation.valid && response.skipped.length === 0) {
            toasts.success(
              title,
              `Grafik jest teraz w wersji v${response.schedule.version} i spelnia twarde ograniczenia.`,
            )
          } else {
            toasts.warning(
              title,
              response.validation.valid
                ? 'Czesci wpisow nie dalo sie przywrocic:'
                : `Grafik jest w wersji v${response.schedule.version}, ale przy obecnych danych ma bledy - sprawdz panel walidacji.`,
              response.skipped,
            )
          }
          onClose()
          navigate(`/grafik?year=${schedule.year}&month=${schedule.month}`)
        },
        onError: (err) =>
          toasts.error(
            'Nie udalo sie przywrocic wersji',
            err instanceof ApiError ? err.message : 'Sprobuj ponownie.',
          ),
      },
    )
  }

  return (
    <Modal
      title={`${monthLabel(schedule.year, schedule.month)} - wersja v${version.version}`}
      onClose={onClose}
      size="xl"
      footer={
        <>
          <button className="btn btn-outline-secondary" onClick={onClose} type="button">
            Zamknij
          </button>
          {!locked &&
            (confirming ? (
              <>
                <span className="small text-secondary me-2">
                  Biezacy grafik zostanie zapisany w historii, a ta wersja stanie sie aktualna.
                </span>
                <button
                  className="btn btn-warning"
                  onClick={runRestore}
                  disabled={restore.isPending}
                  type="button"
                >
                  {restore.isPending && <span className="spinner-border spinner-border-sm me-1" />}
                  Potwierdz przywrocenie
                </button>
              </>
            ) : (
              <button
                className="btn btn-primary"
                onClick={() => setConfirming(true)}
                disabled={!detail}
                type="button"
              >
                <i className="bi bi-arrow-counterclockwise me-1" />
                Przywroc te wersje
              </button>
            ))}
        </>
      }
    >
      <p className="small text-secondary mb-2">
        {version.reason} &middot; {formatDateTime(version.created_at)} &middot;{' '}
        {detail ? `${detail.snapshot.assignments.length} przypisanych zmian` : '...'}
      </p>
      {locked && (
        <div className="alert alert-dark py-2 small">
          <i className="bi bi-lock me-1" />
          Grafik jest zatwierdzony. Aby przywrocic starsza wersje, najpierw cofnij zatwierdzenie.
        </div>
      )}
      {error && <ErrorBox error={error} />}
      {isLoading || !month ? (
        <Loading />
      ) : (
        <ScheduleGrid
          days={month.days}
          employees={month.employees.filter(
            (e) => e.active || assignments.some((a) => a.employee_id === e.id),
          )}
          shifts={month.shifts}
          assignments={assignments}
          availability={[]}
          editable={false}
          onCellClick={() => undefined}
          onMove={() => undefined}
        />
      )}
    </Modal>
  )
}
