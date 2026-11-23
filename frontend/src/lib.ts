/** Small shared helpers (formatting, month names, colours). */
import type { EmployeeColor } from './types'

export const MONTHS_PL = [
  'Styczen', 'Luty', 'Marzec', 'Kwiecien', 'Maj', 'Czerwiec',
  'Lipiec', 'Sierpien', 'Wrzesien', 'Pazdziernik', 'Listopad', 'Grudzien',
]

export const WEEKDAYS_PL = ['Pn', 'Wt', 'Sr', 'Cz', 'Pt', 'So', 'Nd']

export function monthLabel(year: number, month: number): string {
  return `${MONTHS_PL[month - 1]} ${year}`
}

/** 2275 -> "37:55" (minutes only, never floats). */
export function formatMinutes(minutes: number): string {
  const sign = minutes < 0 ? '-' : ''
  const value = Math.abs(Math.round(minutes))
  return `${sign}${Math.floor(value / 60)}:${String(value % 60).padStart(2, '0')}`
}

export function formatDate(iso: string): string {
  const [y, m, d] = iso.split('-')
  return `${d}.${m}.${y}`
}

export function formatDateTime(iso: string | null): string {
  if (!iso) return '-'
  const date = new Date(iso)
  return date.toLocaleString('pl-PL', { dateStyle: 'short', timeStyle: 'short' })
}

export const COLOR_LABEL: Record<EmployeeColor, string> = {
  RED: 'Pielegniarka, staz powyzej 3 lat',
  YELLOW: 'Pielegniarka, staz 1-3 lata',
  GREEN: 'Pielegniarka, staz do 1 roku',
  PURPLE: 'Opiekunka',
}

export const ROLE_LABEL: Record<string, string> = {
  NURSE: 'Pielegniarka',
  CARE_WORKER: 'Opiekunka',
}

export const AVAILABILITY_LABEL: Record<string, string> = {
  AVAILABLE: 'Dostepny',
  UNAVAILABLE: 'Niedostepny (twarde)',
  PREFERRED_DAY: 'Preferuje dzien (D)',
  PREFERRED_MORNING: 'Preferuje ranek (R)',
  PREFERRED_NIGHT: 'Preferuje noc (N)',
  PREFERRED_OFF: 'Prosi o wolne',
}

export const STATUS_LABEL: Record<string, string> = {
  DRAFT: 'Szkic',
  GENERATING: 'Generowanie',
  GENERATED: 'Wygenerowany',
  VALID: 'Poprawny',
  INVALID: 'Bledy',
  APPROVED: 'Zatwierdzony',
  ARCHIVED: 'Zarchiwizowany',
}

export const STATUS_VARIANT: Record<string, string> = {
  DRAFT: 'secondary',
  GENERATING: 'info',
  GENERATED: 'primary',
  VALID: 'success',
  INVALID: 'danger',
  APPROVED: 'dark',
  ARCHIVED: 'secondary',
}

export const ACTION_LABEL: Record<string, string> = {
  LOGIN: 'Logowanie',
  LOGOUT: 'Wylogowanie',
  EMPLOYEE_CREATED: 'Dodanie pracownika',
  EMPLOYEE_UPDATED: 'Edycja pracownika',
  EMPLOYEE_DEACTIVATED: 'Dezaktywacja pracownika',
  AVAILABILITY_CHANGED: 'Zmiana dostepnosci',
  SCHEDULE_GENERATED: 'Wygenerowanie grafiku',
  SCHEDULE_VALIDATED: 'Walidacja grafiku',
  SCHEDULE_APPROVED: 'Zatwierdzenie grafiku',
  SCHEDULE_RESTORED: 'Przywrocenie wersji grafiku',
  SCHEDULE_MODE_CHANGED: 'Zmiana trybu ukladania grafiku',
  SCHEDULE_MANUAL_EDIT: 'Reczne ukladanie grafiku',
  ASSIGNMENT_CREATED: 'Dodanie zmiany',
  ASSIGNMENT_MOVED: 'Przeniesienie zmiany',
  ASSIGNMENT_UPDATED: 'Edycja zmiany',
  ASSIGNMENT_DELETED: 'Usuniecie zmiany',
  PDF_EXPORTED: 'Eksport PDF',
  SETTINGS_UPDATED: 'Zmiana ustawien',
  USER_ROLE_CHANGED: 'Zmiana roli',
  USER_ACTIVATION_CHANGED: 'Aktywacja konta',
  HOLIDAYS_IMPORTED: 'Swieta',
}

/** A working-days-only shift (R) does not exist on weekends and holidays. */
export function shiftAllowedOn(
  shift: { workdays_only: boolean },
  day: { is_weekend: boolean; is_holiday: boolean },
): boolean {
  return !shift.workdays_only || (!day.is_weekend && !day.is_holiday)
}

/** ISO date string for a year/month/day without timezone surprises. */
export function isoDate(year: number, month: number, day: number): string {
  return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
}

export function todayParts(): { year: number; month: number } {
  const now = new Date()
  return { year: now.getFullYear(), month: now.getMonth() + 1 }
}
