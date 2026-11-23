import { useEffect, useState } from 'react'

import { useAuthStatus, useSaveSettings, useSaveShift, useSettings, useShifts } from '../api/hooks'
import { ErrorBox, Loading, PageHeader } from '../components/common'
import { useToasts } from '../components/Toasts'
import { formatMinutes } from '../lib'
import type { DepartmentConfig, Shift } from '../types'

/** "37:55" <-> 2275 so the manager never types raw minutes. */
function parseHoursMinutes(value: string): number | null {
  const match = value.trim().match(/^(\d{1,3}):([0-5]\d)$/)
  if (!match) return null
  return Number(match[1]) * 60 + Number(match[2])
}

export default function SettingsPage() {
  const { data: auth } = useAuthStatus()
  const { data, isLoading, error } = useSettings()
  const { data: shifts } = useShifts()
  const save = useSaveSettings()
  const saveShift = useSaveShift()
  const toasts = useToasts()

  const [form, setForm] = useState<DepartmentConfig | null>(null)
  const [weekly, setWeekly] = useState('')
  const [rest, setRest] = useState('')

  useEffect(() => {
    if (!data) return
    setForm(data)
    setWeekly(formatMinutes(data.weekly_minutes_limit))
    setRest(formatMinutes(data.min_rest_minutes))
  }, [data])

  if (isLoading) return <Loading />
  if (error) return <ErrorBox error={error} />
  if (!form) return null

  const isAdmin = auth?.user?.role === 'ADMIN'

  const submit = () => {
    const weeklyMinutes = parseHoursMinutes(weekly)
    const restMinutes = parseHoursMinutes(rest)
    if (weeklyMinutes === null || restMinutes === null) {
      toasts.error('Nieprawidlowy format', 'Uzyj formatu GG:MM, np. 37:55.')
      return
    }
    save.mutate(
      {
        facility_name: form.facility_name,
        department_name: form.department_name,
        weekly_minutes_limit: weeklyMinutes,
        min_rest_minutes: restMinutes,
        sunday_free_every_n: form.sunday_free_every_n,
        sunday_rule_mode: form.sunday_rule_mode,
        sunday_cycle_anchor: form.sunday_cycle_anchor,
        sunday_includes_saturday_night: form.sunday_includes_saturday_night,
        solver_time_limit_seconds: form.solver_time_limit_seconds,
        solver_seed: form.solver_seed,
        solver_workers: form.solver_workers,
        allow_overstaffing: form.allow_overstaffing,
        weight_night_fairness: form.weight_night_fairness,
        weight_weekend_fairness: form.weight_weekend_fairness,
        weight_holiday_fairness: form.weight_holiday_fairness,
        weight_hours_fairness: form.weight_hours_fairness,
        weight_preferences: form.weight_preferences,
        weight_preferred_off: form.weight_preferred_off,
        weight_coverage_bonus: form.weight_coverage_bonus,
      },
      {
        onSuccess: () => toasts.success('Ustawienia zapisane'),
        onError: (err) => toasts.error('Nie zapisano', (err as Error).message),
      },
    )
  }

  const set = <K extends keyof DepartmentConfig>(key: K, value: DepartmentConfig[K]) =>
    setForm({ ...form, [key]: value })

  return (
    <>
      <PageHeader
        title="Ustawienia oddzialu"
        subtitle={
          isAdmin
            ? 'Zmiany wplywaja na generator i walidator - obowiazuja od nastepnej generacji.'
            : 'Podglad ustawien. Edycja wymaga roli ADMIN.'
        }
        actions={
          isAdmin && (
            <button className="btn btn-primary" onClick={submit} disabled={save.isPending} type="button">
              <i className="bi bi-save me-1" /> Zapisz ustawienia
            </button>
          )
        }
      />

      <fieldset disabled={!isAdmin}>
        <div className="row g-3">
          <div className="col-12 col-xl-6">
            <div className="card shadow-sm h-100">
              <div className="card-header bg-white fw-semibold">Placowka</div>
              <div className="card-body">
                <div className="mb-3">
                  <label className="form-label">Nazwa placowki</label>
                  <input
                    className="form-control"
                    value={form.facility_name}
                    onChange={(e) => set('facility_name', e.target.value)}
                  />
                </div>
                <div className="mb-0">
                  <label className="form-label">Oddzial</label>
                  <input
                    className="form-control"
                    value={form.department_name}
                    onChange={(e) => set('department_name', e.target.value)}
                  />
                </div>
              </div>
            </div>
          </div>

          <div className="col-12 col-xl-6">
            <div className="card shadow-sm h-100">
              <div className="card-header bg-white fw-semibold">Twarde ograniczenia</div>
              <div className="card-body">
                <div className="row g-3">
                  <div className="col-6">
                    <label className="form-label">Limit tygodniowy (GG:MM)</label>
                    <input
                      className="form-control"
                      value={weekly}
                      onChange={(e) => setWeekly(e.target.value)}
                      placeholder="37:55"
                    />
                    <div className="form-text">Tydzien: poniedzialek - niedziela.</div>
                  </div>
                  <div className="col-6">
                    <label className="form-label">Minimalny odpoczynek (GG:MM)</label>
                    <input
                      className="form-control"
                      value={rest}
                      onChange={(e) => setRest(e.target.value)}
                      placeholder="11:00"
                    />
                  </div>
                  <div className="col-6">
                    <label className="form-label">Wolna niedziela co N</label>
                    <input
                      type="number"
                      min={1}
                      max={52}
                      className="form-control"
                      value={form.sunday_free_every_n}
                      onChange={(e) => set('sunday_free_every_n', Number(e.target.value))}
                    />
                  </div>
                  <div className="col-6">
                    <label className="form-label">Tryb cyklu niedziel</label>
                    <select
                      className="form-select"
                      value={form.sunday_rule_mode}
                      onChange={(e) =>
                        set('sunday_rule_mode', e.target.value as DepartmentConfig['sunday_rule_mode'])
                      }
                    >
                      <option value="SLIDING">Przesuwny (kazde N kolejnych niedziel)</option>
                      <option value="BLOCK">Blokowy (od daty zakotwiczenia)</option>
                    </select>
                  </div>
                  <div className="col-6">
                    <label className="form-label">Poczatek cyklu (tryb blokowy)</label>
                    <input
                      type="date"
                      className="form-control"
                      value={form.sunday_cycle_anchor}
                      onChange={(e) => set('sunday_cycle_anchor', e.target.value)}
                    />
                  </div>
                  <div className="col-6 d-flex align-items-end">
                    <div className="form-check form-switch">
                      <input
                        className="form-check-input"
                        type="checkbox"
                        id="satNight"
                        checked={form.sunday_includes_saturday_night}
                        onChange={(e) => set('sunday_includes_saturday_night', e.target.checked)}
                      />
                      <label className="form-check-label small" htmlFor="satNight">
                        Nocka z soboty liczy sie jako praca w niedziele
                      </label>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="col-12 col-xl-6">
            <div className="card shadow-sm h-100">
              <div className="card-header bg-white fw-semibold">Solver</div>
              <div className="card-body">
                <div className="row g-3">
                  <div className="col-4">
                    <label className="form-label">Limit czasu (s)</label>
                    <input
                      type="number"
                      min={1}
                      max={75}
                      className="form-control"
                      value={form.solver_time_limit_seconds}
                      onChange={(e) => set('solver_time_limit_seconds', Number(e.target.value))}
                    />
                    <div className="form-text">Maks. 75 s (limit proxy / Cloudflare).</div>
                  </div>
                  <div className="col-4">
                    <label className="form-label">Ziarno (seed)</label>
                    <input
                      type="number"
                      min={0}
                      className="form-control"
                      value={form.solver_seed}
                      onChange={(e) => set('solver_seed', Number(e.target.value))}
                    />
                  </div>
                  <div className="col-4">
                    <label className="form-label">Watki</label>
                    <input
                      type="number"
                      min={1}
                      max={64}
                      className="form-control"
                      value={form.solver_workers}
                      onChange={(e) => set('solver_workers', Number(e.target.value))}
                    />
                    <div className="form-text">1 = powtarzalny wynik.</div>
                  </div>
                  <div className="col-12">
                    <div className="form-check form-switch">
                      <input
                        className="form-check-input"
                        type="checkbox"
                        id="overstaffing"
                        checked={form.allow_overstaffing}
                        onChange={(e) => set('allow_overstaffing', e.target.checked)}
                      />
                      <label className="form-check-label small" htmlFor="overstaffing">
                        Pozwol obsadzic zmiane powyzej minimum
                      </label>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="col-12 col-xl-6">
            <div className="card shadow-sm h-100">
              <div className="card-header bg-white fw-semibold">
                Wagi miekkich kryteriow (wyzsza = wazniejsze)
              </div>
              <div className="card-body">
                <div className="row g-3">
                  {(
                    [
                      ['weight_night_fairness', 'Rowny podzial nocy'],
                      ['weight_weekend_fairness', 'Rowny podzial weekendow'],
                      ['weight_holiday_fairness', 'Rowny podzial swiat'],
                      ['weight_hours_fairness', 'Rowny podzial godzin'],
                      ['weight_preferences', 'Preferencje zmian'],
                      ['weight_preferred_off', 'Preferowane dni wolne'],
                      ['weight_coverage_bonus', 'Premia za obsade ponad minimum'],
                    ] as const
                  ).map(([key, label]) => (
                    <div className="col-6" key={key}>
                      <label className="form-label small">{label}</label>
                      <input
                        type="number"
                        min={0}
                        max={10000}
                        className="form-control form-control-sm"
                        value={form[key]}
                        onChange={(e) => set(key, Number(e.target.value))}
                      />
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          <div className="col-12">
            <div className="card shadow-sm">
              <div className="card-header bg-white fw-semibold">Zmiany</div>
              <div className="table-responsive">
                <table className="table align-middle mb-0">
                  <thead className="table-light">
                    <tr>
                      <th>Kod</th>
                      <th>Nazwa</th>
                      <th>Poczatek</th>
                      <th>Koniec</th>
                      <th>Czas</th>
                      <th>Przez polnoc</th>
                      <th>Min. obsada</th>
                      <th title="Ile osob z minimalnej obsady musi miec role pielegniarki">
                        Min. pielegniarek
                      </th>
                      <th title="Zmiana nie wystepuje w soboty, niedziele i swieta">
                        Tylko dni robocze
                      </th>
                      <th>Aktywna</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {(shifts ?? []).map((shift) => (
                      <ShiftRow
                        key={shift.id}
                        shift={shift}
                        editable={isAdmin}
                        onSave={(payload) =>
                          saveShift.mutate(
                            { id: shift.id, ...payload },
                            {
                              onSuccess: () => toasts.success(`Zmiana ${shift.code} zapisana`),
                              onError: (err) => toasts.error('Blad', (err as Error).message),
                            },
                          )
                        }
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </fieldset>
    </>
  )
}

function ShiftRow({
  shift,
  editable,
  onSave,
}: {
  shift: Shift
  editable: boolean
  onSave: (payload: Partial<Shift>) => void
}) {
  const [draft, setDraft] = useState({
    name: shift.name,
    start_time: shift.start_time.slice(0, 5),
    end_time: shift.end_time.slice(0, 5),
    duration_minutes: shift.duration_minutes,
    minimum_staff: shift.minimum_staff,
    minimum_nurses: shift.minimum_nurses,
    workdays_only: shift.workdays_only,
    active: shift.active,
  })

  /** Wall-clock length of start..end, wrapping over midnight. */
  function span(start: string, end: string): number {
    const [sh, sm] = start.split(':').map(Number)
    const [eh, em] = end.split(':').map(Number)
    if ([sh, sm, eh, em].some((n) => Number.isNaN(n))) return draft.duration_minutes
    const minutes = eh * 60 + em - (sh * 60 + sm)
    return minutes <= 0 ? minutes + 24 * 60 : minutes
  }

  // Changing the hours used to keep the old duration, so e.g. moving the end
  // of R from 14:35 to 15:00 silently left it counted as 7:35. Keep them in
  // step; the duration can still be overridden by hand (e.g. unpaid breaks).
  function setTimes(start: string, end: string) {
    setDraft({ ...draft, start_time: start, end_time: end, duration_minutes: span(start, end) })
  }

  const nursesInvalid = draft.minimum_nurses > draft.minimum_staff

  const dirty =
    draft.name !== shift.name ||
    draft.start_time !== shift.start_time.slice(0, 5) ||
    draft.end_time !== shift.end_time.slice(0, 5) ||
    draft.duration_minutes !== shift.duration_minutes ||
    draft.minimum_staff !== shift.minimum_staff ||
    draft.minimum_nurses !== shift.minimum_nurses ||
    draft.workdays_only !== shift.workdays_only ||
    draft.active !== shift.active

  return (
    <tr>
      <td>
        <span className={`badge shift-${shift.code}`}>{shift.code}</span>
      </td>
      <td>
        <input
          className="form-control form-control-sm"
          value={draft.name}
          onChange={(e) => setDraft({ ...draft, name: e.target.value })}
        />
      </td>
      <td>
        <input
          type="time"
          className="form-control form-control-sm"
          value={draft.start_time}
          onChange={(e) => setTimes(e.target.value, draft.end_time)}
        />
      </td>
      <td>
        <input
          type="time"
          className="form-control form-control-sm"
          value={draft.end_time}
          onChange={(e) => setTimes(draft.start_time, e.target.value)}
        />
      </td>
      <td>
        <input
          type="number"
          min={1}
          className="form-control form-control-sm"
          style={{ width: 90 }}
          value={draft.duration_minutes}
          onChange={(e) => setDraft({ ...draft, duration_minutes: Number(e.target.value) })}
          title="Minuty"
        />
        <div className="form-text">{formatMinutes(draft.duration_minutes)}</div>
      </td>
      <td>{shift.crosses_midnight ? 'tak' : 'nie'}</td>
      <td>
        <input
          type="number"
          min={0}
          max={50}
          className="form-control form-control-sm"
          style={{ width: 80 }}
          value={draft.minimum_staff}
          onChange={(e) => setDraft({ ...draft, minimum_staff: Number(e.target.value) })}
        />
      </td>
      <td>
        <input
          type="number"
          min={0}
          max={draft.minimum_staff}
          className={`form-control form-control-sm ${nursesInvalid ? 'is-invalid' : ''}`}
          style={{ width: 80 }}
          value={draft.minimum_nurses}
          onChange={(e) => setDraft({ ...draft, minimum_nurses: Number(e.target.value) })}
          title="Opiekunka nie zastapi pielegniarki - 0 wylacza regule"
        />
        {nursesInvalid && <div className="invalid-feedback">Wiecej niz obsada</div>}
      </td>
      <td>
        <div className="form-check form-switch">
          <input
            className="form-check-input"
            type="checkbox"
            checked={draft.workdays_only}
            onChange={(e) => setDraft({ ...draft, workdays_only: e.target.checked })}
            title="Nie w weekendy i swieta"
          />
        </div>
      </td>
      <td>
        <div className="form-check form-switch">
          <input
            className="form-check-input"
            type="checkbox"
            checked={draft.active}
            onChange={(e) => setDraft({ ...draft, active: e.target.checked })}
          />
        </div>
      </td>
      <td className="text-end">
        {editable && (
          <button
            className="btn btn-sm btn-primary"
            disabled={!dirty || nursesInvalid}
            onClick={() =>
              onSave({
                name: draft.name,
                start_time: `${draft.start_time}:00`,
                end_time: `${draft.end_time}:00`,
                duration_minutes: draft.duration_minutes,
                minimum_staff: draft.minimum_staff,
                minimum_nurses: draft.minimum_nurses,
                workdays_only: draft.workdays_only,
                active: draft.active,
              })
            }
            type="button"
          >
            Zapisz
          </button>
        )}
      </td>
    </tr>
  )
}
