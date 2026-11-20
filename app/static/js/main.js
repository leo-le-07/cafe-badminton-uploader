// Editor page: holds the state, wires the player, timeline and source list,
// handles the keyboard and autosaves the session.
//
// Exports: getState(), dispatch(fn), subscribe(listener), getBootstrap(),
//   getLocked(), setLocked(ids), getOpenMatchId(), getPlayhead(), seek(t),
//   onEnterKey(handler), saveNow(), matchColor(index)
// The right-hand column (matches.js, queue.js) and the sign-in control
// (auth.js) are created here once the bootstrap data has arrived.

import * as api from './api.js';
import { createAuth } from './auth.js';
import { createModeState, createModeToggle } from './mode.js';
import { esc, formatLength, pad } from './format.js';
import { createMatches } from './matches.js';
import {
  addSource,
  buildLayout,
  deleteSegmentAt,
  editorFromStored,
  markIn,
  markOut,
  moveEdge,
  newMatch,
  removeSource,
  selectMatch,
  storedSession,
  undo,
} from './model.js';
import { createPlayer, formatTimecode } from './player.js';
import { createQueue } from './queue.js';
import { isStaleSessionError, isTransientSaveError, saveRetryDelay } from './save.js';
import { createTimeline, matchColor } from './timeline.js';

export { matchColor };

const SAVE_DELAY_MS = 1000;

let boot = null;
let state = null;
let revision = 0; // revision of the stored session this tab is based on
let hiddenOpen = null; // stored open point whose file is not on the timeline
let staleError = null; // set once another tab saved: this tab saves nothing more
let locked = new Set();
let player = null;
let timeline = null;
let enterHandler = null;
let auth = null;
let matchesView = null;
let queue = null;
const listeners = new Set();

const $ = (id) => document.getElementById(id);

// ---------------------------------------------------------------- public API

export const getState = () => state;
export const getBootstrap = () => boot;
export const getLocked = () => locked;
// The match that owns the open segment (shown or not), or null.
export const getOpenMatchId = () => storedSession(state, hiddenOpen).open?.match_id ?? null;
export const getPlayhead = () => (player ? player.time() : 0);
export const seek = (t) => player && player.seek(t);

// Applies fn(state) -> state. A no-op returns the same object and does nothing.
export function dispatch(fn) {
  const next = fn(state);
  if (next && next !== state) setState(next);
  return state;
}

export function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

// Ids of matches that are queued, running or done (no editing allowed).
// queue.js sets them from every poll of the job list.
export function setLocked(ids) {
  const next = new Set(ids);
  if (next.size === locked.size && [...next].every((id) => locked.has(id))) return;
  locked = next;
  renderAll();
}

// Hook for `Enter`: focus the first team input of the selected match.
export function onEnterKey(handler) {
  enterHandler = handler;
}

function setState(next) {
  const prev = state;
  state = next;
  if (next.layout !== prev.layout) player.setLayout(next.layout);
  if (next.session !== prev.session || next.open !== prev.open) scheduleSave();
  renderAll();
}

function renderAll() {
  if (!state) return;
  renderSources();
  renderPlayhead();
  for (const listener of listeners) listener(state);
}

// ---------------------------------------------------------------- top bar

function setSaveStatus(kind, text, detail = '') {
  const pill = $('save-pill');
  pill.textContent = text;
  pill.title = detail;
  pill.classList.toggle('bad', kind === 'error');
}

// ---------------------------------------------------------------- sources

const readableInfos = () => boot.sources.filter((s) => !s.missing && !s.unreadable);
// Source name -> recording date (YYYY-MM-DD) for the title preview.
const recordedDates = () => Object.fromEntries(
  boot.sources.filter((s) => s.recorded_at).map((s) => [s.name, s.recorded_at.slice(0, 10)]),
);
const circled = (i) => String.fromCharCode(0x2460 + i);

function formatRecorded(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const day = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = Math.round((day(new Date()) - day(d)) / 86400000);
  const clock = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  if (diff === 0) return `hôm nay ${clock}`;
  if (diff === 1) return `hôm qua ${clock}`;
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)} ${clock}`;
}

function renderSources() {
  const order = state.layout.map((e) => e.name);
  const inSession = new Set(state.session.sources);
  $('sources').innerHTML = boot.sources.map((s) => {
    const on = inSession.has(s.name);
    const idx = order.indexOf(s.name);
    let info;
    if (s.missing) info = 'Không tìm thấy file';
    else if (s.unreadable) info = 'Không đọc được file';
    else info = [formatLength(s.duration), formatRecorded(s.recorded_at)].filter(Boolean).join(' · ');
    const cls = ['src', on ? 'on' : '', s.missing || s.unreadable ? 'missing' : ''].join(' ');
    const chk = idx >= 0 ? `<span class="chk">${circled(idx)}</span>` : on ? '<span class="chk">✕</span>' : '';
    const arch = s.archivable
      ? `<button type="button" class="arch"${staleError ? ' disabled' : ''}>Lưu trữ</button>`
      : '';
    return `<div class="${cls}" role="checkbox" aria-checked="${on}" data-name="${esc(s.name)}">${chk}${esc(s.name)}<small>${info}</small>${arch}</div>`;
  }).join('');
}

function toggleSource(name) {
  const info = boot.sources.find((s) => s.name === name);
  if (!info) return;
  if (!state.session.sources.includes(name)) {
    if (info.missing || info.unreadable) return;
    dispatch((s) => addSource(s, name, readableInfos()));
    return;
  }
  const used = state.session.matches.some((m) => m.segments.some((seg) => seg.source === name));
  if (used && !window.confirm(`Bỏ ${name} khỏi timeline? Các đoạn đã đánh dấu trong file này sẽ bị xoá.`)) return;
  const before = state;
  dispatch((s) => removeSource(s, name, locked));
  if (state === before) window.alert(`Không bỏ được ${name}: có trận đang trong hàng đợi dùng file này.`);
}

// Archiving moves the file out of INPUT_DIR and drops it from the stored
// session, so the editor is reloaded from the server afterwards.
async function archiveSource(name) {
  if (staleError) return;
  if (!window.confirm('Chuyển file gốc sang thư mục lưu trữ?')) return;
  try {
    await saveNow();
    await api.archiveSource(name);
  } catch (err) {
    window.alert(`Không lưu trữ được ${name}: ${err.message}`);
    return;
  }
  await reload();
}

async function refreshSources() {
  try {
    boot.sources = await api.listSources();
  } catch {
    return; // the next finished job or reload tries again
  }
  renderSources();
  renderMatches();
}

// ---------------------------------------------------------------- player overlay

let lastHold = '';

function renderPlayhead() {
  const t = player.time();
  const total = state.layout.reduce((a, e) => a + e.duration, 0);
  $('tc').textContent = `${formatTimecode(state.layout, t)} / ${formatTimecode(state.layout, total)}`;
  const open = state.open;
  const index = open ? state.session.matches.findIndex((m) => m.id === open.matchId) : -1;
  const hold = index >= 0 ? `● ĐANG GIỮ · Trận ${index + 1}` : '○ Không giữ';
  if (hold !== lastHold) {
    const el = $('hold');
    el.textContent = hold;
    el.classList.toggle('off', index < 0);
    el.style.background = index >= 0 ? matchColor(index) : '';
    lastHold = hold;
  }
  $('player').classList.toggle('empty', state.layout.length === 0);
  timeline.render(state, state.layout, t, { locked });
}

// ---------------------------------------------------------------- timeline intents

let edgeBase = null;

function onMoveEdge(matchId, segIndex, edge, t, phase) {
  if (phase === 'start') edgeBase = state;
  if (!edgeBase) return;
  if (phase === 'end') {
    edgeBase = null;
    return;
  }
  // Every move starts again from the state before the drag, so one drag is
  // one undo step.
  const next = moveEdge(edgeBase, matchId, segIndex, edge, t, locked);
  if (next !== state) setState(next);
  const m = next.session.matches.find((x) => x.id === matchId);
  const seg = m && m.segments[segIndex];
  const entry = seg && next.layout.find((e) => e.name === seg.source);
  if (entry) player.seek(entry.offset + seg[edge]);
}

// ---------------------------------------------------------------- keyboard

function isTyping(el) {
  if (!el || el === document.body) return false;
  if (el.isContentEditable || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT') return true;
  if (el.tagName !== 'INPUT') return false;
  return !['range', 'checkbox', 'radio', 'button', 'submit'].includes(el.type);
}

// Controls whose own Enter/Space action must win over the editor shortcut.
const ACTIVATABLE = 'button, a[href], input[type=checkbox], [role=button], [role=checkbox]';

function onKey(e) {
  if (!state) return;
  if (e.isComposing || e.keyCode === 229) return; // the IME owns this key, Esc included
  if (isTyping(document.activeElement)) {
    if (e.key === 'Escape') {
      document.activeElement.blur();
      e.preventDefault();
    }
    return;
  }
  const t = player.time();
  const mod = e.metaKey || e.ctrlKey;
  if (mod && !e.shiftKey && !e.altKey && e.code === 'KeyZ') {
    e.preventDefault();
    dispatch((s) => undo(s, locked));
    return;
  }
  if (mod || e.altKey) return;
  // Enter/Space on a focused button, link or checkbox activate it natively
  // (and Space then does not also toggle playback).
  if (['Enter', 'NumpadEnter', 'Space'].includes(e.code) && e.target instanceof Element && e.target.closest(ACTIVATABLE)) {
    return;
  }

  const once = !e.repeat;
  const has = state.layout.length > 0; // I/O/N/Delete need a ticked source
  const actions = {
    KeyI: () => once && has && dispatch((s) => markIn(s, t, undefined, locked)),
    KeyO: () => once && has && dispatch((s) => markOut(s, t, locked)),
    KeyN: () => once && has && dispatch((s) => newMatch(s, t, undefined, locked)),
    Space: () => once && player.toggle(),
    KeyJ: () => once && player.shuttle(-1),
    KeyK: () => once && player.shuttle(0),
    KeyL: () => once && player.shuttle(1),
    ArrowLeft: () => player.seek(Math.max(0, t - (e.shiftKey ? 10 : 1))),
    ArrowRight: () => player.seek(t + (e.shiftKey ? 10 : 1)),
    Comma: () => player.step(-1),
    Period: () => player.step(1),
    Equal: () => timeline.zoomBy(10),
    NumpadAdd: () => timeline.zoomBy(10),
    Minus: () => timeline.zoomBy(-10),
    NumpadSubtract: () => timeline.zoomBy(-10),
    Enter: () => once && enterHandler && enterHandler(state.session.selected_match_id),
    NumpadEnter: () => once && enterHandler && enterHandler(state.session.selected_match_id),
    Delete: () => has && dispatch((s) => deleteSegmentAt(s, t, locked)),
    Backspace: () => has && dispatch((s) => deleteSegmentAt(s, t, locked)),
  };
  const action = actions[e.code];
  if (!action) return;
  e.preventDefault();
  if (document.activeElement && document.activeElement !== document.body) document.activeElement.blur();
  action();
}

// ---------------------------------------------------------------- autosave

// What gets saved is the session plus the open segment; a "version" is the
// pair, compared by identity.
const current = () => ({ session: state.session, open: state.open });
const isCurrent = (v) => !!v && v.session === state.session && v.open === state.open;

let saved = null; // last version the server accepted
let attempted = null; // last version the server refused (400/409); never re-sent
let saveTimer = 0;
let saving = null; // promise of the save in flight
let saveError = null; // error of the last failed save
let failed = null; // version whose last save failed transiently (network, 5xx)
let retries = 0; // automatic retries of `failed` so far

function scheduleSave() {
  if (staleError) return;
  clearTimeout(saveTimer);
  retries = 0;
  saveTimer = setTimeout(flushSave, SAVE_DELAY_MS);
  if (!saving) setSaveStatus('saving', 'Đang lưu…');
}

// Another tab saved since this one loaded. Nothing more is saved from here,
// and the upload and archive buttons stay off until the page is reloaded.
function markStale(err) {
  staleError = err;
  clearTimeout(saveTimer);
  saveTimer = 0;
  setSaveStatus('error', 'Chưa lưu: phiên đã đổi ở tab khác', err.message);
  $('stale-text').textContent = `${err.message} Những thay đổi ở tab này từ lúc đó chưa được lưu.`;
  $('stale').hidden = false;
  renderSources();
  if (queue) queue.renderGo();
}

async function flushSave(opts) {
  clearTimeout(saveTimer);
  saveTimer = 0;
  if (staleError) return;
  // Never two saves at once: the one in flight saves again when it ends.
  if (saving) return;
  if (isCurrent(saved)) {
    setSaveStatus('ok', 'Đã lưu');
    return;
  }
  if (isCurrent(attempted)) return; // refused; wait for a change
  const version = current();
  const body = { ...storedSession(state, hiddenOpen), revision };
  setSaveStatus('saving', 'Đang lưu…');
  saving = api.saveSession(body, opts).then(
    (res) => {
      revision = res.revision;
      saved = version;
      saveError = null;
      failed = null;
      retries = 0;
      if (isCurrent(saved)) setSaveStatus('ok', 'Đã lưu');
    },
    (err) => {
      saveError = err;
      if (isStaleSessionError(err)) {
        attempted = version;
        markStale(err);
        return;
      }
      const detail = (err.errors || [err.message]).join('\n');
      if (!isTransientSaveError(err)) {
        attempted = version;
        setSaveStatus('error', `Lưu thất bại: ${err.message}`, detail);
        return;
      }
      // Transient: try the same version again by itself after a backoff.
      failed = version;
      setSaveStatus('error', `Lưu thất bại: ${err.message} · sẽ thử lại`, detail);
      if (isCurrent(version)) {
        clearTimeout(saveTimer);
        saveTimer = setTimeout(flushSave, saveRetryDelay(retries));
        retries += 1;
      }
    },
  );
  await saving;
  saving = null;
  if (!isCurrent(version)) await flushSave(opts);
}

// Saves now and resolves once the server holds the current version; throws
// the server's error when the save fails. A refused version (400/409) is not
// re-sent; a transient failure always gets one fresh attempt here. Used
// before enqueue and archive, which act on the stored session.
export async function saveNow() {
  let tried = false;
  while (!isCurrent(saved)) {
    if (staleError) throw staleError;
    if (saving) {
      await saving;
      continue;
    }
    if (isCurrent(attempted)) throw saveError;
    if (tried && isCurrent(failed)) throw saveError;
    tried = true;
    await flushSave();
  }
}

function flushOnLeave() {
  if (state && !staleError && !isCurrent(saved) && !isCurrent(attempted) && !saving) {
    flushSave({ keepalive: true });
  }
}

// ---------------------------------------------------------------- bootstrap

// (Re)builds the editor from a bootstrap payload. Undo history starts over.
// The tab now holds the server's current session and revision, so it is no
// longer stale: saving, upload and archive work again.
function load(data) {
  boot = data;
  const infos = new Map(readableInfos().map((s) => [s.name, s]));
  const layout = buildLayout(boot.session.sources.filter((n) => infos.has(n)).map((n) => infos.get(n)));
  ({ state, hiddenOpen } = editorFromStored(boot.session, layout, boot.defaults));
  revision = boot.session.revision ?? 0;
  saved = current();
  attempted = null;
  failed = null;
  retries = 0;
  clearTimeout(saveTimer);
  staleError = null;
  $('stale').hidden = true;
  locked = new Set(boot.jobs.map((j) => j.match.id));
}

function renderMatches() {
  matchesView.render(state, { players: boot.players, locked, recordedDates: recordedDates() });
  if (queue) queue.renderGo();
}

async function reload() {
  let data;
  try {
    data = await api.bootstrap();
  } catch (err) {
    window.alert(`Không tải lại được dữ liệu: ${err.message}`);
    return;
  }
  const prevLayout = state.layout;
  load(data);
  if (state.layout !== prevLayout) player.setLayout(state.layout);
  setSaveStatus('ok', 'Đã lưu');
  queue.render(boot.jobs);
  renderAll();
}

async function start() {
  let data;
  try {
    data = await api.bootstrap();
  } catch (err) {
    $('stage').textContent = `Không tải được dữ liệu: ${err.message}`;
    return;
  }
  load(data);

  setSaveStatus('ok', 'Đã lưu');
  player = createPlayer($('stage'), state.layout);
  timeline = createTimeline($('timeline'), {
    onSeek: (t) => player.seek(t),
    onMoveEdge,
    onSelectMatch: (id) => dispatch((s) => selectMatch(s, id)),
  });
  player.onTime(renderPlayhead);

  auth = createAuth($('auth'), boot.auth, () => queue && queue.renderGo());
  const modeState = createModeState(boot.mode, api.setMode);
  createModeToggle($('mode'), {
    modes: boot.modes,
    state: modeState,
    onChange: () => queue && queue.renderGo(),
  });
  matchesView = createMatches($('matches'), { dispatch, getState, getLocked, getOpenMatchId });
  queue = createQueue(
    { go: $('go'), note: $('go-note'), panel: $('queue') },
    {
      getState,
      getLocked,
      getOpenMatchId,
      isStale: () => !!staleError,
      isSignedIn: () => auth.get().ok,
      getMode: () => modeState.get(),
      modes: boot.modes,
      saveNow,
      onLocked: setLocked,
      onDone: refreshSources,
      onSignedOut: () => auth.refresh(),
    },
    boot.jobs,
  );
  subscribe(renderMatches);
  onEnterKey((id) => matchesView.focusTeam1(id));
  renderAll();
  queue.startPolling();

  $('stale-reload').addEventListener('click', () => window.location.reload());
  $('sources').addEventListener('click', (e) => {
    const el = e.target.closest('.src');
    if (!el) return;
    if (e.target.closest('.arch')) archiveSource(el.dataset.name);
    else toggleSource(el.dataset.name);
  });
  document.addEventListener('keydown', onKey);
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') flushOnLeave();
  });
  window.addEventListener('pagehide', flushOnLeave);
}

start();
