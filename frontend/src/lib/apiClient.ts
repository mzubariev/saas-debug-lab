const API_URL = import.meta.env.VITE_API_URL || "http://localhost"

// ─── Token helpers ────────────────────────────────────────────────────────
export const TOKEN_KEY = "saas_debug_token"

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

export function removeToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

// ─── Types ────────────────────────────────────────────────────────────────
export type TaskStatus = "created" | "in_progress" | "completed"

export interface Task {
  id: string
  title: string
  status: TaskStatus
  created_at: string
  updated_at: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
}

export interface UserInfo {
  username: string
  role: string
}

// Thrown on HTTP 401 so callers (AuthContext) can react by logging out.
export class UnauthorizedError extends Error {
  constructor() {
    super("Unauthorized")
    this.name = "UnauthorizedError"
  }
}

// ─── Core request ─────────────────────────────────────────────────────────
type RequestOptions = RequestInit & {
  params?: Record<string, string>
}

function buildUrl(path: string, params?: Record<string, string>): string {
  const url = new URL(`${API_URL}${path}`)
  if (params) {
    Object.entries(params).forEach(([k, v]) => url.searchParams.append(k, v))
  }
  return url.toString()
}

export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {}
): Promise<T> {
  const token = getToken()
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> ?? {}),
  }
  if (token) {
    headers["Authorization"] = `Bearer ${token}`
  }

  const { params, ...rest } = options
  const response = await fetch(buildUrl(path, params), { ...rest, headers })

  if (response.status === 401) {
    throw new UnauthorizedError()
  }

  if (!response.ok) {
    let detail = `API error ${response.status}`
    try {
      const body = await response.json()
      detail = body?.detail ?? detail
    } catch {
      // ignore parse failures
    }
    throw new Error(detail)
  }

  return response.json()
}

// ─── Auth ─────────────────────────────────────────────────────────────────
// The auth endpoint uses OAuth2PasswordRequestForm (form-encoded), not JSON.
export async function login(
  username: string,
  password: string
): Promise<TokenResponse> {
  const body = new URLSearchParams({ username, password })
  const response = await fetch(buildUrl("/auth/token"), {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
  })

  if (response.status === 401) throw new UnauthorizedError()
  if (!response.ok) throw new Error(`Login failed (${response.status})`)

  return response.json()
}

export function getMe(): Promise<UserInfo> {
  return apiRequest<UserInfo>("/auth/me")
}

// ─── Tasks ────────────────────────────────────────────────────────────────
export function getTasks(): Promise<Task[]> {
  return apiRequest<Task[]>("/tasks")
}

export function createTask(title: string): Promise<Task> {
  return apiRequest<Task>("/tasks", {
    method: "POST",
    body: JSON.stringify({ title }),
  })
}

export function startTask(id: string): Promise<Task> {
  return apiRequest<Task>(`/tasks/${id}/start`, { method: "PATCH" })
}

export function completeTask(id: string): Promise<Task> {
  return apiRequest<Task>(`/tasks/${id}/complete`, { method: "PATCH" })
}
