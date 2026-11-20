import test from 'node:test';
import assert from 'node:assert/strict';

import { createModeState } from '../../app/static/js/mode.js';

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
