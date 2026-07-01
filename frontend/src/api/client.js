const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

export async function createTask(payload) {
  return request('/api/tasks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
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

export function openTaskEvents(taskId) {
  return new EventSource(`${API_BASE_URL}/api/tasks/${taskId}/events`)
}

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, options)
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new Error(data.detail || '请求失败')
  }
  return response.json()
}
