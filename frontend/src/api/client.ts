const API_BASE_URL = import.meta.env.VITE_API_BASE_URL

export class ApiError extends Error {
  readonly status: number

  constructor(
    status: number,
    message: string,
  ) {
    super(message)
    this.status = status
  }
}

async function apiRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    credentials: 'include',
    headers: {
      ...(options.body && !(options.body instanceof FormData)
        ? { 'Content-Type': 'application/json' }
        : {}),
      ...options.headers,
    },
  })

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`
    try {
      const body = (await response.json()) as { detail?: string }
      if (typeof body.detail === 'string') message = body.detail
    } catch {
      // Keep the status-based fallback for non-JSON errors.
    }
    throw new ApiError(response.status, message)
  }

  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export function apiGet<T>(path: string): Promise<T> {
  return apiRequest<T>(path)
}

export function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return apiRequest<T>(path, {
    method: 'POST',
    body: body === undefined ? undefined : JSON.stringify(body),
  })
}

export function apiPatch<T>(path: string, body: unknown): Promise<T> {
  return apiRequest<T>(path, { method: 'PATCH', body: JSON.stringify(body) })
}

export function apiUpload<T>(path: string, file: File): Promise<T> {
  const body = new FormData()
  body.append('file', file)
  return apiRequest<T>(path, { method: 'POST', body })
}
