import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildLayout,
  totalDuration,
  toLocal,
  toGlobal,
  snap,
  createEditor,
  markIn,
  markOut,
  newMatch,
  selectMatch,
  deleteSegmentAt,
  moveEdge,
  updateMatch,
  removeSource,
  addSource,
  undo,
  segmentsOnTimeline,
  keptDuration,
  previewTitle,
  matchProblems,
  removeMatch,
  recordedDate,
  editorFromStored,
  storedSession,
} from '../../app/static/js/model.js';

const SOURCES = [
  { name: 'a.mov', duration: 100, fps: 30 },
  { name: 'b.mov', duration: 50, fps: 30 },
];

function deepFreeze(value) {
  if (value && typeof value === 'object' && !Object.isFrozen(value)) {
    Object.freeze(value);
    for (const key of Object.keys(value)) deepFreeze(value[key]);
  }
  return value;
}

function ids() {
  let n = 0;
  return () => `m${++n}`;
}

function emptySession() {
  return { sources: ['a.mov', 'b.mov'], matches: [], selected_match_id: null };
}

function match(id, segments, extra = {}) {
  return {
    id,
    match_type: 'md',
    team1: [],
    team2: [],
    tournament: 'Cafe Game',
    segments,
    ...extra,
  };
}

function editor(session = emptySession(), sources = SOURCES) {
  return deepFreeze(createEditor(deepFreeze(session), buildLayout(sources)));
}

function selected(state) {
  return state.session.matches.find((m) => m.id === state.session.selected_match_id);
}

// Two matches already on the timeline: m1 [10,20] and m2 [30,40] on a.mov.
function twoMatches(selectedId = 'm1') {
  return editor({
    sources: ['a.mov', 'b.mov'],
    matches: [
      match('m1', [{ source: 'a.mov', start: 10, end: 20 }]),
      match('m2', [{ source: 'a.mov', start: 30, end: 40 }]),
    ],
    selected_match_id: selectedId,
  });
}

test('layout nối các nguồn và đổi qua lại giữa thời gian chung và thời gian trong file', () => {
  const layout = buildLayout([...SOURCES, { name: 'c.mov', duration: 10, fps: 0 }]);
  assert.deepEqual(layout, [
    { name: 'a.mov', offset: 0, duration: 100, fps: 30 },
    { name: 'b.mov', offset: 100, duration: 50, fps: 30 },
    { name: 'c.mov', offset: 150, duration: 10, fps: 30 },
  ]);
  assert.equal(totalDuration(layout), 160);
  assert.deepEqual(toLocal(layout, 99.5), { name: 'a.mov', time: 99.5 });
  assert.deepEqual(toLocal(layout, 100), { name: 'b.mov', time: 0 });
  assert.deepEqual(toLocal(layout, 160), { name: 'c.mov', time: 10 });
  assert.equal(toGlobal(layout, 'b.mov', 10), 110);
});

test('I rồi O tạo một đoạn của trận đang chọn', () => {
  let s = editor();
  s = markIn(s, 10, ids());
  s = markOut(s, 20);
  assert.equal(s.open, null);
  assert.equal(s.session.matches.length, 1);
  assert.equal(s.session.selected_match_id, 'm1');
  assert.deepEqual(selected(s).segments, [{ source: 'a.mov', start: 10, end: 20 }]);
});

test('O rồi I giữa trận tạo hai đoạn, khúc giữa bị bỏ', () => {
  let s = editor();
  s = markIn(s, 10, ids());
  s = markOut(s, 20);
  s = markIn(s, 30);
  s = markOut(s, 40);
  assert.deepEqual(selected(s).segments, [
    { source: 'a.mov', start: 10, end: 20 },
    { source: 'a.mov', start: 30, end: 40 },
  ]);
  assert.equal(keptDuration(selected(s)), 20);
});

test('đoạn mở chạy qua vạch nối được tách thành hai đoạn liền nhau cùng trận', () => {
  let s = editor();
  s = markIn(s, 90, ids());
  s = markOut(s, 110);
  assert.deepEqual(selected(s).segments, [
    { source: 'a.mov', start: 90, end: 100 },
    { source: 'b.mov', start: 0, end: 10 },
  ]);
});

test('đoạn mở qua vạch nối với nguồn 29.97fps có điểm cuối đúng bằng thời lượng file', () => {
  let s = editor(emptySession(), [
    { name: 'a.mov', duration: 100.01, fps: 29.97 },
    { name: 'b.mov', duration: 50, fps: 29.97 },
  ]);
  s = markIn(s, 99, ids());
  s = markOut(s, 101);
  const [first, second] = selected(s).segments;
  assert.equal(first.source, 'a.mov');
  assert.equal(first.end, 100.01);
  assert.equal(second.source, 'b.mov');
  assert.equal(second.start, 0);
  assert.equal(second.end, 30 / 29.97);
});

test('các đoạn của một trận luôn xếp theo thời gian', () => {
  let s = editor();
  s = markIn(s, 30, ids());
  s = markOut(s, 40);
  s = markIn(s, 10);
  s = markOut(s, 20);
  assert.deepEqual(
    selected(s).segments.map((seg) => seg.start),
    [10, 30],
  );
});

test('N đóng đoạn đang mở, tạo và chọn trận mới, kế thừa loại trận trước', () => {
  const next = ids();
  let s = editor();
  s = markIn(s, 10, next);
  s = updateMatch(s, 'm1', { match_type: 'xd', tournament: 'Giải Mùa Thu' });
  s = newMatch(s, 20, next);
  assert.equal(s.open, null);
  assert.deepEqual(s.session.matches[0].segments, [{ source: 'a.mov', start: 10, end: 20 }]);
  assert.equal(s.session.matches.length, 2);
  assert.equal(s.session.selected_match_id, 'm2');
  assert.deepEqual(selected(s), match('m2', [], { match_type: 'xd', tournament: 'Giải Mùa Thu' }));
});

test('trận đầu tiên dùng loại md và giải mặc định', () => {
  let s = deepFreeze(createEditor(emptySession(), buildLayout(SOURCES), { tournament: 'CLB Sun' }));
  s = markIn(s, 10, ids());
  assert.deepEqual(selected(s), match('m1', [], { tournament: 'CLB Sun' }));
  const plain = markIn(editor(), 10, ids());
  assert.equal(selected(plain).tournament, 'Cafe Game');
});

test('mã trận mặc định chỉ gồm chữ thường, số và dấu gạch ngang', () => {
  let s = markIn(editor(), 10);
  s = markOut(s, 20);
  s = newMatch(s, 30);
  const [a, b] = s.session.matches.map((m) => m.id);
  assert.match(a, /^[a-z0-9-]+$/);
  assert.match(b, /^[a-z0-9-]+$/);
  assert.notEqual(a, b);
});

test('N khi trận đang chọn chưa có đoạn nào thì không tạo thêm trận rỗng', () => {
  const next = ids();
  let s = editor();
  s = newMatch(s, 0, next);
  assert.equal(s.session.matches.length, 1);
  const again = newMatch(s, 5, next);
  assert.equal(again, s);
});

test('đoạn mới bị chặn ở mép đoạn kề bên, không chồng lên trận khác', () => {
  let s = twoMatches('m2');
  s = markIn(s, 15);
  assert.deepEqual(s.open, { matchId: 'm2', start: 20 });
  // Closing past m2's own segment stops at its start.
  s = markOut(s, 35);
  assert.deepEqual(selected(s).segments, [
    { source: 'a.mov', start: 20, end: 30 },
    { source: 'a.mov', start: 30, end: 40 },
  ]);
});

test('O bị chặn ở đầu đoạn của trận khác', () => {
  let s = twoMatches('m1');
  s = markIn(s, 22);
  s = markOut(s, 50);
  assert.deepEqual(s.session.matches[0].segments, [
    { source: 'a.mov', start: 10, end: 20 },
    { source: 'a.mov', start: 22, end: 30 },
  ]);
});

test('I khi đã có đoạn mở thì đặt lại điểm vào', () => {
  let s = editor();
  s = markIn(s, 10, ids());
  s = markIn(s, 12);
  assert.deepEqual(s.open, { matchId: 'm1', start: 12 });
  assert.equal(s.undo.length, 2);
});

test('I trong một đoạn đã đóng của trận đang chọn dời điểm vào', () => {
  let s = twoMatches('m1');
  s = markIn(s, 15);
  assert.equal(s.open, null);
  assert.deepEqual(s.session.matches[0].segments, [{ source: 'a.mov', start: 15, end: 20 }]);
});

test('O trong một đoạn đã đóng của trận đang chọn dời điểm ra', () => {
  let s = twoMatches('m1');
  s = markOut(s, 15);
  assert.deepEqual(s.session.matches[0].segments, [{ source: 'a.mov', start: 10, end: 15 }]);
});

test('O khi không có đoạn mở và con trỏ ngoài mọi đoạn thì không đổi gì', () => {
  const s = twoMatches('m1');
  assert.equal(markOut(s, 25), s);
  // Inside another match's segment does not edit it either.
  assert.equal(markOut(s, 35), s);
});

test('O trước điểm I thì không tạo đoạn âm', () => {
  let s = editor();
  s = markIn(s, 20, ids());
  const before = s;
  s = markOut(s, 10);
  assert.equal(s.open, null);
  assert.deepEqual(s.session, before.session);
  assert.deepEqual(selected(s).segments, []);
  // O at exactly the I point, after snapping, also discards.
  let t = markIn(editor(), 20, ids());
  t = markOut(t, 20.01);
  assert.equal(t.open, null);
  assert.deepEqual(selected(t).segments, []);
});

test('moveEdge kẹp theo đoạn kề bên, theo biên file nguồn, và giữ đoạn dài ít nhất 1 frame', () => {
  const s = editor({
    sources: ['a.mov', 'b.mov'],
    matches: [
      match('m1', [
        { source: 'a.mov', start: 10, end: 20 },
        { source: 'b.mov', start: 5, end: 10 },
      ]),
      match('m2', [{ source: 'a.mov', start: 30, end: 40 }]),
    ],
    selected_match_id: 'm1',
  });
  // Neighbour of another match.
  let r = moveEdge(s, 'm1', 0, 'end', 35);
  assert.deepEqual(r.session.matches[0].segments[0], { source: 'a.mov', start: 10, end: 30 });
  r = moveEdge(s, 'm2', 0, 'start', 5);
  assert.deepEqual(r.session.matches[1].segments[0], { source: 'a.mov', start: 20, end: 40 });
  // Source bounds: b.mov's segment cannot start before b.mov does.
  r = moveEdge(s, 'm1', 1, 'start', 90);
  assert.deepEqual(r.session.matches[0].segments[1], { source: 'b.mov', start: 0, end: 10 });
  r = moveEdge(s, 'm1', 1, 'end', 400);
  assert.deepEqual(r.session.matches[0].segments[1], { source: 'b.mov', start: 5, end: 50 });
  // At least one frame long.
  r = moveEdge(s, 'm1', 0, 'start', 25);
  assert.deepEqual(r.session.matches[0].segments[0], { source: 'a.mov', start: 599 / 30, end: 20 });
  r = moveEdge(s, 'm1', 0, 'end', 0);
  assert.deepEqual(r.session.matches[0].segments[0], { source: 'a.mov', start: 10, end: 301 / 30 });
  // Snapped to the frame grid of the segment's own source.
  r = moveEdge(s, 'm1', 1, 'end', 112.017);
  assert.equal(r.session.matches[0].segments[1].end, 361 / 30);
  // No change and unknown segment return the same state.
  assert.equal(moveEdge(s, 'm1', 0, 'start', 10), s);
  assert.equal(moveEdge(s, 'm1', 7, 'start', 10), s);
});

test('moveEdge khớp đúng giá trị khi chạm đoạn kề bên trong nguồn thứ hai', () => {
  const s = editor({
    sources: ['a.mov', 'b.mov'],
    matches: [
      match('m1', [{ source: 'b.mov', start: 0, end: 301 / 30 }]),
      match('m2', [{ source: 'b.mov', start: 20, end: 30 }]),
    ],
    selected_match_id: 'm2',
  });
  const r = moveEdge(s, 'm2', 0, 'start', 100);
  assert.equal(r.session.matches[1].segments[0].start, 301 / 30);
});

test('deleteSegmentAt xoá đúng đoạn dưới con trỏ', () => {
  let s = editor({
    sources: ['a.mov', 'b.mov'],
    matches: [
      match('m1', [
        { source: 'a.mov', start: 10, end: 20 },
        { source: 'a.mov', start: 50, end: 60 },
      ]),
      match('m2', [{ source: 'a.mov', start: 30, end: 40 }]),
    ],
    selected_match_id: 'm1',
  });
  // Deletes in a match that is not selected; the emptied match stays.
  let r = deleteSegmentAt(s, 35);
  assert.deepEqual(r.session.matches[1].segments, []);
  assert.equal(r.session.matches.length, 2);
  assert.deepEqual(r.session.matches[0], s.session.matches[0]);
  r = deleteSegmentAt(s, 55);
  assert.deepEqual(r.session.matches[0].segments, [{ source: 'a.mov', start: 10, end: 20 }]);
  assert.equal(deleteSegmentAt(s, 25), s);
  // An open segment under the cursor is discarded.
  s = markIn(s, 70);
  r = deleteSegmentAt(s, 75);
  assert.equal(r.open, null);
  assert.deepEqual(r.session, s.session);
});

test('mọi điểm được làm tròn theo frame', () => {
  const layout = buildLayout(SOURCES);
  assert.equal(snap(layout, 10.017), 301 / 30);
  assert.equal(snap(layout, 110.017), 100 + 301 / 30);
  assert.equal(snap(layout, -3), 0);
  assert.equal(snap(layout, 999), 150);
  let s = editor();
  s = markIn(s, 10.017, ids());
  s = markOut(s, 19.99);
  assert.deepEqual(selected(s).segments, [{ source: 'a.mov', start: 301 / 30, end: 20 }]);
  const slow = buildLayout([{ name: 'x.mov', duration: 10, fps: 29.97 }]);
  assert.equal(snap(slow, 1), 30 / 29.97);
});

test('undo hoàn tác từng thao tác theo thứ tự ngược lại, kể cả updateMatch', () => {
  const s0 = editor();
  const s1 = markIn(s0, 10, ids());
  const s2 = markOut(s1, 20);
  const s3 = updateMatch(s2, 'm1', { team1: ['Nam'] });
  const s4 = selectMatch(s3, 'm1');
  assert.equal(s4, s3);
  let u = undo(s3);
  assert.deepEqual(u.session, s2.session);
  assert.deepEqual(u.open, s2.open);
  u = undo(u);
  assert.deepEqual(u.session, s1.session);
  assert.deepEqual(u.open, { matchId: 'm1', start: 10 });
  u = undo(u);
  assert.deepEqual(u.session, s0.session);
  assert.equal(u.open, null);
  assert.equal(undo(u), u);
});

test('thao tác không đổi gì thì không thêm vào undo', () => {
  const s = twoMatches('m1');
  assert.equal(updateMatch(s, 'm1', { team1: [] }), s);
  assert.equal(selectMatch(s, 'nope'), s);
  const r = selectMatch(s, 'm2');
  assert.equal(r.session.selected_match_id, 'm2');
  assert.equal(r.undo.length, 0);
});

test('undo giữ tối đa 200 bước', () => {
  let s = twoMatches('m1');
  for (let i = 0; i < 205; i++) s = updateMatch(s, 'm1', { tournament: `G${i}` });
  assert.equal(s.undo.length, 200);
});

test('thao tác trên trận đang khoá không đổi state', () => {
  const locked = new Set(['m1']);
  const s = twoMatches('m1');
  assert.equal(markIn(s, 50, undefined, locked), s);
  assert.equal(markIn(s, 15, undefined, locked), s);
  assert.equal(markOut(s, 15, locked), s);
  assert.equal(deleteSegmentAt(s, 15, locked), s);
  assert.equal(moveEdge(s, 'm1', 0, 'end', 25, locked), s);
  assert.equal(updateMatch(s, 'm1', { team1: ['Nam'] }, locked), s);
  assert.equal(removeSource(s, 'a.mov', locked), s);
  // Other matches stay editable.
  assert.notEqual(deleteSegmentAt(s, 35, locked), s);
  // N leaves the locked match alone and starts a new one.
  const r = newMatch(s, 50, () => 'm3', locked);
  assert.equal(r.session.matches.length, 3);
  assert.deepEqual(r.session.matches[0], s.session.matches[0]);
  assert.equal(r.session.selected_match_id, 'm3');
});

test('removeSource xoá các đoạn của nguồn đó và bỏ trận rỗng không có tên', () => {
  let s = editor({
    sources: ['a.mov', 'b.mov'],
    matches: [
      match('m1', [{ source: 'a.mov', start: 10, end: 20 }]),
      match('m2', [{ source: 'a.mov', start: 30, end: 40 }], { team1: ['Nam'] }),
      match('m3', [
        { source: 'a.mov', start: 90, end: 100 },
        { source: 'b.mov', start: 0, end: 10 },
      ]),
      match('m4', [{ source: 'b.mov', start: 20, end: 30 }]),
    ],
    selected_match_id: 'm1',
  });
  s = selectMatch(s, 'm4');
  s = markIn(s, 140);
  s = selectMatch(s, 'm1');
  const r = removeSource(s, 'a.mov');
  assert.deepEqual(r.session.sources, ['b.mov']);
  assert.deepEqual(
    r.session.matches.map((m) => [m.id, m.segments]),
    [
      ['m2', []],
      ['m3', [{ source: 'b.mov', start: 0, end: 10 }]],
      ['m4', [{ source: 'b.mov', start: 20, end: 30 }]],
    ],
  );
  assert.equal(r.session.selected_match_id, null);
  assert.deepEqual(r.layout, [{ name: 'b.mov', offset: 0, duration: 50, fps: 30 }]);
  // The open segment in b.mov moves with the new layout.
  assert.deepEqual(r.open, { matchId: 'm4', start: 40 });
  // Undo brings the source and layout back.
  const u = undo(r);
  assert.deepEqual(u.session, s.session);
  assert.deepEqual(u.layout, s.layout);
  assert.equal(removeSource(s, 'zzz.mov'), s);
});

test('removeSource bỏ đoạn mở bắt đầu trong nguồn đó', () => {
  let s = markIn(editor(), 10, ids());
  s = removeSource(s, 'a.mov');
  assert.equal(s.open, null);
  assert.equal(s.session.selected_match_id, 'm1');
});

test('segmentsOnTimeline trả các đoạn theo trục chung, kể cả đoạn đang mở', () => {
  let s = editor({
    sources: ['a.mov', 'b.mov'],
    matches: [
      match('m1', [{ source: 'b.mov', start: 0, end: 10 }]),
      match('m2', [{ source: 'a.mov', start: 30, end: 40 }]),
    ],
    selected_match_id: 'm2',
  });
  s = markIn(s, 50);
  assert.deepEqual(segmentsOnTimeline(s, 120), [
    { matchId: 'm2', segIndex: 0, start: 30, end: 40, open: false },
    { matchId: 'm2', segIndex: null, start: 50, end: 100, open: true },
    { matchId: 'm1', segIndex: 0, start: 100, end: 110, open: false },
  ]);
  assert.equal(segmentsOnTimeline(s)[1].end, 50);
});

test('previewTitle khớp định dạng Python', () => {
  const m = match('m1', [], { team1: ['Nam', 'Hùng'], team2: ['Tú', 'Long'] });
  assert.equal(previewTitle(m, '2026-11-20'), 'Nam/Hùng vs Tú/Long | Cafe Game (2026-11-20)');
});

test('matchProblems báo thiếu tên một bên và chưa có đoạn', () => {
  assert.deepEqual(matchProblems(match('m1', [], { team1: ['Nam'], team2: ['  '] })), [
    'Thiếu tên người chơi đội 2',
    'Chưa có đoạn nào',
  ]);
  assert.deepEqual(matchProblems(match('m1', [])), [
    'Thiếu tên người chơi đội 1',
    'Thiếu tên người chơi đội 2',
    'Chưa có đoạn nào',
  ]);
  const ok = match('m1', [{ source: 'a.mov', start: 0, end: 1 }], { team1: ['Nam'], team2: ['Tú'] });
  assert.deepEqual(matchProblems(ok), []);
});

test('moveEdge giữ ít nhất 1 frame khi mép kia nằm ở cuối file lệch lưới 29.97fps', () => {
  const s = editor(
    {
      sources: ['a.mov'],
      matches: [match('m1', [{ source: 'a.mov', start: 40, end: 50.003 }])],
      selected_match_id: 'm1',
    },
    [{ name: 'a.mov', duration: 50.003, fps: 29.97 }],
  );
  const seg = moveEdge(s, 'm1', 0, 'start', 60).session.matches[0].segments[0];
  assert.equal(seg.start, 1497 / 29.97);
  assert.ok(seg.end - seg.start >= 1 / 29.97);
});

// ---------------------------------------------------------------- addSource

const INFOS = [
  { name: 'a.mov', duration: 100, fps: 30, recorded_at: '2026-11-20T19:00:00+07:00' },
  { name: 'c.mov', duration: 20, fps: 25, recorded_at: '2026-11-20T19:30:00+07:00' },
  { name: 'b.mov', duration: 50, fps: 30, recorded_at: '2026-11-20T20:00:00+07:00' },
];

test('addSource chèn nguồn theo thứ tự danh sách đã sắp và giữ lịch sử hoàn tác', () => {
  let s = editor({
    sources: ['a.mov', 'b.mov'],
    matches: [match('m1', [{ source: 'b.mov', start: 0, end: 10 }])],
    selected_match_id: 'm1',
  });
  s = markIn(s, 120);
  s = deepFreeze(s);
  const r = addSource(s, 'c.mov', INFOS);
  assert.deepEqual(r.session.sources, ['a.mov', 'c.mov', 'b.mov']);
  assert.deepEqual(r.layout, [
    { name: 'a.mov', offset: 0, duration: 100, fps: 30 },
    { name: 'c.mov', offset: 100, duration: 20, fps: 25 },
    { name: 'b.mov', offset: 120, duration: 50, fps: 30 },
  ]);
  // Segments are local to their file, so they do not move in the session…
  assert.deepEqual(r.session.matches, s.session.matches);
  // …and the open segment keeps its place in b.mov.
  assert.deepEqual(r.open, { matchId: 'm1', start: 140 });
  assert.equal(r.undo.length, s.undo.length + 1);
  const u = undo(r);
  assert.deepEqual(u.session, s.session);
  assert.deepEqual(u.layout, s.layout);
  assert.deepEqual(u.open, s.open);
});

test('addSource vào phiên rỗng và bỏ qua nguồn đã có hoặc không có thời lượng', () => {
  const s = editor({ sources: [], matches: [], selected_match_id: null }, []);
  const r = addSource(s, 'b.mov', INFOS);
  assert.deepEqual(r.session.sources, ['b.mov']);
  assert.deepEqual(r.layout, [{ name: 'b.mov', offset: 0, duration: 50, fps: 30 }]);
  assert.equal(addSource(r, 'b.mov', INFOS), r);
  assert.equal(addSource(r, 'zzz.mov', INFOS), r);
  assert.equal(addSource(r, 'x.mov', [{ name: 'x.mov', missing: true }]), r);
});

// ---------------------------------------------------------------- missing sources

// a.mov and b.mov on disk; gone.mov is in the session but not on the timeline.
function withMissing() {
  return editor(
    {
      sources: ['a.mov', 'gone.mov', 'b.mov'],
      matches: [
        match('m1', [
          { source: 'a.mov', start: 10, end: 20 },
          { source: 'gone.mov', start: 5, end: 8 },
        ]),
        match('m2', [{ source: 'gone.mov', start: 0, end: 3 }]),
      ],
      selected_match_id: 'm1',
    },
    SOURCES,
  );
}

test('nguồn bị thiếu trên đĩa không làm hỏng editor và đoạn của nó giữ nguyên', () => {
  const s = withMissing();
  assert.deepEqual(segmentsOnTimeline(s, 50), [
    { matchId: 'm1', segIndex: 0, start: 10, end: 20, open: false },
  ]);
  // Marking, moving and deleting still work and leave gone.mov untouched.
  let r = markIn(s, 30, ids());
  r = markOut(r, 40);
  assert.deepEqual(r.session.matches[0].segments, [
    { source: 'a.mov', start: 10, end: 20 },
    { source: 'a.mov', start: 30, end: 40 },
    { source: 'gone.mov', start: 5, end: 8 },
  ]);
  assert.deepEqual(r.session.matches[1], s.session.matches[1]);
  assert.equal(moveEdge(s, 'm1', 1, 'end', 50), s);
  assert.equal(deleteSegmentAt(s, 6), s);
  const d = deleteSegmentAt(s, 15);
  assert.deepEqual(d.session.matches[0].segments, [{ source: 'gone.mov', start: 5, end: 8 }]);
  const n = newMatch(markIn(s, 60), 70, () => 'm3');
  assert.deepEqual(n.session.matches[0].segments.at(-1), { source: 'gone.mov', start: 5, end: 8 });
  assert.equal(n.session.selected_match_id, 'm3');
});

test('removeSource bỏ được nguồn bị thiếu trên đĩa', () => {
  const r = removeSource(withMissing(), 'gone.mov');
  assert.deepEqual(r.session.sources, ['a.mov', 'b.mov']);
  assert.deepEqual(
    r.session.matches.map((m) => [m.id, m.segments]),
    [['m1', [{ source: 'a.mov', start: 10, end: 20 }]]],
  );
  assert.deepEqual(r.layout, buildLayout(SOURCES));
});

test('addSource giữ nguồn bị thiếu trong phiên', () => {
  const s = withMissing();
  const infos = [...SOURCES.slice(0, 1), { name: 'c.mov', duration: 20, fps: 25 }, SOURCES[1]];
  const r = addSource(s, 'c.mov', infos);
  assert.deepEqual(r.session.sources, ['a.mov', 'c.mov', 'b.mov', 'gone.mov']);
  assert.deepEqual(r.layout.map((e) => e.name), ['a.mov', 'c.mov', 'b.mov']);
});

test('removeMatch xoá trận, chọn trận trước đó và hoàn tác được', () => {
  const s = editor({
    sources: ['a.mov', 'b.mov'],
    matches: [
      match('m1', [{ source: 'a.mov', start: 10, end: 20 }]),
      match('m2', [{ source: 'a.mov', start: 30, end: 40 }]),
      match('m3', []),
    ],
    selected_match_id: 'm2',
  });
  const r = removeMatch(s, 'm2');
  assert.deepEqual(r.session.matches.map((m) => m.id), ['m1', 'm3']);
  assert.equal(r.session.selected_match_id, 'm1');
  assert.deepEqual(undo(r).session, s.session);
  // Removing a match that is not selected keeps the selection.
  assert.equal(removeMatch(s, 'm3').session.selected_match_id, 'm2');
  // The first match has no previous one.
  const first = removeMatch(selectMatch(s, 'm1'), 'm1');
  assert.equal(first.session.selected_match_id, null);
  assert.equal(removeMatch(s, 'nope'), s);
});

test('removeMatch bỏ đoạn đang mở của trận đó, giữ đoạn mở của trận khác', () => {
  const s = markIn(twoMatches('m2'), 60);
  assert.deepEqual(s.open, { matchId: 'm2', start: 60 });
  const r = removeMatch(s, 'm2');
  assert.equal(r.open, null);
  assert.deepEqual(undo(r).open, s.open);
  const k = removeMatch(s, 'm1');
  assert.deepEqual(k.open, s.open);
});

test('removeMatch không xoá trận đang khoá', () => {
  const s = twoMatches('m1');
  assert.equal(removeMatch(s, 'm1', new Set(['m1'])), s);
});

test('undo không hoàn tác thay đổi của trận đã khoá sau đó', () => {
  const s0 = twoMatches('m1');
  const s1 = updateMatch(s0, 'm1', { team1: ['Nam'] });
  const s2 = updateMatch(s1, 'm2', { team1: ['Tú'] });
  const locked = new Set(['m1']);
  // Undoing m2's change leaves m1 alone: allowed.
  const u = undo(s2, locked);
  assert.deepEqual(u.session, s1.session);
  // The next step would change locked m1: blocked.
  assert.equal(undo(u, locked), u);
  // A step that would bring back or drop a locked match is blocked too.
  const s3 = newMatch(s2, 50, () => 'm3');
  assert.equal(undo(s3, new Set(['m3'])), s3);
  const s4 = removeMatch(s2, 'm2');
  assert.equal(undo(s4, new Set(['m2'])), s4);
  // Without locks undo works as before.
  assert.deepEqual(undo(u).session, s0.session);
});

test('recordedDate lấy ngày quay của nguồn chứa đoạn đầu tiên', () => {
  const dates = { 'a.mov': '2026-11-19', 'b.mov': '2026-11-20' };
  const session = { sources: ['b.mov', 'a.mov'] };
  const m = match('m1', [{ source: 'a.mov', start: 1, end: 2 }, { source: 'b.mov', start: 0, end: 1 }]);
  assert.equal(recordedDate(m, session, dates, '2000-01-01'), '2026-11-19');
  // No segment yet: the first session source.
  assert.equal(recordedDate(match('m2', []), session, dates, '2000-01-01'), '2026-11-20');
  // Nothing known: today.
  assert.equal(recordedDate(match('m2', []), { sources: [] }, dates, '2000-01-01'), '2000-01-01');
  assert.equal(
    recordedDate(match('m3', [{ source: 'gone.mov', start: 0, end: 1 }]), session, dates, '2000-01-01'),
    '2000-01-01',
  );
});

// ---------------------------------------------------------------- stored open point

const OPEN_PROBLEM = 'Còn một đoạn đang mở — bấm O để đóng';

function stored(open, extra = {}) {
  return {
    sources: ['a.mov', 'b.mov'],
    matches: [match('m1', [{ source: 'b.mov', start: 0, end: 2 }])],
    selected_match_id: 'm1',
    open,
    revision: 7,
    ...extra,
  };
}

test('editorFromStored đặt đoạn đang mở vào timeline theo giờ toàn cục', () => {
  const { state, hiddenOpen } = editorFromStored(
    deepFreeze(stored({ match_id: 'm1', source: 'b.mov', time: 10 })),
    buildLayout(SOURCES),
  );
  assert.deepEqual(state.open, { matchId: 'm1', start: 110 });
  assert.equal(hiddenOpen, null);
  assert.equal('open' in state.session, false);
  assert.equal('revision' in state.session, false);
  assert.deepEqual(state.undo, []);
});

test('storedSession ghi đoạn đang mở theo giờ của file nguồn', () => {
  const { state } = editorFromStored(deepFreeze(stored(null)), buildLayout(SOURCES));
  const s = markIn(state, 100 + 307 / 30, ids());
  const out = storedSession(s, null);
  assert.deepEqual(out.open, { match_id: 'm1', source: 'b.mov', time: 307 / 30 });
  assert.equal('revision' in out, false);
  assert.deepEqual(storedSession(state, null).open, null);
});

test('đoạn đang mở ngay sau một đoạn ở file khác offset vẫn đúng lưới frame', () => {
  const sources = [
    { name: 'a.mov', duration: 600.123, fps: 29.97 },
    { name: 'b.mov', duration: 50, fps: 29.97 },
  ];
  const session = {
    sources: ['a.mov', 'b.mov'],
    matches: [match('m1', []), match('m2', [{ source: 'b.mov', start: 30 / 29.97, end: 299 / 29.97 }])],
    selected_match_id: 'm1',
  };
  // I inside m2's segment starts m1's open segment at that segment's end.
  const s = markIn(editor(session, sources), 600.123 + 100 / 29.97, ids());
  assert.equal(s.open.matchId, 'm1');
  assert.equal(storedSession(s, null).open.time, 299 / 29.97);
});

test('đoạn đang mở được lưu, tải lại và hoàn tác như trước', () => {
  const layout = buildLayout(SOURCES);
  const s1 = markIn(editorFromStored(deepFreeze(stored(null)), layout).state, 20, ids());
  const again = editorFromStored(deepFreeze({ ...storedSession(s1, null), revision: 8 }), layout).state;
  assert.deepEqual(again.open, s1.open);
  const closed = markOut(again, 30);
  assert.deepEqual(closed.session.matches[0].segments[0], { source: 'a.mov', start: 20, end: 30 });
  assert.deepEqual(undo(closed).open, again.open);
});

test('đoạn đang mở ở file đang thiếu không hiện nhưng được giữ nguyên khi lưu', () => {
  const open = { match_id: 'm1', source: 'b.mov', time: 9999 };
  const { state, hiddenOpen } = editorFromStored(deepFreeze(stored(open)), buildLayout([SOURCES[0]]));
  assert.equal(state.open, null);
  assert.deepEqual(hiddenOpen, open);
  assert.deepEqual(storedSession(state, hiddenOpen).open, open);
  // Bỏ file khỏi phiên, hoặc xoá trận, thì nó đi theo.
  const noSource = { ...state, session: { ...state.session, sources: ['a.mov'] } };
  assert.equal(storedSession(noSource, hiddenOpen).open, null);
  const noMatch = { ...state, session: { ...state.session, matches: [] } };
  assert.equal(storedSession(noMatch, hiddenOpen).open, null);
  // Bấm I ở chỗ khác thì đoạn mới thay nó.
  const marked = markIn(state, 50, ids());
  assert.deepEqual(storedSession(marked, hiddenOpen).open, { match_id: 'm1', source: 'a.mov', time: 50 });
});

test('đoạn đang mở của trận không còn thì không được đặt lên timeline', () => {
  const { state, hiddenOpen } = editorFromStored(
    deepFreeze(stored({ match_id: 'gone', source: 'a.mov', time: 1 })),
    buildLayout(SOURCES),
  );
  assert.equal(state.open, null);
  assert.equal(storedSession(state, hiddenOpen).open, null);
});

test('matchProblems: trận còn đoạn đang mở chưa upload được', () => {
  const ok = match('m1', [{ source: 'a.mov', start: 0, end: 1 }], { team1: ['Nam'], team2: ['Tú'] });
  assert.deepEqual(matchProblems(ok, 'm1'), [OPEN_PROBLEM]);
  assert.deepEqual(matchProblems(ok, 'm2'), []);
  assert.deepEqual(matchProblems(ok, null), []);
});

// ---------------------------------------------------------------- title rules

test('previewTitle: giải để trống thì dùng giải mặc định, tên được cắt khoảng trắng', () => {
  const m = match('m1', [], { team1: [' Nam ', '', 'Hùng'], team2: ['Tú'], tournament: '  ' });
  assert.equal(previewTitle(m, '2026-11-20'), 'Nam/Hùng vs Tú | Cafe Game (2026-11-20)');
});

test('matchProblems: tiêu đề quá 100 ký tự', () => {
  const seg = [{ source: 'a.mov', start: 0, end: 1 }];
  const long = match('m1', seg, { team1: ['A'.repeat(71)], team2: ['B'] });
  assert.deepEqual(matchProblems(long), ['Tiêu đề dài 101 ký tự, YouTube chỉ nhận tối đa 100']);
  const fits = match('m1', seg, { team1: ['A'.repeat(70)], team2: ['B'] });
  assert.deepEqual(matchProblems(fits), []);
});

test('matchProblems: tên hoặc giải có dấu < >', () => {
  const seg = [{ source: 'a.mov', start: 0, end: 1 }];
  const message = 'Tên người chơi và giải không được chứa dấu < hoặc >';
  assert.deepEqual(matchProblems(match('m1', seg, { team1: ['<Nam>'], team2: ['Tú'] })), [message]);
  assert.deepEqual(matchProblems(match('m1', seg, { team1: ['Nam'], team2: ['Tú'], tournament: 'Cup > 1' })), [message]);
});

// ---------------------------------------------------------------- open point as an obstacle

// The rule the stored session must keep: the open point never lies strictly
// inside a segment of its source.
function assertOpenOutsideSegments(state) {
  const { open } = storedSession(state, null);
  if (!open) return;
  for (const m of state.session.matches) {
    for (const s of m.segments) {
      if (s.source !== open.source) continue;
      assert.ok(!(s.start < open.time && open.time < s.end),
        `open ${open.time} inside ${m.id} [${s.start}, ${s.end}]`);
    }
  }
}

function withOpenAt20(m1Segments, openMatch = 'm2') {
  const session = {
    sources: ['a.mov', 'b.mov'],
    matches: [match('m1', m1Segments), match('m2', [])],
    selected_match_id: openMatch,
  };
  const s = markIn(editor(session), 20, ids());
  assert.deepEqual(s.open, { matchId: openMatch, start: 20 });
  return s;
}

test('moveEdge: kéo mép cuối qua điểm đang mở thì dừng ở đó (lỗi reviewer báo)', () => {
  const s = withOpenAt20([{ source: 'a.mov', start: 0, end: 10 }]);
  const moved = moveEdge(s, 'm1', 0, 'end', 30);
  assert.equal(moved.session.matches[0].segments[0].end, 20);
  assertOpenOutsideSegments(moved);
});

test('moveEdge: kéo mép đầu qua điểm đang mở thì dừng ở đó', () => {
  const s = withOpenAt20([{ source: 'a.mov', start: 30, end: 40 }]);
  const moved = moveEdge(s, 'm1', 0, 'start', 5);
  assert.equal(moved.session.matches[0].segments[0].start, 20);
  assertOpenOutsideSegments(moved);
});

test('moveEdge: điểm đang mở của chính trận đó cũng chặn', () => {
  const s = withOpenAt20([{ source: 'a.mov', start: 0, end: 10 }], 'm1');
  const moved = moveEdge(s, 'm1', 0, 'end', 30);
  assert.equal(moved.session.matches[0].segments[0].end, 20);
  assertOpenOutsideSegments(moved);
});

test('moveEdge: điểm đang mở ở file khác không chặn', () => {
  const session = {
    sources: ['a.mov', 'b.mov'],
    matches: [match('m1', [{ source: 'a.mov', start: 0, end: 10 }]), match('m2', [])],
    selected_match_id: 'm2',
  };
  const s = markIn(editor(session), 120, ids());
  assert.equal(moveEdge(s, 'm1', 0, 'end', 30).session.matches[0].segments[0].end, 30);
});

test('I/O trên đoạn đã đóng và I khi đang mở không bao giờ đặt điểm mở vào trong đoạn', () => {
  const segs = [{ source: 'a.mov', start: 0, end: 10 }, { source: 'a.mov', start: 40, end: 50 }];
  let s = editor({ sources: ['a.mov', 'b.mov'], matches: [match('m1', segs), match('m2', [{ source: 'a.mov', start: 60, end: 70 }])], selected_match_id: 'm1' });
  for (const t of [5, 45, 65, 20, 3, 62, 48]) {
    s = markIn(s, t, ids());
    assertOpenOutsideSegments(s);
  }
  s = markOut(s, 55);
  assertOpenOutsideSegments(s);
  // With no open segment, I and O move the selected match's own edges.
  s = markIn(s, 42, ids());
  s = markOut(s, 47);
  assert.equal(s.open, null);
  s = markIn(s, 25, ids());
  for (const t of [4, 44, 66]) {
    s = markIn(s, t, ids());
    assertOpenOutsideSegments(s);
  }
});
