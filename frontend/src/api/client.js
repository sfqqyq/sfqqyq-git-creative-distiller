const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

export async function createTask(payload) {
  return request('/api/tasks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function login(payload) {
  return request('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function logout() {
  return request('/api/auth/logout', {
    method: 'POST',
  })
}

export async function fetchCurrentUser() {
  return request('/api/auth/me')
}

export async function fetchTasks() {
  return request('/api/tasks')
}

export async function fetchTask(taskId) {
  return request(`/api/tasks/${taskId}`)
}

export async function fetchReport(taskId) {
  return request(`/api/tasks/${taskId}/report`)
}

export async function createIncrementalTask(taskId, payload = {}) {
  return request(`/api/tasks/${taskId}/incremental`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function deleteTask(taskId) {
  return request(`/api/tasks/${taskId}`, {
    method: 'DELETE',
  })
}

export async function deleteCreativePoint(pointId) {
  return request(`/api/creative-points/${pointId}`, {
    method: 'DELETE',
  })
}

export async function generateCreativePointImagePrompt(pointId) {
  return request(`/api/creative-points/${pointId}/image-prompt`, {
    method: 'POST',
  })
}

export async function generateCreativePointImage(pointId, payload) {
  return request(`/api/creative-points/${pointId}/image`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function openTaskEvents(taskId) {
  return new EventSource(`${API_BASE_URL}/api/tasks/${taskId}/events`, { withCredentials: true })
}

async function request(path, options = {}) {
  const method = options.method || 'GET'
  const requestOptions = method === 'GET' ? { cache: 'no-store', ...options } : { ...options }
  requestOptions.credentials = 'include'
  const url = method === 'GET' ? withCacheBuster(path) : path
  const response = await fetch(`${API_BASE_URL}${url}`, requestOptions)
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new Error(data.detail || '请求失败')
  }
  return response.json()
}

function withCacheBuster(path) {
  const separator = path.includes('?') ? '&' : '?'
  return `${path}${separator}_t=${Date.now()}`
}
