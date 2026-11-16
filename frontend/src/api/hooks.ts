/** TanStack Query hooks - one place that knows the API shape. */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from './client'
import type {
  AuditEntry,
  AuthStatus,
  Availability,
  AvailabilityType,
  DashboardData,
  DepartmentConfig,
  EditResponse,
  Employee,
  GenerateResponse,
  Holiday,
  RestoreResponse,
  Schedule,
  ScheduleDetail,
  ScheduleVersion,
  ScheduleVersionDetail,
  Shift,
  Statistics,
  User,
  ValidationResult,
} from '../types'

export const keys = {
  auth: ['auth'] as const,
  dashboard: (year: number, month: number) => ['dashboard', year, month] as const,
  employees: ['employees'] as const,
  shifts: ['shifts'] as const,
  settings: ['settings'] as const,
  users: ['users'] as const,
  audit: ['audit'] as const,
  schedules: ['schedules'] as const,
  schedule: (year: number, month: number) => ['schedule', year, month] as const,
  history: (id: number) => ['history', id] as const,
  historyVersion: (id: number, version: number) => ['history', id, version] as const,
  statistics: (id: number) => ['statistics', id] as const,
  holidays: (year: number) => ['holidays', year] as const,
  availability: (employeeId: number | null, year: number, month: number) =>
    ['availability', employeeId, year, month] as const,
}

// --- auth -----------------------------------------------------------------
export function useAuthStatus() {
  return useQuery({
    queryKey: keys.auth,
    queryFn: () => api.get<AuthStatus>('/api/auth/status'),
    staleTime: 30_000,
    retry: false,
  })
}

export function useDevLogin() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<User>('/api/auth/dev-login'),
    onSuccess: () => client.invalidateQueries(),
  })
}

export function useLogout() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<{ success: boolean }>('/api/auth/logout'),
    onSuccess: () => client.clear(),
  })
}

// --- dashboard ------------------------------------------------------------
export function useDashboard(year: number, month: number) {
  return useQuery({
    queryKey: keys.dashboard(year, month),
    queryFn: () => api.get<DashboardData>(`/api/dashboard?year=${year}&month=${month}`),
  })
}

// --- employees ------------------------------------------------------------
export function useEmployees() {
  return useQuery({
    queryKey: keys.employees,
    queryFn: () => api.get<Employee[]>('/api/employees'),
  })
}

export interface EmployeePayload {
  first_name: string
  last_name: string
  role: string
  employment_date: string
  active: boolean
}

export function useSaveEmployee() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id?: number; data: EmployeePayload }) =>
      id
        ? api.put<Employee>(`/api/employees/${id}`, data)
        : api.post<Employee>('/api/employees', data),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: keys.employees })
      client.invalidateQueries({ queryKey: ['schedule'] })
      client.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
}

export function useDeactivateEmployee() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.delete<Employee>(`/api/employees/${id}`),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: keys.employees })
      client.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
}

// --- schedule -------------------------------------------------------------
export function useSchedule(year: number, month: number) {
  return useQuery({
    queryKey: keys.schedule(year, month),
    queryFn: () => api.get<ScheduleDetail>(`/api/schedules/${year}/${month}`),
  })
}

export function useSchedules() {
  return useQuery({
    queryKey: keys.schedules,
    queryFn: () => api.get<Schedule[]>('/api/schedules'),
  })
}

export function useGenerate() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (input: { year: number; month: number }) =>
      api.post<GenerateResponse>('/api/schedules/generate', input),
    onSuccess: () => client.invalidateQueries(),
  })
}

export function useValidate() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      api.post<{ schedule: Schedule; validation: ValidationResult }>(
        `/api/schedules/${id}/validate`,
      ),
    onSuccess: () => client.invalidateQueries(),
  })
}

export function useApprove() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, undo }: { id: number; undo?: boolean }) =>
      api.post(`/api/schedules/${id}/${undo ? 'unapprove' : 'approve'}`),
    onSuccess: () => client.invalidateQueries(),
  })
}

export function useHistory(id: number | undefined) {
  return useQuery({
    queryKey: keys.history(id ?? 0),
    queryFn: () => api.get<ScheduleVersion[]>(`/api/schedules/${id}/history`),
    enabled: Boolean(id),
  })
}

export function useHistoryVersion(id: number | undefined, version: number | undefined) {
  return useQuery({
    queryKey: keys.historyVersion(id ?? 0, version ?? 0),
    queryFn: () =>
      api.get<ScheduleVersionDetail>(`/api/schedules/${id}/history/${version}`),
    enabled: Boolean(id && version),
    staleTime: Infinity, // a stored version never changes
  })
}

export function useRestoreVersion() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, version }: { id: number; version: number }) =>
      api.post<RestoreResponse>(`/api/schedules/${id}/history/${version}/restore`),
    onSuccess: () => client.invalidateQueries(),
  })
}

export function useStatistics(id: number | undefined) {
  return useQuery({
    queryKey: keys.statistics(id ?? 0),
    queryFn: () => api.get<Statistics>(`/api/schedules/${id}/statistics`),
    enabled: Boolean(id),
  })
}

// --- assignments ----------------------------------------------------------
export interface AssignmentInput {
  schedule_id: number
  employee_id: number
  work_date: string
  shift_code: string
}

export function useCreateAssignment() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (input: AssignmentInput) => api.post<EditResponse>('/api/assignments', input),
    onSuccess: () => client.invalidateQueries(),
  })
}

export function useUpdateAssignment() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({
      id,
      ...body
    }: {
      id: number
      employee_id?: number
      work_date?: string
      shift_code?: string
    }) => api.put<EditResponse>(`/api/assignments/${id}`, body),
    onSuccess: () => client.invalidateQueries(),
  })
}

export function useDeleteAssignment() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.delete<EditResponse>(`/api/assignments/${id}`),
    onSuccess: () => client.invalidateQueries(),
  })
}

// --- availability ---------------------------------------------------------
export function useAvailability(employeeId: number | null, year: number, month: number) {
  return useQuery({
    queryKey: keys.availability(employeeId, year, month),
    queryFn: () => {
      const params = new URLSearchParams({ year: String(year), month: String(month) })
      if (employeeId) params.set('employee_id', String(employeeId))
      return api.get<Availability[]>(`/api/availability?${params.toString()}`)
    },
  })
}

export function useSetAvailabilityBulk() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (input: { employee_id: number; dates: string[]; type: AvailabilityType }) =>
      api.post<Availability[]>('/api/availability/bulk', input),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ['availability'] })
      client.invalidateQueries({ queryKey: ['schedule'] })
    },
  })
}

export function useDeleteAvailability() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.delete<void>(`/api/availability/${id}`),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ['availability'] })
      client.invalidateQueries({ queryKey: ['schedule'] })
    },
  })
}

// --- holidays -------------------------------------------------------------
export function useHolidays(year: number) {
  return useQuery({
    queryKey: keys.holidays(year),
    queryFn: () => api.get<Holiday[]>(`/api/holidays/${year}`),
  })
}

export function useCreateHoliday() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (input: { date: string; name: string }) =>
      api.post<Holiday>('/api/holidays', { ...input, country: 'PL' }),
    onSuccess: () => client.invalidateQueries({ queryKey: ['holidays'] }),
  })
}

export function useDeleteHoliday() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.delete<void>(`/api/holidays/${id}`),
    onSuccess: () => client.invalidateQueries({ queryKey: ['holidays'] }),
  })
}

// --- settings / shifts ----------------------------------------------------
export function useSettings() {
  return useQuery({
    queryKey: keys.settings,
    queryFn: () => api.get<DepartmentConfig>('/api/settings'),
  })
}

export function useSaveSettings() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (data: Partial<DepartmentConfig>) =>
      api.put<DepartmentConfig>('/api/settings', data),
    onSuccess: () => client.invalidateQueries(),
  })
}

export function useShifts() {
  return useQuery({
    queryKey: keys.shifts,
    queryFn: () => api.get<Shift[]>('/api/settings/shifts'),
  })
}

export function useSaveShift() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: { id: number } & Partial<Shift>) =>
      api.put<Shift>(`/api/settings/shifts/${id}`, body),
    onSuccess: () => client.invalidateQueries(),
  })
}

// --- users / audit --------------------------------------------------------
export function useUsers() {
  return useQuery({ queryKey: keys.users, queryFn: () => api.get<User[]>('/api/users') })
}

export function useSaveUser() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: { id: number; role?: string; is_active?: boolean }) =>
      api.put<User>(`/api/users/${id}`, body),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.users }),
  })
}

export function useAudit(limit = 150) {
  return useQuery({
    queryKey: [...keys.audit, limit],
    queryFn: () => api.get<AuditEntry[]>(`/api/audit?limit=${limit}`),
  })
}
