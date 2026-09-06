/** KONTROLA GRAFIKU - the checklist plus clickable error details. */
import { useState } from 'react'

import { formatDate } from '../lib'
import type { ValidationResult, Violation } from '../types'

interface Props {
  validation: ValidationResult | null
  onLocate?: (violation: Violation) => void
}

export default function ValidationPanel({ validation, onLocate }: Props) {
  const [open, setOpen] = useState<string | null>(null)

  if (!validation) {
    return (
      <div className="card shadow-sm">
        <div className="card-header bg-white fw-semibold">Kontrola grafiku</div>
        <div className="card-body text-secondary small">
          Grafik nie byl jeszcze walidowany.
        </div>
      </div>
    )
  }

  const grouped = (items: Violation[]) => {
    const map = new Map<string, Violation[]>()
    for (const item of items) {
      const list = map.get(item.code) ?? []
      list.push(item)
      map.set(item.code, list)
    }
    return map
  }

  const errors = grouped(validation.errors)
  const warnings = grouped(validation.warnings)

  const statusBadge = validation.valid
    ? validation.warnings.length
      ? { variant: 'warning', label: 'WARNING' }
      : { variant: 'success', label: 'OK' }
    : { variant: 'danger', label: 'ERROR' }

  return (
    <div className="card shadow-sm">
      <div className="card-header bg-white d-flex justify-content-between align-items-center">
        <span className="fw-semibold">Kontrola grafiku</span>
        <span className={`badge text-bg-${statusBadge.variant}`}>{statusBadge.label}</span>
      </div>
      <div className="card-body py-2">
        {validation.checks.map((row) => {
          const items = row.kind === 'hard' ? errors.get(row.code) : warnings.get(row.code)
          const isOpen = open === row.code
          const ok = row.status === 'OK'
          return (
            <div key={row.code}>
              <div
                className="check-row"
                role={items?.length ? 'button' : undefined}
                onClick={() => items?.length && setOpen(isOpen ? null : row.code)}
              >
                <span className={ok ? '' : 'fw-semibold'}>
                  <i
                    className={`bi me-2 ${
                      ok
                        ? 'bi-check-circle-fill text-success'
                        : row.kind === 'hard'
                          ? 'bi-x-circle-fill text-danger'
                          : 'bi-exclamation-triangle-fill text-warning'
                    }`}
                  />
                  {row.label}
                </span>
                <span className="d-flex align-items-center gap-2">
                  {row.count > 0 && (
                    <span
                      className={`badge text-bg-${row.kind === 'hard' ? 'danger' : 'warning'}`}
                    >
                      {row.count}
                    </span>
                  )}
                  {items?.length ? (
                    <i className={`bi ${isOpen ? 'bi-chevron-up' : 'bi-chevron-down'} small`} />
                  ) : null}
                </span>
              </div>

              {isOpen && items?.length ? (
                <ul className="list-unstyled small ps-4 pb-2 mb-0">
                  {items.slice(0, 25).map((item, index) => (
                    <li key={index} className="py-1 border-bottom">
                      <button
                        className="btn btn-link btn-sm p-0 text-start text-decoration-none"
                        onClick={() => onLocate?.(item)}
                        type="button"
                      >
                        {item.date && (
                          <span className="badge text-bg-light me-1">{formatDate(item.date)}</span>
                        )}
                        {item.message}
                      </button>
                    </li>
                  ))}
                  {items.length > 25 && (
                    <li className="text-secondary pt-1">
                      ... i {items.length - 25} kolejnych
                    </li>
                  )}
                </ul>
              ) : null}
            </div>
          )
        })}
      </div>
    </div>
  )
}
