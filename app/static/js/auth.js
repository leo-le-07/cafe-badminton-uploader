// YouTube sign-in control in the top bar: "● YouTube đã đăng nhập · <kênh>",
// or a sign-in button that starts the server's OAuth flow and polls
// /api/auth every 2 s while the attempt is in progress.

import * as api from './api.js';

const POLL_MS = 2000;
const FOCUS_CHECK_MS = 60000; // re-check on window focus at most once a minute

// `auth` is the bootstrap/`GET /api/auth` dict {ok, channel, login}.
// `onChange(auth)` is called whenever a new auth dict arrives.
export function createAuth(container, auth, onChange) {
  let current = auth;
  let timer = 0;
  let error = ''; // a failure of our own request, shown like login.error

  function render() {
    const login = current.login || {};
    container.replaceChildren();
    const pill = document.createElement('span');
    pill.className = 'pill';
    if (current.ok) {
      pill.classList.add('ok');
      pill.textContent = current.channel
        ? `● YouTube đã đăng nhập · ${current.channel}`
        : '● YouTube đã đăng nhập';
      container.append(pill);
      return;
    }
    pill.classList.add('bad');
    pill.textContent = '○ YouTube chưa đăng nhập';
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'login';
    button.disabled = !!login.in_progress;
    button.textContent = login.in_progress ? 'Đang chờ đăng nhập trên trình duyệt…' : 'Đăng nhập YouTube';
    button.addEventListener('click', start);
    container.append(pill, button);
    const message = error || (!login.in_progress && login.error) || '';
    if (message) {
      const span = document.createElement('span');
      span.className = 'login-error';
      span.textContent = message;
      span.title = message;
      container.append(span);
    }
  }

  function set(next) {
    current = next;
    render();
    onChange(current);
  }

  async function poll() {
    timer = 0;
    try {
      const next = await api.authStatus();
      error = '';
      set(next);
    } catch (err) {
      error = err.message;
      render();
    }
    if (current.login && current.login.in_progress) timer = setTimeout(poll, POLL_MS);
  }

  async function start(e) {
    e.currentTarget.blur();
    error = '';
    current = { ...current, login: { in_progress: true, error: null } };
    render();
    try {
      await api.login();
    } catch (err) {
      error = err.message;
      current = { ...current, login: { in_progress: false, error: null } };
      render();
      return;
    }
    clearTimeout(timer);
    timer = setTimeout(poll, POLL_MS);
  }

  // Fetches the sign-in state again, e.g. after the server said we are
  // signed out, so an expired token shows the sign-in button.
  let lastCheck = Date.now();
  async function refresh() {
    lastCheck = Date.now();
    if (timer) return; // an attempt is being followed already
    try {
      const next = await api.authStatus();
      error = '';
      set(next);
      if (current.login && current.login.in_progress && !timer) timer = setTimeout(poll, POLL_MS);
    } catch {
      // Keep what is shown; the next check tries again.
    }
  }

  window.addEventListener('focus', () => {
    if (Date.now() - lastCheck >= FOCUS_CHECK_MS) refresh();
  });

  render();
  // A reload while an attempt is running keeps following it.
  if (current.login && current.login.in_progress) timer = setTimeout(poll, POLL_MS);

  return {
    get: () => current,
    refresh,
  };
}
