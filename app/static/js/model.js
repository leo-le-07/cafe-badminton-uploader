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
export const DEFAULT_TOURNAMENT = 'Cafe Game';
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

// A source can be in the session without being on the timeline: its file is
// missing on disk (or unreadable), so its duration is unknown. Its segments
// stay in the session untouched and every operation skips them.
function entryOrNull(layout, name) {
  return layout.find((e) => e.name === name) ?? null;
}

// Every closed segment on the timeline in global time, sorted by start.
function placed(session, layout) {
  const all = [];
  for (const m of session.matches) {
    m.segments.forEach((seg, segIndex) => {
      const e = entryOrNull(layout, seg.source);
      if (!e) return;
      const offset = e.offset;
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
    defaults: { tournament: defaults.tournament ?? DEFAULT_TOURNAMENT, theme: defaults.theme ?? '' },
  };
}

function commit(state, changes) {
  const entry = { session: state.session, open: state.open, layout: state.layout };
  return { ...state, ...changes, undo: [...state.undo, entry].slice(-UNDO_LIMIT) };
}

// Undo is refused when the step would change, bring back or drop a locked
// match (one sent to the queue after the step was recorded).
export function undo(state, locked = NO_LOCKS) {
  if (state.undo.length === 0) return state;
  const entry = state.undo[state.undo.length - 1];
  for (const id of locked) {
    const now = findMatch(state.session, id);
    const then = findMatch(entry.session, id);
    if (now !== then && JSON.stringify(now) !== JSON.stringify(then)) return state;
  }
  return { ...state, ...entry, undo: state.undo.slice(0, -1) };
}

function findMatch(session, id) {
  return session.matches.find((m) => m.id === id);
}

function selectedMatch(state) {
  return findMatch(state.session, state.session.selected_match_id);
}

// Segments on the timeline sorted by global start; segments of sources not on
// the timeline follow in their stored order.
function sortSegments(layout, segments) {
  const key = (seg) => {
    const e = entryOrNull(layout, seg.source);
    return e ? e.offset + seg.start : Infinity;
  };
  return [...segments].sort((a, b) => key(a) - key(b) || 0);
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
    theme: previous ? (previous.theme ?? '') : state.defaults.theme,
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
  const e = seg && entryOrNull(state.layout, seg.source);
  if (!e) return state;
  const local = roundLocal(e, t - e.offset);
  // Neighbours in the same source, compared in local time to avoid drift.
  const others = state.session.matches
    .flatMap((x) => x.segments.filter((s) => s.source === seg.source && s !== seg));

  // The open point is an obstacle like a neighbour's edge: a segment may
  // touch it but never grow over it.
  const at = state.open ? toLocal(state.layout, state.open.start) : null;
  const point = at && at.name === seg.source ? roundLocal(e, at.time) : null;

  let value;
  if (edge === 'start') {
    let lo = others.filter((s) => s.end <= seg.start + EPS).reduce((a, s) => Math.max(a, s.end), 0);
    if (point !== null && point <= seg.start + EPS) lo = Math.max(lo, point);
    const hi = frameBefore(e, seg.end);
    value = Math.max(lo, Math.min(local, hi));
  } else {
    let hi = others
      .filter((s) => s.start >= seg.end - EPS)
      .reduce((a, s) => Math.min(a, s.start), e.duration);
    if (point !== null && point >= seg.end - EPS) hi = Math.min(hi, point);
    const lo = frameAfter(e, seg.start);
    value = Math.min(hi, Math.max(local, lo));
  }
  if (value === seg[edge]) return state;
  return commit(state, { session: replaceSegment(state, matchId, segIndex, { [edge]: value }) });
}

// ---------------------------------------------------------------- matches

const EDITABLE_FIELDS = ['match_type', 'team1', 'team2', 'tournament', 'theme'];

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

// Removes match `id`, its open segment if any, and selects the match before
// it (or none) when it was selected.
export function removeMatch(state, id, locked = NO_LOCKS) {
  const { session } = state;
  const index = session.matches.findIndex((m) => m.id === id);
  if (index < 0 || locked.has(id)) return state;
  const matches = session.matches.filter((m) => m.id !== id);
  const selected = session.selected_match_id === id
    ? (session.matches[index - 1]?.id ?? null)
    : session.selected_match_id;
  return commit(state, {
    session: { ...session, matches, selected_match_id: selected },
    open: state.open && state.open.matchId === id ? null : state.open,
  });
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

// Puts source `name` on the timeline. `infos` is the caller's full list of
// source infos ({name, duration, fps, ...}) already in recording order, such
// as the server's source list; the timeline keeps the relative order of
// `infos`, so the new file lands between the files recorded before and after
// it. Sources in the session that are not on the timeline (missing on disk)
// stay in `session.sources` after the placed ones. Segments are local to
// their file and do not change; an open segment keeps its place in its file.
// Undo removes the source again.
export function addSource(state, name, infos) {
  const { session, layout } = state;
  const info = infos.find((s) => s.name === name);
  if (session.sources.includes(name) || !info || !(info.duration > 0)) return state;
  const placedNames = new Set([...layout.map((e) => e.name), name]);
  const known = new Map(layout.map((e) => [e.name, e]));
  known.set(name, info);
  const ordered = infos.filter((s) => placedNames.has(s.name)).map((s) => known.get(s.name));
  // Placed sources the caller did not list keep their place at the end.
  for (const e of layout) if (!ordered.includes(e)) ordered.push(e);
  const newLayout = buildLayout(ordered);
  const offTimeline = session.sources.filter((s) => !placedNames.has(s));

  let open = state.open;
  if (open && layout.length > 0) {
    const at = toLocal(layout, open.start);
    open = { ...open, start: toGlobal(newLayout, at.name, at.time) };
  }
  return commit(state, {
    session: { ...session, sources: [...newLayout.map((e) => e.name), ...offTimeline] },
    open,
    layout: newLayout,
  });
}

// ---------------------------------------------------------------- stored session

// The server stores the session with two more fields: `open`, the open
// segment as {match_id, source, time} with `time` local to its source, and
// `revision`. The editor keeps the session without them and the open segment
// in `state.open` (global time). An open point that cannot be placed (its
// file is not on the timeline) is returned as `hiddenOpen`: it is not shown
// but saved back unchanged while it still belongs to a match and a source of
// the session (see storedSession).
export function editorFromStored(stored, layout, defaults) {
  const { open: point = null, revision: _revision, ...session } = stored;
  let state = createEditor(session, layout, defaults);
  if (!point || !findMatch(session, point.match_id)) return { state, hiddenOpen: null };
  if (!entryOrNull(layout, point.source)) return { state, hiddenOpen: point };
  const open = { matchId: point.match_id, start: toGlobal(layout, point.source, point.time) };
  state = { ...state, open };
  return { state, hiddenOpen: null };
}

// The session to store, with `open` (no revision). A new open segment
// replaces the hidden one.
export function storedSession(state, hiddenOpen = null) {
  const { session, layout, open } = state;
  let point = null;
  if (open) {
    const e = entryAt(layout, open.start);
    point = { match_id: open.matchId, source: e.name, time: roundLocal(e, open.start - e.offset) };
  } else if (
    hiddenOpen &&
    findMatch(session, hiddenOpen.match_id) &&
    session.sources.includes(hiddenOpen.source)
  ) {
    point = hiddenOpen;
  }
  return { ...session, open: point };
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

const names = (team) => team.map((n) => n.trim()).filter(Boolean);

// The YouTube title. Mirrors app.models.match_title: names trimmed, empty
// ones dropped, the default tournament when it is empty.
// Whether the match is in the default tournament (an empty field counts),
// whose thumbnail colour is fixed. Mirrors match_theme in app/models.py.
export function isDefaultTournament(match) {
  const tournament = match.tournament.trim() || DEFAULT_TOURNAMENT;
  return tournament.toLocaleLowerCase('vi') === DEFAULT_TOURNAMENT.toLocaleLowerCase('vi');
}

// The colour key the thumbnail of a non-default tournament gets: the picked
// one, else the first of `choices` (keys in order).
export function pickedTheme(match, choices) {
  return choices.includes(match.theme) ? match.theme : choices[0];
}

export function previewTitle(match, date) {
  const tournament = match.tournament.trim() || DEFAULT_TOURNAMENT;
  return `${names(match.team1).join('/')} vs ${names(match.team2).join('/')} | ${tournament} (${date})`;
}

// Recording date (YYYY-MM-DD) for the title: that of the source holding the
// match's first segment; with no segment yet, that of the first session
// source; `today` when unknown. `dates` maps source name -> date.
export function recordedDate(match, session, dates, today) {
  const source = match.segments.length > 0 ? match.segments[0].source : session.sources[0];
  return (source !== undefined && dates[source]) || today;
}

export const OPEN_SEGMENT_PROBLEM = 'Còn một đoạn đang mở — bấm O để đóng';
const ANGLE_BRACKET_PROBLEM = 'Tên người chơi và giải không được chứa dấu < hoặc >';
const MAX_TITLE_LENGTH = 100;

// Mirrors app.models.match_problems. `openMatchId` is the match that owns
// the open segment (null when none): it must be closed with O first.
export function matchProblems(match, openMatchId = null) {
  const problems = [];
  if (!match.team1.some((n) => n.trim())) problems.push('Thiếu tên người chơi đội 1');
  if (!match.team2.some((n) => n.trim())) problems.push('Thiếu tên người chơi đội 2');
  if (match.segments.length === 0) problems.push('Chưa có đoạn nào');
  if (openMatchId !== null && openMatchId === match.id) problems.push(OPEN_SEGMENT_PROBLEM);
  if ([...match.team1, ...match.team2, match.tournament].some((t) => /[<>]/.test(t))) {
    problems.push(ANGLE_BRACKET_PROBLEM);
  }
  // Counted in code points like Python's len(); any date has the same length.
  const length = [...previewTitle(match, '0000-00-00')].length;
  if (length > MAX_TITLE_LENGTH) {
    problems.push(`Tiêu đề dài ${length} ký tự, YouTube chỉ nhận tối đa ${MAX_TITLE_LENGTH}`);
  }
  return problems;
}
