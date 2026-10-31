const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');

export async function api(path, options = {}) {
  let response;
  try {
    response = await fetch(`${API_BASE}${path.startsWith('/api') ? path : `/api${path}`}`, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    });
  } catch {
    throw new Error(`Cannot reach the backend at ${API_BASE}. Check that FastAPI is running.`);
  }
  let body;
  try { body = await response.json(); } catch { body = null; }
  if (!response.ok) {
    const detail = body?.detail;
    throw new Error(typeof detail === 'string' ? detail : `Backend request failed (${response.status}).`);
  }
  return body;
}

export const apiBaseUrl = API_BASE;
