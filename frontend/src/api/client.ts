/**
 * Thin fetch wrapper.
 *
 * The session lives in an HTTP-only cookie, so nothing is stored in
 * localStorage. Unsafe requests echo the CSRF cookie back in a header
 * (double-submit protection).
 */

export class ApiError extends Error {
  readonly status: number
  /** Structured payload from the backend (validation errors, violations...). */
  readonly detail: unknown

  constructor(status: number, message: string, detail: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }

  /** Hard-constraint violations returned by a blocked manual edit. */
  get violations(): { code: string; message: string }[] {
    const detail = this.detail as { errors?: { code: string; message: string }[] } | undefined
    return detail?.errors ?? []
  }
}

const CSRF_COOKIE = 'nurse_csrf'
const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS'])

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return match ? decodeURIComponent(match[1]) : null
}

/** Fired on 401 so the app can bounce the user back to the login screen. */
export const UNAUTHORIZED_EVENT = 'nurse:unauthorized'

function friendlyMessage(status: number, payload: unknown): string {
  const detail = (payload as { detail?: unknown })?.detail
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object' && 'message' in detail) {
    return String((detail as { message: unknown }).message)
  }
  switch (status) {
    case 401:
      return 'Sesja wygasla. Zaloguj sie ponownie.'
    case 403:
      return 'Nie masz uprawnien do wykonania tej operacji.'
    case 404:
      return 'Nie znaleziono zasobu.'
    case 409:
      return 'Operacja jest sprzeczna z regulami grafiku.'
    case 422:
      return 'Nieprawidlowe dane wejsciowe.'
    case 429:
      return 'Zbyt wiele zadan. Odczekaj chwile.'
    default:
      return 'Wystapil blad serwera. Sprobuj ponownie.'
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (!SAFE_METHODS.has(method)) {
    const token = readCookie(CSRF_COOKIE)
    if (token) headers['X-CSRF-Token'] = token
  }

  const response = await fetch(path, {
    method,
    headers,
    credentials: 'same-origin',
    body: body === undefined ? undefined : JSON.stringify(body),
  })

  if (response.status === 401) {
    window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT))
  }

  if (!response.ok) {
    let payload: unknown = null
    try {
      payload = await response.json()
    } catch {
      /* the body was not JSON - keep null */
    }
    const detail = (payload as { detail?: unknown })?.detail ?? payload
    throw new ApiError(response.status, friendlyMessage(response.status, payload), detail)
  }

  if (response.status === 204) return undefined as T
  const contentType = response.headers.get('content-type') ?? ''
  if (!contentType.includes('application/json')) return (await response.blob()) as T
  return (await response.json()) as T
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body),
  put: <T>(path: string, body?: unknown) => request<T>('PUT', path, body),
  delete: <T>(path: string) => request<T>('DELETE', path),
}

/** Download a PDF the browser way, keeping the session cookie attached. */
export async function downloadFile(path: string, filename: string): Promise<void> {
  const response = await fetch(path, { credentials: 'same-origin' })
  if (!response.ok) {
    throw new ApiError(response.status, friendlyMessage(response.status, null), null)
  }
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
