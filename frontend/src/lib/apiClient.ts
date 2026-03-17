const API_URL =
  import.meta.env.VITE_API_URL ||
  "http://localhost:8000"

type RequestOptions = RequestInit & {
  params?: Record<string, string>
}

function buildUrl(path: string, params?: Record<string, string>) {
  const url = new URL(`${API_URL}${path}`)

  if (params) {
    Object.entries(params).forEach(([key, value]) =>
      url.searchParams.append(key, value)
    )
  }

  return url.toString()
}

export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {}
): Promise<T> {

  const response = await fetch(buildUrl(path, options.params), {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    },
    ...options
  })

  if (!response.ok) {
    const text = await response.text()

    console.error("API error", {
      path,
      status: response.status,
      body: text
    })

    throw new Error(`API error ${response.status}`)
  }

  return response.json()
}