// HTTP calls to the local server (app/server.py), one function per route.
// Every failure throws an Error whose message is the server's first error;
// `err.errors` holds them all, `err.status` the HTTP status (0 = network) and
// `err.code` the server's machine-readable code, if any.

// The server refuses changes without this header, so another website cannot
// make the browser change anything here (app/server.py, EDITOR_HEADER).
const EDITOR_HEADER = { 'X-Cafe-Editor': '1' };

async function request(method, path, body, { keepalive = false } = {}) {
  const init = { method, keepalive, headers: { ...EDITOR_HEADER } };
  if (body !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(path, init);
  } catch {
    throw apiError(0, ['Không kết nối được với máy chủ']);
  }
  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    const errors = Array.isArray(data?.errors) && data.errors.length > 0
      ? data.errors
      : [`Lỗi máy chủ (${res.status})`];
    throw apiError(res.status, errors, typeof data?.code === 'string' ? data.code : null);
  }
  return data;
}

function apiError(status, errors, code = null) {
  const err = new Error(errors[0]);
  err.errors = errors;
  err.status = status;
  err.code = code;
  return err;
}

const part = (s) => encodeURIComponent(s);

export const bootstrap = () => request('GET', '/api/bootstrap');
export const listSources = () => request('GET', '/api/sources');
// `keepalive` lets the request outlive the page (used when the tab closes).
export const saveSession = (session, opts) => request('PUT', '/api/session', session, opts);
export const listJobs = () => request('GET', '/api/jobs');
export const setMode = (mode) => request('PUT', '/api/mode', { mode });
export const enqueue = (ids, mode) => request('POST', '/api/jobs', { match_ids: ids, mode });
export const retry = (id) => request('POST', `/api/jobs/${part(id)}/retry`);
export const unqueue = (id) => request('POST', `/api/jobs/${part(id)}/unqueue`);
export const archiveSource = (name) => request('POST', `/api/sources/${part(name)}/archive`);
export const authStatus = () => request('GET', '/api/auth');
export const login = () => request('POST', '/api/auth/login');

export const mediaUrl = (name) => `/media/${part(name)}`;
