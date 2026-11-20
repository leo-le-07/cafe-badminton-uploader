// Multi-source player: one <video> per source on the timeline, only the one
// under the playhead is shown. Every time here is on the shared timeline
// (seconds from the start of the first source).
//
// Seeks are coalesced: at most one per animation frame, and none while the
// video is still busy with the previous seek (only the latest target is kept),
// so scrubbing a large HEVC file never builds up a queue of seeks.

import { snap, totalDuration } from './model.js';
import { mediaUrl } from './api.js';

const RATES = [1, 2, 4, 8];
// Seek slightly past the frame's start so the decoder lands on that frame and
// not on the one before it because of rounding.
const NUDGE = 0.001;
const PRIME_BEFORE_END = 2;

// The source at global time t; a boundary belongs to the later file
// (same rule as model.js).
function indexAt(layout, t) {
  const i = layout.findIndex((e) => t < e.offset + e.duration - 1e-6);
  return i === -1 ? layout.length - 1 : i;
}

const pad = (n) => String(n).padStart(2, '0');

// HH:MM:SS:FF, FF counted with the fps of the source under t.
export function formatTimecode(layout, t) {
  const e = layout[indexAt(layout, t)];
  const fps = e ? e.fps : 30;
  const secs = Math.floor(t + 1e-6);
  const ff = Math.min(Math.floor((t - secs) * fps + 1e-6), Math.ceil(fps) - 1);
  return `${formatClock(secs)}:${pad(Math.max(ff, 0))}`;
}

// HH:MM:SS
export function formatClock(t) {
  const s = Math.floor(t + 1e-6);
  return `${pad(Math.floor(s / 3600))}:${pad(Math.floor(s / 60) % 60)}:${pad(s % 60)}`;
}

export function createPlayer(container, initialLayout) {
  let layout = [];
  const videos = new Map(); // name -> <video>
  const listeners = new Set();
  let head = 0;
  let current = -1; // index of the shown source
  let target = null; // pending global seek target
  let seekFrame = 0;
  let mode = 'paused'; // 'paused' | 'forward' | 'reverse'
  let rate = 1;
  let loop = 0;
  let lastTick = 0;
  let primed = -1;

  const total = () => totalDuration(layout);
  const emit = () => listeners.forEach((cb) => cb(head));

  // A file that cannot be played shows a message over the player and stops
  // playback, instead of a silent black frame.
  const errorEl = document.createElement('div');
  errorEl.className = 'play-error';
  errorEl.hidden = true;
  container.appendChild(errorEl);

  function showError(name) {
    errorEl.textContent = `Không phát được video: ${name}`;
    errorEl.hidden = false;
    if (mode !== 'paused') pause();
  }

  const clearError = () => {
    errorEl.hidden = true;
  };

  function makeVideo(name) {
    const v = document.createElement('video');
    v.preload = 'metadata';
    v.playsInline = true;
    v.hidden = true;
    v.src = mediaUrl(name);
    v.addEventListener('seeked', scheduleSeek);
    v.addEventListener('loadedmetadata', scheduleSeek);
    // Shown only for the file on screen; another file's error shows when
    // the playhead reaches it (see show()).
    v.addEventListener('error', () => {
      if (videos.get(name) === v && layout[current]?.name === name) showError(name);
    });
    v.addEventListener('playing', clearError);
    container.appendChild(v);
    return v;
  }

  function show(index) {
    if (index === current) return videos.get(layout[index].name);
    const old = current >= 0 && layout[current] ? videos.get(layout[current].name) : null;
    if (old) {
      old.pause();
      old.hidden = true;
    }
    current = index;
    const v = videos.get(layout[index].name);
    v.hidden = false;
    if (v.error) showError(layout[index].name);
    else clearError();
    if (mode === 'forward') startVideo(v);
    return v;
  }

  function startVideo(v) {
    v.playbackRate = rate;
    const p = v.play();
    if (!p) return;
    p.catch((err) => {
      // AbortError: paused again before playback started; nothing is wrong.
      if (err && err.name === 'AbortError') return;
      const name = [...videos].find(([, x]) => x === v)?.[0];
      if (name) showError(name);
    });
  }

  function scheduleSeek() {
    if (target !== null && !seekFrame) seekFrame = requestAnimationFrame(applySeek);
  }

  function applySeek() {
    seekFrame = 0;
    if (target === null || layout.length === 0) return;
    const index = indexAt(layout, target);
    const e = layout[index];
    const v = show(index);
    if (v.seeking) return; // 'seeked' schedules the latest target
    const local = Math.min(target - e.offset + NUDGE, e.duration);
    target = null;
    if (Math.abs(v.currentTime - local) > 1e-4) v.currentTime = local;
  }

  function seek(t) {
    if (layout.length === 0) return;
    head = Math.min(Math.max(t, 0), total());
    target = head;
    scheduleSeek();
    emit();
  }

  function tick(now) {
    loop = requestAnimationFrame(tick);
    const dt = Math.min((now - lastTick) / 1000, 0.25);
    lastTick = now;
    if (mode === 'reverse') {
      if (head <= 0) return pause();
      seek(Math.max(head - dt * rate, 0));
      return;
    }
    const e = layout[current];
    const v = e && videos.get(e.name);
    if (!v || target !== null || v.seeking) return;
    if (v.ended || v.currentTime >= e.duration - NUDGE) {
      if (current + 1 >= layout.length) {
        head = total();
        pause();
        emit();
        return;
      }
      target = layout[current + 1].offset;
      head = target;
      applySeek();
      emit();
      return;
    }
    const t = e.offset + v.currentTime;
    if (t !== head) {
      head = t;
      emit();
    }
    // Load the start of the next file shortly before this one ends.
    const next = layout[current + 1];
    if (next && primed !== current + 1 && e.duration - v.currentTime < PRIME_BEFORE_END) {
      primed = current + 1;
      const nv = videos.get(next.name);
      nv.currentTime = 0;
    }
  }

  function startLoop() {
    if (!loop) {
      lastTick = performance.now();
      loop = requestAnimationFrame(tick);
    }
  }

  function play() {
    if (layout.length === 0) return;
    if (head >= total() - 1e-3) seek(0);
    mode = 'forward';
    rate = 1;
    if (current >= 0) startVideo(videos.get(layout[current].name));
    startLoop();
  }

  function pause() {
    mode = 'paused';
    rate = 1;
    if (loop) cancelAnimationFrame(loop);
    loop = 0;
    for (const v of videos.values()) v.pause();
    // Stop on a whole frame so marking and the timecode agree with the picture.
    if (layout.length > 0) seek(snap(layout, head));
  }

  function shuttle(dir) {
    if (dir === 0 || layout.length === 0) return pause();
    const want = dir > 0 ? 'forward' : 'reverse';
    if (mode === want) {
      rate = RATES[Math.min(RATES.indexOf(rate) + 1, RATES.length - 1)];
      if (mode === 'forward' && current >= 0) videos.get(layout[current].name).playbackRate = rate;
      return;
    }
    if (want === 'forward') return play();
    for (const v of videos.values()) v.pause();
    mode = 'reverse';
    rate = 1;
    startLoop();
  }

  function step(frames) {
    if (layout.length === 0) return;
    if (mode !== 'paused') pause();
    const e = layout[indexAt(layout, head)];
    const frame = Math.floor((head - e.offset) * e.fps + 1e-6);
    seek(snap(layout, e.offset + (frame + frames) / e.fps));
  }

  function setLayout(next) {
    const names = new Set(next.map((e) => e.name));
    for (const [name, v] of videos) {
      if (!names.has(name)) {
        v.pause();
        v.removeAttribute('src');
        v.load();
        v.remove();
        videos.delete(name);
      }
    }
    for (const e of next) if (!videos.has(e.name)) videos.set(e.name, makeVideo(e.name));
    // Keep the playhead on the same moment of the same file when files move.
    const at = current >= 0 && layout[current] ? layout[current] : null;
    const moved = at && next.find((e) => e.name === at.name);
    const t = moved ? moved.offset + (head - at.offset) : head;
    layout = next;
    current = -1;
    primed = -1;
    clearError();
    for (const v of videos.values()) v.hidden = true;
    if (layout.length === 0) {
      if (mode !== 'paused') pause();
      head = 0;
      emit();
      return;
    }
    seek(t);
  }

  setLayout(initialLayout);

  return {
    seek,
    time: () => head,
    play,
    pause,
    toggle: () => (mode === 'paused' ? play() : pause()),
    shuttle,
    step,
    onTime(cb) {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    setLayout,
    playing: () => mode !== 'paused',
  };
}
