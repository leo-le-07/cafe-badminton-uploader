import test from 'node:test';
import assert from 'node:assert/strict';

import { createModeState, createModeToggle } from '../../app/static/js/mode.js';

test('đổi mode thành công thì lưu rồi mới đổi', async () => {
  const saved = [];
  const s = createModeState('dev', async (m) => { saved.push(m); });
  assert.equal(await s.set('production'), true);
  assert.equal(s.get(), 'production');
  assert.deepEqual(saved, ['production']);
});

test('lưu mode thất bại thì vẫn ở mode cũ', async () => {
  const s = createModeState('dev', async () => { throw new Error('mất kết nối'); });
  assert.equal(await s.set('production'), false);
  assert.equal(s.get(), 'dev');
  // Lần sau vẫn thử lại được.
  assert.equal(s.busy(), false);
});

test('đang lưu thì không nhận thêm lần đổi khác', async () => {
  let release;
  let calls = 0;
  const s = createModeState('dev', () => { calls += 1; return new Promise((r) => { release = r; }); });
  const first = s.set('production');
  assert.equal(s.busy(), true);
  assert.equal(s.get(), 'dev');
  assert.equal(await s.set('dev'), false);
  release();
  assert.equal(await first, true);
  assert.equal(calls, 1);
  assert.equal(s.get(), 'production');
});

test('chọn lại mode đang dùng thì không gọi server', async () => {
  let calls = 0;
  const s = createModeState('dev', async () => { calls += 1; });
  assert.equal(await s.set('dev'), true);
  assert.equal(calls, 0);
});

test('lưu mode thất bại thì ghi nhận lỗi cho tới lần đổi sau', async () => {
  let fail = true;
  const s = createModeState('production', async () => { if (fail) throw new Error('mất kết nối'); });
  assert.equal(s.failed(), false);
  await s.set('dev');
  assert.equal(s.failed(), true);
  fail = false;
  await s.set('dev');
  assert.equal(s.failed(), false);
  assert.equal(s.get(), 'dev');
});

// Vừa đủ DOM cho createModeToggle.
function fakeElement() {
  return {
    dataset: {},
    children: [],
    attrs: {},
    listeners: {},
    append(child) { this.children.push(child); },
    setAttribute(name, value) { this.attrs[name] = value; },
    addEventListener(type, fn) { this.listeners[type] = fn; },
  };
}

test('toggle báo thay đổi cả lúc bắt đầu lưu lẫn lúc lưu xong', async (t) => {
  globalThis.document = { createElement: fakeElement };
  t.after(() => { delete globalThis.document; });
  let release;
  const state = createModeState('production', () => new Promise((r) => { release = r; }));
  const seen = [];
  const el = fakeElement();
  createModeToggle(el, {
    modes: { dev: 'private', production: 'public' },
    state,
    onChange: () => seen.push([state.get(), state.busy()]),
  });
  const [dev, production] = el.children;
  assert.equal(dev.textContent, 'Dev · private');
  assert.equal(production.attrs['aria-pressed'], 'true');

  const clicked = dev.listeners.click();
  // Đang lưu: vẫn là mode cũ, nơi dùng mode phải biết để chờ.
  assert.deepEqual(seen, [['production', true]]);
  assert.equal(dev.disabled, true);
  release();
  await clicked;
  assert.deepEqual(seen, [['production', true], ['dev', false]]);
  assert.equal(el.dataset.mode, 'dev');
  assert.equal(dev.attrs['aria-pressed'], 'true');
  assert.equal(dev.disabled, false);
});

test('toggle đổi mode thất bại thì vẫn ở mode cũ và báo thay đổi để hiện lỗi', async (t) => {
  globalThis.document = { createElement: fakeElement };
  t.after(() => { delete globalThis.document; });
  const state = createModeState('production', async () => { throw new Error('mất kết nối'); });
  const seen = [];
  const el = fakeElement();
  createModeToggle(el, {
    modes: { dev: 'private', production: 'public' },
    state,
    onChange: () => seen.push([state.get(), state.busy(), state.failed()]),
  });
  await el.children[0].listeners.click();
  assert.deepEqual(seen.at(-1), ['production', false, true]);
  assert.equal(el.dataset.mode, 'production');
});
