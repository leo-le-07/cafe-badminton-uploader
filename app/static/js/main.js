// Editor page: holds the state, wires the player, timeline and source list,
// handles the keyboard and autosaves the session.
//
// Exports for the modules of the right-hand column (Task 11):
//   getState(), dispatch(fn), subscribe(listener), getBootstrap(),
//   getLocked(), setLocked(ids), getPlayhead(), seek(t), onEnterKey(handler),
//   matchColor(index)

import * as api from './api.js';
import {
  addSource,
  buildLayout,
  createEditor,
  deleteSegmentAt,
  markIn,
  markOut,
  moveEdge,
  newMatch,
  removeSource,
  selectMatch,
  undo,
} from './model.js';
import { createPlayer, formatTimecode } from './player.js';
import { createTimeline, matchColor } from './timeline.js';

export { matchColor };

const SAVE_DELAY_MS = 1000;

let boot = null;
let state = null;
let locked = new Set();
let player = null;
let timeline = null;
let enterHandler = null;
const listeners = new Set();

const $ = (id) => document.getElementById(id);

// ---------------------------------------------------------------- public API

export const getState = () => state;
export const getBootstrap = () => boot;
export const getLocked = () => locked;
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
export function setLocked(ids) {
  locked = new Set(ids);
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
  if (next.session !== prev.session) scheduleSave();
  renderAll();
}

function renderAll() {
  if (!state) return;
  renderSources();
  renderPlayhead();
  for (const listener of listeners) listener(state);
}

// ---------------------------------------------------------------- top bar

function renderTop() {
  const auth = $('auth-pill');
  auth.textContent = boot.auth.ok ? '● YouTube đã đăng nhập' : '○ YouTube chưa đăng nhập';
  auth.classList.toggle('ok', boot.auth.ok);
  auth.classList.toggle('bad', !boot.auth.ok);
  if (boot.auth.channel) auth.title = boot.auth.channel;
  $('defaults-pill').textContent = `Mặc định: ${boot.defaults.tournament} · ${boot.defaults.privacy}`;
}

function setSaveStatus(kind, text, detail = '') {
  const pill = $('save-pill');
  pill.textContent = text;
  pill.title = detail;
  pill.classList.toggle('bad', kind === 'error');
}

// ---------------------------------------------------------------- sources

const readableInfos = () => boot.sources.filter((s) => !s.missing && !s.unreadable);
const circled = (i) => String.fromCharCode(0x2460 + i);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => `&#${c.charCodeAt(0)};`);
const pad = (n) => String(n).padStart(2, '0');

function formatLength(sec) {
  const s = Math.round(sec);
  const h = Math.floor(s / 3600);
  const mmss = `${pad(Math.floor(s / 60) % 60)}:${pad(s % 60)}`;
  return h > 0 ? `${h}:${mmss}` : mmss;
}

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
    return `<div class="${cls}" role="checkbox" aria-checked="${on}" data-name="${esc(s.name)}">${chk}${esc(s.name)}<small>${info}</small></div>`;
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

function onKey(e) {
  if (!state) return;
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
    dispatch(undo);
    return;
  }
  if (mod || e.altKey) return;

  const once = !e.repeat;
  const actions = {
    KeyI: () => once && dispatch((s) => markIn(s, t, undefined, locked)),
    KeyO: () => once && dispatch((s) => markOut(s, t, locked)),
    KeyN: () => once && dispatch((s) => newMatch(s, t, undefined, locked)),
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
    Delete: () => dispatch((s) => deleteSegmentAt(s, t, locked)),
    Backspace: () => dispatch((s) => deleteSegmentAt(s, t, locked)),
  };
  const action = actions[e.code];
  if (!action) return;
  e.preventDefault();
  if (document.activeElement && document.activeElement !== document.body) document.activeElement.blur();
  action();
}

// ---------------------------------------------------------------- autosave

let saved = null; // last session the server accepted
let attempted = null; // last session sent, accepted or not
let saveTimer = 0;
let saving = false;

function scheduleSave() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(flushSave, SAVE_DELAY_MS);
  if (!saving) setSaveStatus('saving', 'Đang lưu…');
}

async function flushSave(opts) {
  clearTimeout(saveTimer);
  saveTimer = 0;
  // Never two saves at once: the one in flight saves again when it ends.
  if (saving) return;
  if (state.session === saved) {
    setSaveStatus('ok', 'Đã lưu');
    return;
  }
  if (state.session === attempted) return; // refused already; wait for a change
  const session = state.session;
  saving = true;
  attempted = session;
  setSaveStatus('saving', 'Đang lưu…');
  try {
    await api.saveSession(session, opts);
    saved = session;
    if (state.session === saved) setSaveStatus('ok', 'Đã lưu');
  } catch (err) {
    setSaveStatus('error', `Lưu thất bại: ${err.message}`, (err.errors || [err.message]).join('\n'));
  } finally {
    saving = false;
  }
  if (state.session !== attempted) flushSave(opts);
}

function flushOnLeave() {
  if (state && state.session !== saved && state.session !== attempted && !saving) {
    flushSave({ keepalive: true });
  }
}

// ---------------------------------------------------------------- bootstrap

async function start() {
  try {
    boot = await api.bootstrap();
  } catch (err) {
    $('stage').textContent = `Không tải được dữ liệu: ${err.message}`;
    return;
  }
  const infos = new Map(readableInfos().map((s) => [s.name, s]));
  const layout = buildLayout(boot.session.sources.filter((n) => infos.has(n)).map((n) => infos.get(n)));
  state = createEditor(boot.session, layout, boot.defaults);
  saved = boot.session;
  const ids = new Set(boot.session.matches.map((m) => m.id));
  locked = new Set(boot.jobs.map((j) => j.match.id).filter((id) => ids.has(id)));

  renderTop();
  setSaveStatus('ok', 'Đã lưu');
  player = createPlayer($('stage'), state.layout);
  timeline = createTimeline($('timeline'), {
    onSeek: (t) => player.seek(t),
    onMoveEdge,
    onSelectMatch: (id) => dispatch((s) => selectMatch(s, id)),
  });
  player.onTime(renderPlayhead);
  renderAll();

  $('sources').addEventListener('click', (e) => {
    const el = e.target.closest('.src');
    if (el) toggleSource(el.dataset.name);
  });
  document.addEventListener('keydown', onKey);
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') flushOnLeave();
  });
  window.addEventListener('pagehide', flushOnLeave);
}

start();
