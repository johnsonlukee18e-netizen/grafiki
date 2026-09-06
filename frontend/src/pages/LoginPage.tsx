import { useSearchParams } from 'react-router-dom'

import { useAuthStatus, useDevLogin } from '../api/hooks'

export default function LoginPage() {
  const { data } = useAuthStatus()
  const devLogin = useDevLogin()
  const [params] = useSearchParams()
  const error = params.get('error')

  return (
    <div className="container" style={{ maxWidth: 460 }}>
      <div className="card shadow-sm mt-5">
        <div className="card-body p-4 text-center">
          <i className="bi bi-hospital fs-1 text-primary" />
          <h1 className="h4 mt-2 mb-1">Grafiki pielegniarek</h1>
          <p className="text-secondary small mb-4">
            Zaloguj sie kontem Google, aby zarzadzac grafikami oddzialu.
          </p>

          {error && (
            <div className="alert alert-danger text-start small" role="alert">
              <i className="bi bi-exclamation-triangle me-1" />
              {error}
            </div>
          )}

          {data?.oauth_configured ? (
            <a className="btn btn-primary w-100" href="/api/auth/google">
              <i className="bi bi-google me-2" />
              Zaloguj przez Google
            </a>
          ) : (
            <div className="alert alert-warning text-start small mb-0" role="alert">
              Logowanie Google nie jest jeszcze skonfigurowane. Ustaw
              <code className="mx-1">GOOGLE_CLIENT_ID</code> i
              <code className="mx-1">GOOGLE_CLIENT_SECRET</code>
              w pliku <code>.env</code>, a nastepnie zrestartuj backend.
            </div>
          )}

          {data?.dev_auth_enabled && (
            <>
              <hr />
              <div className="small text-secondary mb-2">
                Tryb deweloperski (niedostepny w produkcji)
              </div>
              <button
                className="btn btn-outline-secondary w-100"
                onClick={() => devLogin.mutate()}
                disabled={devLogin.isPending}
                type="button"
              >
                <i className="bi bi-terminal me-2" />
                Zaloguj lokalnie jako administrator
              </button>
              {devLogin.isError && (
                <div className="text-danger small mt-2">
                  {(devLogin.error as Error).message}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
