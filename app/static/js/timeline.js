// Zoomable timeline (behaviour of docs/.../mockups/timeline-scrub.html):
// overview strip with the visible window, ruler, segments coloured by match,
// joints between sources, hover timecode, click-drag scrubbing with edge
// auto-scroll, edge dragging. It only renders and reports intents through the
// callbacks; it never changes editor state itself.

import { segmentsOnTimeline, snap, totalDuration } from './model.js';
import { formatClock, formatTimecode } from './player.js';

export const MATCH_COLORS = ['#3fa7ff', '#5ed38a', '#ff8a4c'];
export const matchColor = (index) => MATCH_COLORS[((index % 3) + 3) % 3];

const EDGE_PX = 7;
const PX_PER_FRAME = 12;
const ZOOM_STEP = 10;
const AUTO_SCROLL_MARGIN = 40;
const AUTO_SCROLL_PX = 14;
const FOLLOW_MARGIN = 30;
const NO_LOCKS = new Set();

const circled = (i) => String.fromCharCode(0x2460 + i);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => `&#${c.charCodeAt(0)};`);

const TEMPLATE = `
  <div class="bar">
    <h4>Toàn bộ video</h4>
    <div class="sp"></div>
    <button type="button" data-act="fit">Vừa màn hình</button>
    <button type="button" data-act="out" title="Thu nhỏ (−)">−</button>
    <input type="range" min="0" max="100" value="0" step="any" aria-label="Mức zoom">
    <button type="button" data-act="in" title="Phóng to (+)">+</button>
    <b class="zl"></b>
  </div>
  <div class="mini"><div class="mini-segs"></div><div class="h"></div><div class="view"></div></div>
  <div class="scroller">
    <div class="inner">
      <div class="ruler"></div>
      <div class="track"></div>
      <div class="hover"><span></span></div>
      <div class="head"></div>
    </div>
  </div>`;

export function createTimeline(container, { onSeek, onMoveEdge, onSelectMatch }) {
  container.classList.add('tlbox');
  container.innerHTML = TEMPLATE;
  const $ = (sel) => container.querySelector(sel);
  const sc = $('.scroller');
  const inner = $('.inner');
  const track = $('.track');
  const ruler = $('.ruler');
  const mini = $('.mini');
  const miniSegs = $('.mini-segs');
  const miniHead = $('.mini .h');
  const miniView = $('.mini .view');
  const headEl = $('.head');
  const hover = $('.hover');
  const zoomInput = $('.bar input');
  const zoomLabel = $('.zl');

  let layout = [];
  let state = null;
  let locked = NO_LOCKS;
  let playhead = 0;
  let dur = 0;
  let zoom = 0; // 0..100
  let pps = 1;
  let width = 0; // cached scroller width
  let built = null; // what the segment DOM was built from
  let segs = []; // segments on screen, global times
  let openEl = null;
  let openSeg = null;
  let scrollX = 0; // cached sc.scrollLeft, so playhead ticks never force a layout
  let openLimit = Infinity;
  let drag = null; // {kind: 'scrub'|'edge', seg, edge, x}
  let pendingDrag = null;
  let dragFrame = 0;
  let edgeTimer = 0;

  const maxPps = () => PX_PER_FRAME * Math.max(30, ...layout.map((e) => e.fps));
  const minPps = () => (width > 0 ? width / Math.max(dur, 1) : 1);
  const fullWidth = () => Math.max(dur * pps, width);

  // ------------------------------------------------------------ rendering

  function rebuildSegments() {
    const order = new Map(state.session.matches.map((m, i) => [m.id, i]));
    const selected = state.session.selected_match_id;
    segs = segmentsOnTimeline(state, playhead);
    const open = segs.find((s) => s.open);
    openLimit = open
      ? segs.filter((s) => !s.open && s.start >= open.start - 1e-6).reduce((a, s) => Math.min(a, s.start), Infinity)
      : Infinity;
    let html = '';
    let miniHtml = '';
    for (const s of segs) {
      const i = order.get(s.matchId);
      const cls = ['seg'];
      if (s.open) cls.push('open');
      if (s.matchId === selected) cls.push('sel');
      if (locked.has(s.matchId)) cls.push('locked');
      const label = s.open ? '' : `Trận ${i + 1} · ${formatClock(s.end - s.start)}`;
      html += `<div class="${cls.join(' ')}" style="left:${s.start * pps}px;width:${(s.end - s.start) * pps}px;background-color:${matchColor(i)}">${label}</div>`;
      if (!s.open) {
        miniHtml += `<div class="s${locked.has(s.matchId) ? ' locked' : ''}" style="left:${(s.start / dur) * 100}%;width:${((s.end - s.start) / dur) * 100}%;background:${matchColor(i)}"></div>`;
      }
    }
    layout.forEach((e, i) => {
      if (i > 0) html += `<div class="joint" style="left:${e.offset * pps}px"><span>${circled(i)} ${esc(e.name)}</span></div>`;
    });
    if (layout.length === 0) html = '<div class="empty">Tick một video ở cột trái để bắt đầu</div>';
    track.innerHTML = html;
    miniSegs.innerHTML = miniHtml;
    openEl = track.querySelector('.seg.open');
    openSeg = open ?? null;
    built = { session: state.session, open: state.open, layout, locked, pps };
  }

  function renderRuler() {
    const fps = Math.max(30, ...layout.map((e) => e.fps));
    const steps = [1 / fps, 0.5, 1, 5, 10, 30, 60, 300, 600, 1800, 3600];
    const major = steps.find((s) => s * pps >= 90) || 3600;
    const minor = major / (major <= 1 / fps ? 1 : 5);
    const from = sc.scrollLeft / pps;
    const to = Math.min((sc.scrollLeft + width) / pps, dur);
    let h = '';
    for (let k = Math.floor(from / minor); k * minor <= to + 1e-9; k++) {
      const t = k * minor;
      const isMajor = Math.abs(t / major - Math.round(t / major)) < 1e-6;
      const text = isMajor ? (major < 1 ? formatTimecode(layout, t) : formatClock(t)) : '';
      h += `<div class="tick${isMajor ? '' : ' minor'}" style="left:${t * pps}px">${text}</div>`;
    }
    ruler.innerHTML = h;
    const vis = width / pps;
    zoomLabel.textContent = 'đang xem ' + (vis >= 60 ? `${(vis / 60).toFixed(1)} phút` : `${vis.toFixed(1)} giây`);
    miniView.style.left = `${(from / Math.max(dur, 1e-9)) * 100}%`;
    miniView.style.width = `${Math.min(100, (vis / Math.max(dur, 1e-9)) * 100)}%`;
  }

  function placeHead() {
    headEl.style.left = `${playhead * pps}px`;
    miniHead.style.left = `${dur > 0 ? (playhead / dur) * 100 : 0}%`;
    if (openEl) {
      const end = Math.max(openSeg.start, Math.min(playhead, openLimit));
      openEl.style.width = `${(end - openSeg.start) * pps}px`;
    }
  }

  // Keep the playhead in view when it moves by playback or keys.
  function follow() {
    const x = playhead * pps;
    if (x < scrollX || x > scrollX + width - FOLLOW_MARGIN) {
      scrollX = Math.max(0, Math.min(x - FOLLOW_MARGIN, fullWidth() - width));
      sc.scrollLeft = scrollX;
    }
  }

  function render(nextState, nextLayout, nextPlayhead, opts = {}) {
    const moved = nextPlayhead !== playhead;
    state = nextState;
    locked = opts.locked ?? locked;
    playhead = nextPlayhead;
    if (nextLayout !== layout) {
      layout = nextLayout;
      dur = totalDuration(layout);
      measure();
      setZoom(zoom, null, true);
    }
    if (
      !built || built.session !== state.session || built.open !== state.open ||
      built.layout !== layout || built.locked !== locked || built.pps !== pps
    ) {
      rebuildSegments();
    }
    if (moved && !drag) follow();
    placeHead();
  }

  // ------------------------------------------------------------ zoom

  function measure() {
    width = sc.clientWidth;
  }

  function setZoom(v, anchorX, keepScroll = false) {
    zoom = Math.max(0, Math.min(100, v));
    zoomInput.value = zoom;
    if (anchorX == null) anchorX = playhead * pps - sc.scrollLeft;
    if (anchorX < 0 || anchorX > width) anchorX = width / 2;
    const t = (sc.scrollLeft + anchorX) / pps;
    const lo = minPps();
    const hi = Math.max(maxPps(), lo);
    pps = lo * Math.pow(hi / lo, zoom / 100);
    inner.style.width = `${fullWidth()}px`;
    if (!keepScroll) {
      sc.scrollLeft = t * pps - anchorX;
      scrollX = sc.scrollLeft;
    }
    if (state) {
      rebuildSegments();
      placeHead();
    }
    renderRuler();
  }

  const zoomBy = (delta, anchorX) => setZoom(zoom + delta, anchorX);
  const fit = () => setZoom(0);

  container.addEventListener('click', (e) => {
    const act = e.target.closest('button')?.dataset.act;
    if (!act) return;
    if (act === 'fit') fit();
    if (act === 'in') zoomBy(ZOOM_STEP);
    if (act === 'out') zoomBy(-ZOOM_STEP);
    e.target.closest('button').blur(); // keep Space for play/pause
  });
  zoomInput.addEventListener('input', () => setZoom(+zoomInput.value));
  zoomInput.addEventListener('change', () => zoomInput.blur());
  sc.addEventListener('scroll', () => {
    scrollX = sc.scrollLeft;
    renderRuler();
  });
  sc.addEventListener('wheel', (e) => {
    if (!(e.metaKey || e.ctrlKey)) return;
    e.preventDefault();
    setZoom(zoom - e.deltaY * 0.15, e.clientX - sc.getBoundingClientRect().left);
  }, { passive: false });
  new ResizeObserver(() => {
    measure();
    setZoom(zoom, null, true);
  }).observe(sc);
  mini.addEventListener('click', (e) => {
    const r = mini.getBoundingClientRect();
    sc.scrollLeft = ((e.clientX - r.left) / r.width) * dur * pps - width / 2;
  });

  // ------------------------------------------------------------ pointer

  const xOf = (clientX) => clientX - inner.getBoundingClientRect().left;
  const timeOf = (x) => snap(layout, x / pps);

  // The closest editable edge within EDGE_PX of x; on a tie, the segment the
  // pointer is inside wins.
  function edgeAt(x) {
    let best = null;
    for (const s of segs) {
      if (s.open || locked.has(s.matchId)) continue;
      for (const edge of ['start', 'end']) {
        const d = Math.abs(x - s[edge] * pps);
        const within = x >= s.start * pps && x < s.end * pps;
        if (d <= EDGE_PX && (!best || d < best.d || (d === best.d && within))) best = { seg: s, edge, d };
      }
    }
    return best;
  }

  function flushDrag() {
    dragFrame = 0;
    if (!drag || pendingDrag === null) return;
    const x = pendingDrag;
    pendingDrag = null;
    emitDrag(x);
  }

  // An edge keeps the distance between the pointer and the edge at press time,
  // so grabbing it a few pixels off does not make it jump.
  function emitDrag(x) {
    if (drag.kind === 'edge') {
      onMoveEdge(drag.seg.matchId, drag.seg.segIndex, drag.edge, timeOf(Math.max(0, x + drag.offset)), 'move');
    } else {
      onSeek(timeOf(x));
    }
  }

  function dragTo(clientX) {
    pendingDrag = Math.max(0, Math.min(xOf(clientX), dur * pps));
    if (!dragFrame) dragFrame = requestAnimationFrame(flushDrag);
  }

  function showHover(clientX) {
    if (layout.length === 0) return;
    const t = timeOf(Math.max(0, xOf(clientX)));
    hover.style.display = 'block';
    hover.style.left = `${t * pps}px`;
    hover.firstChild.textContent = formatTimecode(layout, t);
  }

  inner.addEventListener('pointerdown', (e) => {
    if (e.button !== 0 || layout.length === 0) return;
    e.preventDefault();
    // preventDefault keeps focus where it was; hand it back to the editor so
    // shortcuts work after pressing on the timeline.
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
    inner.setPointerCapture(e.pointerId);
    const x = xOf(e.clientX);
    const hit = edgeAt(x);
    if (hit) {
      const at = hit.seg[hit.edge];
      drag = { kind: 'edge', seg: hit.seg, edge: hit.edge, x: e.clientX, offset: at * pps - x };
      onMoveEdge(hit.seg.matchId, hit.seg.segIndex, hit.edge, at, 'start');
    } else {
      const body = segs.find((s) => x >= s.start * pps && x < s.end * pps);
      if (body) onSelectMatch(body.matchId);
      drag = { kind: 'scrub', x: e.clientX };
      onSeek(timeOf(x));
    }
    document.body.classList.add(drag.kind === 'edge' ? 'dragging-edge' : 'scrubbing');
    edgeTimer = setInterval(() => {
      const r = sc.getBoundingClientRect();
      if (drag.x > r.right - AUTO_SCROLL_MARGIN) sc.scrollLeft += AUTO_SCROLL_PX;
      else if (drag.x < r.left + AUTO_SCROLL_MARGIN) sc.scrollLeft -= AUTO_SCROLL_PX;
      else return;
      dragTo(Math.max(r.left, Math.min(r.right, drag.x)));
    }, 16);
  });

  inner.addEventListener('pointermove', (e) => {
    showHover(e.clientX);
    if (!drag) return;
    drag.x = e.clientX;
    dragTo(e.clientX);
  });

  function endDrag() {
    if (!drag) return;
    clearInterval(edgeTimer);
    if (dragFrame) cancelAnimationFrame(dragFrame);
    dragFrame = 0;
    if (pendingDrag !== null) emitDrag(pendingDrag);
    pendingDrag = null;
    if (drag.kind === 'edge') onMoveEdge(drag.seg.matchId, drag.seg.segIndex, drag.edge, null, 'end');
    document.body.classList.remove('scrubbing', 'dragging-edge');
    drag = null;
  }
  inner.addEventListener('pointerup', endDrag);
  inner.addEventListener('lostpointercapture', endDrag);
  inner.addEventListener('pointerleave', () => {
    if (!drag) hover.style.display = 'none';
  });

  measure();
  setZoom(0, null, true);

  return { render, zoomBy, fit };
}
