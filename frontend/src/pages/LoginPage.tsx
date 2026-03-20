import React, { useState } from "react"
import { Navigate } from "react-router-dom"
import { useAuth } from "../context/AuthContext"
import { UnauthorizedError } from "../lib/apiClient"

export default function LoginPage(): React.JSX.Element {
  const { login, isAuthenticated } = useAuth()

  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError]       = useState("")
  const [loading, setLoading]   = useState(false)

  if (isAuthenticated) {
    return <Navigate to="/" replace />
  }

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>): Promise<void> {
    e.preventDefault()
    setError("")
    setLoading(true)
    try {
      await login(username, password)
    } catch (err) {
      if (err instanceof UnauthorizedError) {
        setError("Invalid username or password.")
      } else {
        setError(err instanceof Error ? err.message : "Something went wrong.")
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-card__logo">
          <div className="login-card__app-name">SaaS Debug Lab</div>
          <div className="login-card__subtitle">Distributed Systems Training Platform</div>
        </div>

        {error && <div className="alert alert--error">{error}</div>}

        <form onSubmit={handleSubmit} autoComplete="off">
          <div className="form-group">
            <label htmlFor="username">Username</label>
            <input
              id="username"
              className="form-control"
              type="text"
              value={username}
              onChange={e => setUsername(e.target.value)}
              placeholder="admin"
              autoFocus
              required
            />
          </div>

          <div className="form-group">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              className="form-control"
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="••••••••"
              required
            />
          </div>

          <button
            type="submit"
            className="btn btn--primary"
            style={{ width: "100%", justifyContent: "center", marginTop: 4 }}
            disabled={loading}
          >
            {loading && <span className="spinner" style={{ width: 16, height: 16 }} />}
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <p style={{ fontSize: "0.76rem", color: "var(--color-muted)", textAlign: "center", marginTop: 20 }}>
          Default credentials: <strong>admin / admin123</strong> or <strong>user / user123</strong>
        </p>
      </div>
    </div>
  )
}
