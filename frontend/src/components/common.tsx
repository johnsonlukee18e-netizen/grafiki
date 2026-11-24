/** Small presentational building blocks shared by the pages. */
import type { ReactNode } from 'react'

import { COLOR_LABEL, MONTHS_PL, STATUS_LABEL, STATUS_VARIANT } from '../lib'
import type { EmployeeColor, ScheduleStatus } from '../types'

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string
  subtitle?: ReactNode
  actions?: ReactNode
}) {
  return (
    <div className="d-flex flex-wrap justify-content-between align-items-end gap-3 mb-4">
      <div>
        <h1 className="page-title">{title}</h1>
        {subtitle && <div className="text-secondary small">{subtitle}</div>}
      </div>
      {actions && <div className="d-flex flex-wrap gap-2">{actions}</div>}
    </div>
  )
}

export function ColorDot({ color, title }: { color: EmployeeColor; title?: string }) {
  return (
    <span
      className={`color-dot color-${color}`}
      title={title ?? COLOR_LABEL[color]}
      aria-label={COLOR_LABEL[color]}
    />
  )
}

export function StatusBadge({ status }: { status: ScheduleStatus }) {
  return (
    <span className={`badge text-bg-${STATUS_VARIANT[status] ?? 'secondary'}`}>
      {STATUS_LABEL[status] ?? status}
    </span>
  )
}

export function Loading({ label = 'Wczytywanie...' }: { label?: string }) {
  return (
    <div className="d-flex align-items-center gap-2 text-secondary py-4">
      <span className="spinner-border spinner-border-sm" role="status" aria-hidden="true" />
      <span>{label}</span>
    </div>
  )
}

export function ErrorBox({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : 'Wystąpił nieoczekiwany błąd.'
  return (
    <div className="alert alert-danger" role="alert">
      <i className="bi bi-exclamation-triangle me-2" />
      {message}
    </div>
  )
}

export function EmptyState({ icon, title, children }: { icon: string; title: string; children?: ReactNode }) {
  return (
    <div className="text-center text-secondary py-5">
      <i className={`bi ${icon} fs-1 d-block mb-2 opacity-50`} />
      <div className="fw-semibold mb-1">{title}</div>
      {children && <div className="small">{children}</div>}
    </div>
  )
}

export function MonthPicker({
  year,
  month,
  onChange,
}: {
  year: number
  month: number
  onChange: (year: number, month: number) => void
}) {
  const shift = (delta: number) => {
    const index = year * 12 + (month - 1) + delta
    onChange(Math.floor(index / 12), (index % 12) + 1)
  }
  const years = Array.from({ length: 7 }, (_, i) => new Date().getFullYear() - 2 + i)

  return (
    <div className="btn-group" role="group" aria-label="Wybór miesiąca">
      <button
        className="btn btn-outline-secondary"
        onClick={() => shift(-1)}
        type="button"
        aria-label="Poprzedni miesiąc"
      >
        <i className="bi bi-chevron-left" />
      </button>
      <select
        className="form-select"
        style={{ minWidth: 150, maxWidth: 180 }}
        value={month}
        onChange={(e) => onChange(year, Number(e.target.value))}
        aria-label="Miesiąc"
      >
        {MONTHS_PL.map((name, index) => (
          <option key={name} value={index + 1}>
            {name}
          </option>
        ))}
      </select>
      <select
        className="form-select"
        style={{ maxWidth: 105 }}
        value={year}
        onChange={(e) => onChange(Number(e.target.value), month)}
        aria-label="Rok"
      >
        {years.map((value) => (
          <option key={value} value={value}>
            {value}
          </option>
        ))}
      </select>
      <button
        className="btn btn-outline-secondary"
        onClick={() => shift(1)}
        type="button"
        aria-label="Następny miesiąc"
      >
        <i className="bi bi-chevron-right" />
      </button>
    </div>
  )
}

export function Modal({
  title,
  onClose,
  children,
  footer,
  size,
}: {
  title: string
  onClose: () => void
  children: ReactNode
  footer?: ReactNode
  size?: 'lg' | 'xl'
}) {
  return (
    <>
      <div className="modal fade show d-block" role="dialog" tabIndex={-1}>
        <div className={`modal-dialog modal-dialog-centered ${size ? `modal-${size}` : ''}`}>
          <div className="modal-content">
            <div className="modal-header">
              <h5 className="modal-title">{title}</h5>
              <button type="button" className="btn-close" aria-label="Zamknij" onClick={onClose} />
            </div>
            <div className="modal-body">{children}</div>
            {footer && <div className="modal-footer">{footer}</div>}
          </div>
        </div>
      </div>
      <div className="modal-backdrop fade show" onClick={onClose} />
    </>
  )
}
