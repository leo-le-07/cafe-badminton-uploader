// Pure editing model for the match editor: no DOM, no mutation of inputs.
//
// Sources are laid end to end on one global timeline. Segments are stored in
// the session with times LOCAL to their source file, exactly as the server's
// app/models.py expects; every operation works in global time and converts
// back. `state.open` is the segment being kept right now, `{matchId, start}`
// with `start` in global time.
//
// Operations return a new state, or the very same object (===) when nothing
// changed. Every change to `session`, `open` or `layout` is undoable.

const EPS = 1e-6;
const UNDO_LIMIT = 200;
const DEFAULT_FPS = 30;
const DEFAULT_TOURNAMENT = 'Cafe Game';
const NO_LOCKS = new Set();

// ---------------------------------------------------------------- timeline

export function buildLayout(sources) {
  let offset = 0;
  return sources.map(({ name, duration, fps }) => {
    const entry = { name, offset, duration, fps: fps > 0 ? fps : DEFAULT_FPS };
    offset += duration;
    return entry;
  });
}

export function totalDuration(layout) {
  return layout.reduce((sum, e) => sum + e.duration, 0);
}

// The source playing at global time t; a boundary belongs to the later file.
function entryAt(layout, t) {
  const found = layout.find((e) => t < e.offset + e.duration - EPS);
  return found ?? layout[layout.length - 1];
}

function entryNamed(layout, name) {
  const found = layout.find((e) => e.name === name);
  if (!found) throw new Error(`Unknown source: ${name}`);
  return found;
}

export function toLocal(layout, t) {
  const e = entryAt(layout, t);
  return { name: e.name, time: t - e.offset };
}

export function toGlobal(layout, name, time) {
  return entryNamed(layout, name).offset + time;
}

// Round a local time onto the source's frame grid, clamped to the file. The
// file's own start and end are always valid points even when off the grid.
function roundLocal(e, local) {
  if (local <= EPS) return 0;
  if (local >= e.duration - EPS) return e.duration;
  return Math.min(Math.round(local * e.fps) / e.fps, e.duration);
}

// Latest grid point at least one frame before `local`, and earliest grid
// point at least one frame after it: the limits that keep a segment one frame
// long even when its other edge sits off the grid at the end of the file.
function frameBefore(e, local) {
  return Math.max(Math.floor((local - 1 / e.fps) * e.fps + EPS) / e.fps, 0);
}

function frameAfter(e, local) {
  return Math.min(Math.ceil((local + 1 / e.fps) * e.fps - EPS) / e.fps, e.duration);
}

export function snap(layout, t) {
  if (layout.length === 0) return 0;
  const clamped = Math.min(Math.max(t, 0), totalDuration(layout));
  const e = entryAt(layout, clamped);
  return e.offset + roundLocal(e, clamped - e.offset);
}

// Split global [start, end] at source boundaries into stored segments.
function toSegments(layout, start, end) {
  const pieces = [];
  for (const e of layout) {
    const from = Math.max(start, e.offset);
    const to = Math.min(end, e.offset + e.duration);
    if (to - from > EPS) {
      pieces.push({
        source: e.name,
        start: roundLocal(e, from - e.offset),
        end: roundLocal(e, to - e.offset),
      });
    }
  }
  return pieces;
}

// Every closed segment in global time, sorted by start.
function placed(session, layout) {
  const all = [];
  for (const m of session.matches) {
    m.segments.forEach((seg, segIndex) => {
      const offset = entryNamed(layout, seg.source).offset;
      all.push({ matchId: m.id, segIndex, start: offset + seg.start, end: offset + seg.end });
    });
  }
  return all.sort((a, b) => a.start - b.start);
}

function inside(seg, t) {
  return t >= seg.start - EPS && t < seg.end - EPS;
}

// ---------------------------------------------------------------- state

export function createEditor(session, layout, defaults = {}) {
  return {
    session,
    layout,
    open: null,
    undo: [],
    defaults: { tournament: defaults.tournament ?? DEFAULT_TOURNAMENT },
  };
}

function commit(state, changes) {
  const entry = { session: state.session, open: state.open, layout: state.layout };
  return { ...state, ...changes, undo: [...state.undo, entry].slice(-UNDO_LIMIT) };
}

export function undo(state) {
  if (state.undo.length === 0) return state;
  const entry = state.undo[state.undo.length - 1];
  return { ...state, ...entry, undo: state.undo.slice(0, -1) };
}

function findMatch(session, id) {
  return session.matches.find((m) => m.id === id);
}

function selectedMatch(state) {
  return findMatch(state.session, state.session.selected_match_id);
}

function sortSegments(layout, segments) {
  const key = (seg) => toGlobal(layout, seg.source, seg.start);
  return [...segments].sort((a, b) => key(a) - key(b));
}

function withSegments(state, session, matchId, segments) {
  return {
    ...session,
    matches: session.matches.map((m) =>
      m.id === matchId ? { ...m, segments: sortSegments(state.layout, segments) } : m,
    ),
  };
}

function replaceSegment(state, matchId, segIndex, changes) {
  const m = findMatch(state.session, matchId);
  const segments = m.segments.map((seg, i) => (i === segIndex ? { ...seg, ...changes } : seg));
  return withSegments(state, state.session, matchId, segments);
}

let idCounter = 0;
function defaultIdFactory() {
  idCounter += 1;
  return `m-${Date.now().toString(36)}-${idCounter.toString(36)}`;
}

function addMatch(state, session, id) {
  const previous = findMatch(session, session.selected_match_id);
  const created = {
    id,
    match_type: previous ? previous.match_type : 'md',
    team1: [],
    team2: [],
    tournament: previous ? previous.tournament : state.defaults.tournament,
    segments: [],
  };
  return { ...session, matches: [...session.matches, created], selected_match_id: id };
}

// ---------------------------------------------------------------- marking

export function markIn(state, t, idFactory = defaultIdFactory, locked = NO_LOCKS) {
  t = snap(state.layout, t);
  let session = state.session;
  if (!selectedMatch(state)) session = addMatch(state, session, idFactory());
  const matchId = session.selected_match_id;
  if (locked.has(matchId)) return state;
  const segs = placed(session, state.layout);

  if (!state.open) {
    const own = segs.find((s) => s.matchId === matchId && inside(s, t));
    if (own) {
      const seg = findMatch(session, matchId).segments[own.segIndex];
      const e = entryNamed(state.layout, seg.source);
      const start = Math.min(roundLocal(e, t - e.offset), frameBefore(e, seg.end));
      if (start === seg.start) return state;
      return commit(state, { session: replaceSegment(state, matchId, own.segIndex, { start }) });
    }
  }

  let start = t;
  for (let hit = segs.find((s) => inside(s, start)); hit; hit = segs.find((s) => inside(s, start))) {
    start = hit.end;
  }
  const open = { matchId, start };
  if (session === state.session && state.open && state.open.matchId === matchId && state.open.start === start) {
    return state;
  }
  return commit(state, { session, open });
}

// Close the open segment at t (already snapped); returns the new session, or
// the old one when the segment collapses to nothing.
function closeOpen(state, t) {
  const { open, layout, session } = state;
  const limit = placed(session, layout)
    .filter((s) => s.end > open.start + EPS)
    .reduce((min, s) => Math.min(min, s.start), Infinity);
  const end = Math.min(t, limit);
  if (end <= open.start + EPS) return session;
  const m = findMatch(session, open.matchId);
  return withSegments(state, session, m.id, [...m.segments, ...toSegments(layout, open.start, end)]);
}

export function markOut(state, t, locked = NO_LOCKS) {
  t = snap(state.layout, t);
  const sel = state.session.selected_match_id;
  if (locked.has(sel)) return state;
  if (state.open) {
    if (locked.has(state.open.matchId)) return state;
    return commit(state, { session: closeOpen(state, t), open: null });
  }
  const own = placed(state.session, state.layout).find(
    (s) => s.matchId === sel && inside(s, t) && t > s.start + EPS,
  );
  if (!own) return state;
  const seg = findMatch(state.session, sel).segments[own.segIndex];
  const e = entryNamed(state.layout, seg.source);
  const end = Math.max(roundLocal(e, t - e.offset), frameAfter(e, seg.start));
  if (end === seg.end) return state;
  return commit(state, { session: replaceSegment(state, sel, own.segIndex, { end }) });
}

export function newMatch(state, t, idFactory = defaultIdFactory, locked = NO_LOCKS) {
  t = snap(state.layout, t);
  const current = selectedMatch(state);
  if (current && current.segments.length === 0 && !state.open) return state;
  let session = state.session;
  if (state.open && !locked.has(state.open.matchId)) session = closeOpen(state, t);
  return commit(state, { session: addMatch(state, session, idFactory()), open: null });
}

export function selectMatch(state, id) {
  if (id === state.session.selected_match_id || !findMatch(state.session, id)) return state;
  return { ...state, session: { ...state.session, selected_match_id: id } };
}

export function deleteSegmentAt(state, t, locked = NO_LOCKS) {
  t = snap(state.layout, t);
  const hit = placed(state.session, state.layout).find((s) => inside(s, t));
  if (hit) {
    if (locked.has(hit.matchId)) return state;
    const m = findMatch(state.session, hit.matchId);
    const segments = m.segments.filter((_, i) => i !== hit.segIndex);
    return commit(state, { session: withSegments(state, state.session, m.id, segments) });
  }
  if (state.open && t >= state.open.start - EPS && !locked.has(state.open.matchId)) {
    return commit(state, { open: null });
  }
  return state;
}

export function moveEdge(state, matchId, segIndex, edge, t, locked = NO_LOCKS) {
  if (locked.has(matchId)) return state;
  const m = findMatch(state.session, matchId);
  const seg = m && m.segments[segIndex];
  if (!seg) return state;
  const e = entryNamed(state.layout, seg.source);
  const local = roundLocal(e, t - e.offset);
  // Neighbours in the same source, compared in local time to avoid drift.
  const others = state.session.matches
    .flatMap((x) => x.segments.filter((s) => s.source === seg.source && s !== seg));

  let value;
  if (edge === 'start') {
    const lo = others.filter((s) => s.end <= seg.start + EPS).reduce((a, s) => Math.max(a, s.end), 0);
    const hi = frameBefore(e, seg.end);
    value = Math.max(lo, Math.min(local, hi));
  } else {
    const hi = others
      .filter((s) => s.start >= seg.end - EPS)
      .reduce((a, s) => Math.min(a, s.start), e.duration);
    const lo = frameAfter(e, seg.start);
    value = Math.min(hi, Math.max(local, lo));
  }
  if (value === seg[edge]) return state;
  return commit(state, { session: replaceSegment(state, matchId, segIndex, { [edge]: value }) });
}

// ---------------------------------------------------------------- matches

const EDITABLE_FIELDS = ['match_type', 'team1', 'team2', 'tournament'];

function sameValue(a, b) {
  if (Array.isArray(a) && Array.isArray(b)) {
    return a.length === b.length && a.every((x, i) => x === b[i]);
  }
  return a === b;
}

export function updateMatch(state, id, fields, locked = NO_LOCKS) {
  const m = findMatch(state.session, id);
  if (!m || locked.has(id)) return state;
  const changes = {};
  for (const key of EDITABLE_FIELDS) {
    if (key in fields && !sameValue(fields[key], m[key])) changes[key] = fields[key];
  }
  if (Object.keys(changes).length === 0) return state;
  const matches = state.session.matches.map((x) => (x.id === id ? { ...x, ...changes } : x));
  return commit(state, { session: { ...state.session, matches } });
}

function hasNames(m) {
  return [...m.team1, ...m.team2].some((name) => name.trim());
}

// Removes a source and rebuilds `state.layout` without it; undo restores both.
export function removeSource(state, name, locked = NO_LOCKS) {
  const { session, layout } = state;
  if (!session.sources.includes(name)) return state;
  const touches = (m) => m.segments.some((s) => s.source === name);
  if (session.matches.some((m) => touches(m) && locked.has(m.id))) return state;

  const matches = session.matches
    .map((m) => (touches(m) ? { ...m, segments: m.segments.filter((s) => s.source !== name) } : m))
    .filter((m, i) => m.segments.length > 0 || hasNames(m) || !touches(session.matches[i]));
  const selected = matches.some((m) => m.id === session.selected_match_id)
    ? session.selected_match_id
    : null;
  const newLayout = buildLayout(layout.filter((e) => e.name !== name));

  let open = null;
  if (state.open && matches.some((m) => m.id === state.open.matchId)) {
    const at = toLocal(layout, state.open.start);
    if (at.name !== name) open = { ...state.open, start: toGlobal(newLayout, at.name, at.time) };
  }
  return commit(state, {
    session: { sources: session.sources.filter((s) => s !== name), matches, selected_match_id: selected },
    open,
    layout: newLayout,
  });
}

// ---------------------------------------------------------------- views

// Closed segments plus the open one, in global time, sorted by start. The open
// segment runs to the playhead, stopped at the next segment.
export function segmentsOnTimeline(state, playhead) {
  const closed = placed(state.session, state.layout).map((s) => ({ ...s, open: false }));
  if (!state.open) return closed;
  const { matchId, start } = state.open;
  const limit = closed.filter((s) => s.start >= start - EPS).reduce((a, s) => Math.min(a, s.start), Infinity);
  const end = Math.max(start, Math.min(playhead ?? start, limit));
  return [...closed, { matchId, segIndex: null, start, end, open: true }].sort((a, b) => a.start - b.start);
}

export function keptDuration(match) {
  return match.segments.reduce((sum, s) => sum + (s.end - s.start), 0);
}

// Mirrors video_prep.create_title.
export function previewTitle(match, date) {
  return `${match.team1.join('/')} vs ${match.team2.join('/')} | ${match.tournament} (${date})`;
}

// Mirrors app.models.match_problems.
export function matchProblems(match) {
  const problems = [];
  if (!match.team1.some((n) => n.trim())) problems.push('Thiếu tên người chơi đội 1');
  if (!match.team2.some((n) => n.trim())) problems.push('Thiếu tên người chơi đội 2');
  if (match.segments.length === 0) problems.push('Chưa có đoạn nào');
  return problems;
}
