// Upload button and job queue panel of the right-hand column.
//
// The button saves the session, then queues every match that is not locked
// and has no problem. The panel polls GET /api/jobs: every second while a job
// is queued or running, every 10 s otherwise. Each poll reports the locked
// match ids (every match with a job, plus those being queued right now) so
// the timeline, the shortcuts and the cards follow the queue.

import * as api from './api.js';
import { matchProblems } from './model.js';

const FAST_MS = 1000;
const SLOW_MS = 10000;

const STEP_LABELS = {
  metadata: 'Tạo thông tin',
  select_thumbnail: 'Chọn thumbnail',
  render_thumbnail: 'Vẽ thumbnail',
  encode: 'Đang encode',
  upload: 'Đang upload',
  set_thumbnail: 'Đặt thumbnail',
  cleanup: 'Lưu trữ',
};
const WITH_PERCENT = new Set(['encode', 'upload']);

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

// Same as the title preview without tournament and date: "Nam/Hùng vs Tú/Long".
export const jobTitle = (match) => `${match.team1.join('/')} vs ${match.team2.join('/')}`;

const percentOf = (job) => (WITH_PERCENT.has(job.step) ? Math.max(0, Math.min(100, Math.floor(job.progress || 0))) : 0);

function statusText(job) {
  if (job.status === 'queued') return 'Đang chờ';
  if (job.status === 'waiting_quota') return 'Chờ quota YouTube, sẽ tự thử lại';
  if (job.status === 'error') return `Lỗi · ${STEP_LABELS[job.step] ?? job.step}`;
  const label = STEP_LABELS[job.step] ?? job.step;
  return WITH_PERCENT.has(job.step) ? `${label} ${percentOf(job)}%` : label;
}

const safeLink = (url) => (typeof url === 'string' && /^https:\/\//.test(url) ? url : null);

// `els`: {go, note, panel}. `deps`: {getState, getLocked, getOpenMatchId,
// isStale, isSignedIn, saveNow, onLocked(ids), onDone(), onSignedOut()}.
export function createQueue(els, deps, initialJobs) {
  const { go, note, panel } = els;
  let jobs = [];
  let statuses = null; // match id -> status at the previous poll
  const pending = new Set(); // ids being queued right now
  const acting = new Set(); // ids with a retry/unqueue request in flight
  const rowErrors = new Map(); // id -> message of a refused action
  const rows = new Map(); // id -> {el, html}
  let busy = false;
  let goError = null; // {text, detail, n}: the last enqueue failure
  let timer = 0;
  let seq = 0;
  let applied = 0;
  let lockKey = null;

  panel.innerHTML = '<h4>Hàng đợi</h4><div class="jobs"></div><p class="hint empty">Chưa có trận nào trong hàng đợi.</p>';
  const list = panel.querySelector('.jobs');
  const empty = panel.querySelector('.empty');

  // ---------------------------------------------------------------- locks

  function publishLocks() {
    const ids = [...new Set([...jobs.map((j) => j.match.id), ...pending])].sort();
    const key = ids.join('\n');
    if (key === lockKey) return;
    lockKey = key;
    deps.onLocked(ids);
  }

  function applyJobs(next) {
    let finished = false;
    if (statuses) {
      for (const j of next) if (j.status === 'done' && statuses.get(j.match.id) !== 'done') finished = true;
    }
    statuses = new Map(next.map((j) => [j.match.id, j.status]));
    jobs = next;
    renderRows();
    publishLocks();
    renderGo();
    if (finished) deps.onDone();
  }

  // ---------------------------------------------------------------- polling

  const active = () => jobs.some((j) => j.status === 'queued' || j.status === 'running');

  // Responses that come back after a newer one are dropped.
  async function refresh() {
    const n = ++seq;
    try {
      const next = await api.listJobs();
      if (n > applied) {
        applied = n;
        applyJobs(next);
      }
    } catch {
      // Keep the last list; the next poll tries again.
    }
  }

  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(tick, active() ? FAST_MS : SLOW_MS);
  }

  async function tick() {
    timer = 0;
    await refresh();
    schedule();
  }

  async function refreshNow() {
    await refresh();
    schedule();
  }

  // ---------------------------------------------------------------- rows

  function rowHtml(job) {
    const id = job.match.id;
    const cls = ['job'];
    if (job.status === 'done') cls.push('done');
    if (job.status === 'error') cls.push('error');
    if (job.status === 'waiting_quota') cls.push('wait');
    const title = esc(jobTitle(job.match));
    let span;
    if (job.status === 'done') {
      const link = safeLink(job.youtube_link);
      span = link
        ? `<a href="${esc(link)}" target="_blank" rel="noopener noreferrer">✓ Xong · mở YouTube</a>`
        : '✓ Xong';
    } else {
      span = esc(statusText(job));
    }
    let html = `<div class="nm"><em class="t" title="${title}">${title}</em><span>${span}</span></div>`;
    if (job.status !== 'done') html += `<div class="bar"><div style="width:${percentOf(job)}%"></div></div>`;
    if (job.status === 'error' && job.error) html += `<div class="msg">${esc(job.error)}</div>`;
    const buttons = [];
    const dis = acting.has(id) ? ' disabled' : '';
    if (job.status === 'error' || job.status === 'waiting_quota') {
      buttons.push(`<button type="button" data-act="retry"${dis}>Thử lại</button>`);
    }
    if (job.status === 'error' || job.status === 'queued') {
      buttons.push(`<button type="button" data-act="unqueue"${dis}>Đưa về chỉnh sửa</button>`);
    }
    if (buttons.length) html += `<div class="acts">${buttons.join('')}</div>`;
    if (rowErrors.has(id)) html += `<div class="msg">${esc(rowErrors.get(id))}</div>`;
    return { cls: cls.join(' '), html };
  }

  // Rows are patched one by one, so a button the user is about to click is
  // not replaced because another row's percentage moved.
  function renderRows() {
    const seen = new Set();
    jobs.forEach((job, i) => {
      const id = job.match.id;
      seen.add(id);
      const { cls, html } = rowHtml(job);
      let row = rows.get(id);
      if (!row) {
        const el = document.createElement('div');
        el.dataset.id = id;
        row = { el, html: null, cls: null };
        rows.set(id, row);
      }
      if (row.html !== html) row.el.innerHTML = html;
      if (row.cls !== cls) row.el.className = cls;
      row.html = html;
      row.cls = cls;
      if (list.children[i] !== row.el) list.insertBefore(row.el, list.children[i] ?? null);
    });
    for (const [id, row] of rows) {
      if (!seen.has(id)) {
        row.el.remove();
        rows.delete(id);
        rowErrors.delete(id);
      }
    }
    empty.hidden = jobs.length > 0;
  }

  async function act(kind, id) {
    if (acting.has(id)) return;
    acting.add(id);
    rowErrors.delete(id);
    renderRows();
    try {
      await (kind === 'retry' ? api.retry(id) : api.unqueue(id));
    } catch (err) {
      rowErrors.set(id, err.message);
    } finally {
      acting.delete(id);
    }
    renderRows();
    await refreshNow();
  }

  panel.addEventListener('click', (e) => {
    const button = e.target.closest('button[data-act]');
    if (!button) return;
    button.blur();
    const id = button.closest('.job')?.dataset.id;
    if (id) act(button.dataset.act, id);
  });

  // ---------------------------------------------------------------- button

  function eligibleIds() {
    const locked = deps.getLocked();
    const openId = deps.getOpenMatchId();
    return deps.getState().session.matches
      .filter((m) => !locked.has(m.id) && matchProblems(m, openId).length === 0)
      .map((m) => m.id);
  }

  function renderGo() {
    const n = eligibleIds().length;
    const signedIn = deps.isSignedIn();
    const stale = deps.isStale();
    // An enqueue error stays until the number of matches ready to go changes
    // (counted at the first render after the attempt, once its locks are gone).
    if (goError && !busy) {
      if (goError.n === null) goError.n = n;
      else if (n !== goError.n) goError = null;
    }
    go.textContent = busy ? 'Đang đưa vào hàng đợi…' : `Xử lý & upload ${n} trận đã đủ thông tin`;
    go.disabled = busy || n === 0 || !signedIn || stale;
    let text = '';
    let detail = '';
    if (stale) {
      text = 'Tải lại trang trước khi upload: phiên đã đổi ở tab khác';
    } else if (goError) {
      text = goError.text;
      detail = goError.detail;
    } else if (!signedIn) {
      text = 'Cần đăng nhập YouTube';
    }
    if (note.textContent !== text) note.textContent = text;
    note.title = detail;
    note.classList.toggle('err', !!goError || stale);
  }

  async function enqueue() {
    if (busy || !deps.isSignedIn() || deps.isStale()) return;
    const ids = eligibleIds();
    if (ids.length === 0) return;
    busy = true;
    goError = null;
    // Lock them here first, so nothing changes them between the save and
    // the server taking its copy.
    ids.forEach((id) => pending.add(id));
    publishLocks();
    renderGo();
    try {
      try {
        await deps.saveNow();
      } catch (err) {
        throw Object.assign(new Error(`Chưa lưu được phiên nên chưa đưa vào hàng đợi: ${err.message}`), {
          errors: err.errors,
        });
      }
      const created = await api.enqueue(ids);
      const added = new Set(created.map((j) => j.match.id));
      jobs = [...jobs.filter((j) => !added.has(j.match.id)), ...created];
      applied = ++seq; // older polls in flight do not know these jobs yet
    } catch (err) {
      goError = { text: err.message, detail: (err.errors || [err.message]).join('\n'), n: null };
      // The server says we are signed out: show the sign-in button again.
      if (err.status === 409 && /đăng nhập/.test(err.message)) deps.onSignedOut();
    } finally {
      busy = false;
      pending.clear();
    }
    applyJobs(jobs);
    await refreshNow();
  }

  go.addEventListener('click', () => {
    go.blur();
    enqueue();
  });

  applyJobs(initialJobs);

  return {
    render: applyJobs,
    renderGo,
    refresh: refreshNow,
    startPolling: schedule,
  };
}
