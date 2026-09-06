export type UserRole = 'ADMIN' | 'MANAGER'
export type EmployeeRole = 'NURSE' | 'CARE_WORKER'
export type EmployeeColor = 'RED' | 'YELLOW' | 'GREEN' | 'PURPLE'
export type ScheduleStatus =
  | 'DRAFT'
  | 'GENERATING'
  | 'GENERATED'
  | 'VALID'
  | 'INVALID'
  | 'APPROVED'
  | 'ARCHIVED'

export type AvailabilityType =
  | 'AVAILABLE'
  | 'UNAVAILABLE'
  | 'PREFERRED_DAY'
  | 'PREFERRED_MORNING'
  | 'PREFERRED_NIGHT'
  | 'PREFERRED_OFF'

export interface User {
  id: number
  email: string
  name: string | null
  avatar_url: string | null
  role: UserRole
  is_active: boolean
  last_login_at: string | null
  created_at: string
}

export interface AuthStatus {
  authenticated: boolean
  user: User | null
  login_url: string
  oauth_configured: boolean
  dev_auth_enabled: boolean
}

export interface Employee {
  id: number
  first_name: string
  last_name: string
  full_name: string
  role: EmployeeRole
  employment_date: string
  active: boolean
  color: EmployeeColor
  seniority_label: string
  created_at: string
  updated_at: string
}

export interface Shift {
  id: number
  code: string
  name: string
  start_time: string
  end_time: string
  duration_minutes: number
  crosses_midnight: boolean
  minimum_staff: number
  active: boolean
  sort_order: number
}

export interface Availability {
  id: number
  employee_id: number
  date: string
  type: AvailabilityType
  note: string | null
}

export interface Holiday {
  id: number
  date: string
  name: string
  country: string
  is_custom: boolean
}

export interface DayInfo {
  date: string
  weekday: number
  is_weekend: boolean
  is_holiday: boolean
  holiday_name: string | null
}

export interface Assignment {
  id: number
  schedule_id: number
  employee_id: number
  shift_id: number
  shift_code: string
  work_date: string
  start_datetime: string
  end_datetime: string
  manually_modified: boolean
}

export interface Schedule {
  id: number
  year: number
  month: number
  status: ScheduleStatus
  version: number
  generated_at: string | null
  approved_at: string | null
  solver_status: string | null
  created_at: string
  updated_at: string
}

export interface Violation {
  code: string
  severity: 'error' | 'warning'
  message: string
  employee_id: number | null
  employee_name: string | null
  date: string | null
  shift_code: string | null
  details: Record<string, unknown>
}

export interface CheckRow {
  code: string
  label: string
  kind: 'hard' | 'soft'
  status: 'OK' | 'WARNING' | 'ERROR'
  count: number
}

export interface EmployeeStats {
  employee_id: number
  employee_name: string
  role: EmployeeRole
  shifts: Record<string, number>
  total_shifts: number
  minutes: number
  hours_label: string
  limit_label: string
  nights: number
  saturdays: number
  sundays: number
  weekend_shifts: number
  holiday_shifts: number
  days_off: number
  weeks: { week: string; minutes: number; label: string; limit_exceeded: boolean }[]
}

export interface Spread {
  min: number
  max: number
  spread: number
  avg: number
}

export interface Statistics {
  employees: EmployeeStats[]
  fairness: Record<string, Spread>
  coverage: {
    date: string
    weekday: number
    is_weekend: boolean
    is_holiday: boolean
    holiday_name: string | null
    shifts: Record<string, { count: number; required: number; understaffed: boolean }>
  }[]
  totals: {
    assignments: number
    minutes: number
    hours_label: string
    employees: number
    days: number
    holidays: number
  }
}

export interface ValidationResult {
  valid: boolean
  errors: Violation[]
  warnings: Violation[]
  statistics: Statistics
  checks: CheckRow[]
}

export interface ScheduleDetail {
  schedule: Schedule | null
  year: number
  month: number
  days: DayInfo[]
  employees: Employee[]
  shifts: Shift[]
  assignments: Assignment[]
  validation: ValidationResult | null
}

export interface SolverDiagnostic {
  code: string
  message: string
  date: string | null
  shift_code: string | null
  details: Record<string, unknown>
}

export interface SolverResult {
  success: boolean
  status: string
  objective: number | null
  is_optimal: boolean
  wall_time_seconds: number
  message: string
  diagnostics: SolverDiagnostic[]
  suggestions: string[]
}

export interface GenerateResponse {
  success: boolean
  schedule: Schedule | null
  solver: SolverResult
  validation: ValidationResult | null
}

export interface EditResponse {
  assignment: Assignment | null
  schedule: Schedule
  validation: ValidationResult
  new_warnings: Violation[]
}

export interface ScheduleVersion {
  id: number
  schedule_id: number
  version: number
  status: ScheduleStatus
  reason: string
  created_at: string
  created_by: number | null
}

export interface DepartmentConfig {
  id: number
  facility_name: string
  department_name: string
  weekly_minutes_limit: number
  min_rest_minutes: number
  sunday_free_every_n: number
  sunday_rule_mode: 'SLIDING' | 'BLOCK'
  sunday_cycle_anchor: string
  sunday_includes_saturday_night: boolean
  country_code: string
  solver_time_limit_seconds: number
  solver_seed: number
  solver_workers: number
  allow_overstaffing: boolean
  weight_night_fairness: number
  weight_weekend_fairness: number
  weight_holiday_fairness: number
  weight_hours_fairness: number
  weight_preferences: number
  weight_preferred_off: number
  weight_coverage_bonus: number
}

export interface DashboardData {
  facility_name: string
  department_name: string
  current: {
    schedule: Schedule
    assignments: number
    errors: number
    warnings: number
    checks: CheckRow[]
  } | null
  employees_active: number
  employees_total: number
  shifts: Shift[]
  recent_schedules: Schedule[]
}

export interface AuditEntry {
  id: number
  user_id: number | null
  user_email: string | null
  action: string
  entity_type: string | null
  entity_id: number | null
  timestamp: string
  metadata: Record<string, unknown> | null
}
