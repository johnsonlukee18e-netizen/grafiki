/** Non-blocking notifications used for warnings and blocked operations. */
import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

type Variant = 'success' | 'danger' | 'warning' | 'info'

interface Toast {
  id: number
  variant: Variant
  title: string
  message: string
  details?: string[]
}

interface ToastApi {
  push: (toast: Omit<Toast, 'id'>) => void
  success: (title: string, message?: string) => void
  error: (title: string, message?: string, details?: string[]) => void
  warning: (title: string, message?: string, details?: string[]) => void
}

const ToastContext = createContext<ToastApi | null>(null)

const AUTO_DISMISS_MS = 9000

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const remove = useCallback((id: number) => {
    setToasts((current) => current.filter((t) => t.id !== id))
  }, [])

  const push = useCallback(
    (toast: Omit<Toast, 'id'>) => {
      const id = Date.now() + Math.random()
      setToasts((current) => [...current, { ...toast, id }])
      // Errors stay until dismissed; the manager must be able to read them.
      if (toast.variant !== 'danger') {
        window.setTimeout(() => remove(id), AUTO_DISMISS_MS)
      }
    },
    [remove],
  )

  const api = useMemo<ToastApi>(
    () => ({
      push,
      success: (title, message = '') => push({ variant: 'success', title, message }),
      error: (title, message = '', details) =>
        push({ variant: 'danger', title, message, details }),
      warning: (title, message = '', details) =>
        push({ variant: 'warning', title, message, details }),
    }),
    [push],
  )

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="toast-stack">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`toast show mb-2 border-0 text-bg-${toast.variant}`}
            role="alert"
          >
            <div className="toast-header">
              <strong className="me-auto">{toast.title}</strong>
              <button
                type="button"
                className="btn-close"
                aria-label="Zamknij"
                onClick={() => remove(toast.id)}
              />
            </div>
            {(toast.message || toast.details?.length) && (
              <div className="toast-body">
                {toast.message && <div>{toast.message}</div>}
                {toast.details?.length ? (
                  <ul className="mb-0 mt-2 ps-3 small">
                    {toast.details.map((detail, index) => (
                      <li key={index}>{detail}</li>
                    ))}
                  </ul>
                ) : null}
              </div>
            )}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToasts(): ToastApi {
  const context = useContext(ToastContext)
  if (!context) throw new Error('useToasts must be used inside ToastProvider')
  return context
}
