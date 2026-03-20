import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react"
import { useNavigate } from "react-router-dom"
import {
  getToken,
  getMe,
  login as apiLogin,
  removeToken,
  setToken,
  type UserInfo,
} from "../lib/apiClient"

// ─── Context shape ────────────────────────────────────────────────────────
interface AuthContextType {
  user: UserInfo | null
  loading: boolean
  isAuthenticated: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
  /** Call when any API request receives a 401. Clears state and redirects. */
  handleUnauthorized: () => void
}

const AuthContext = createContext<AuthContextType | null>(null)

// ─── Provider ─────────────────────────────────────────────────────────────
interface AuthProviderProps {
  children: React.ReactNode
}

export function AuthProvider({ children }: AuthProviderProps): React.JSX.Element {
  const navigate = useNavigate()
  const [user, setUser]       = useState<UserInfo | null>(null)
  const [loading, setLoading] = useState(true)

  // On mount, validate any stored token by fetching /auth/me.
  useEffect(() => {
    const token = getToken()
    if (!token) {
      setLoading(false)
      return
    }
    getMe()
      .then(setUser)
      .catch(() => removeToken())
      .finally(() => setLoading(false))
  }, [])

  const login = useCallback(
    async (username: string, password: string): Promise<void> => {
      const { access_token } = await apiLogin(username, password)
      setToken(access_token)
      const me = await getMe()
      setUser(me)
      navigate("/", { replace: true })
    },
    [navigate]
  )

  const logout = useCallback((): void => {
    removeToken()
    setUser(null)
    navigate("/login", { replace: true })
  }, [navigate])

  const handleUnauthorized = useCallback((): void => {
    removeToken()
    setUser(null)
    navigate("/login", { replace: true })
  }, [navigate])

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        isAuthenticated: !!user,
        login,
        logout,
        handleUnauthorized,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

// ─── Hook ─────────────────────────────────────────────────────────────────
export function useAuth(): AuthContextType {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>")
  return ctx
}
