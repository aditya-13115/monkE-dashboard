const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export { API }

export async function apiJson(path, options = {}) {
  const response = await fetch(`${API}${path}`, {
    ...options,
    headers: {
      Accept: 'application/json',
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...(options.headers || {}),
    },
  })

  let payload = null
  try {
    payload = await response.json()
  } catch {
    payload = null
  }

  if (!response.ok) {
    throw new Error(payload?.detail || `Request failed (${response.status})`)
  }

  return payload
}

export const endpoints = {
  campaign: () => '/api/campaign',
  livePost: (id, force = false) => `/api/posts/${id}/live${force ? '?force=true' : ''}`,
  sentimentPost: (id, force = false) => `/api/sentiment/post/${id}${force ? '?force=true' : ''}`,
}
