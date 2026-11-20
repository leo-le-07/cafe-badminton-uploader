import test from 'node:test';
import assert from 'node:assert/strict';

import { isStaleSessionError, isTransientSaveError, saveRetryDelay } from '../../app/static/js/save.js';

const err = (status) => Object.assign(new Error('x'), { status });

test('lỗi mạng và lỗi 5xx là tạm thời, 400/409 là bị từ chối', () => {
  assert.equal(isTransientSaveError(err(0)), true);
  assert.equal(isTransientSaveError(err(500)), true);
  assert.equal(isTransientSaveError(err(503)), true);
  assert.equal(isTransientSaveError(err(400)), false);
  assert.equal(isTransientSaveError(err(409)), false);
  assert.equal(isTransientSaveError(err(413)), false);
  assert.equal(isTransientSaveError(new Error('no status')), false);
  assert.equal(isTransientSaveError(null), false);
});

test('tự lưu lại sau 2 s, 5 s, rồi mỗi 10 s', () => {
  assert.deepEqual([0, 1, 2, 3, 4, 50].map(saveRetryDelay), [2000, 5000, 10000, 10000, 10000, 10000]);
});

test('409 stale_revision là phiên cũ: không thử lại, phải tải lại trang', () => {
  const stale = Object.assign(err(409), { code: 'stale_revision' });
  assert.equal(isStaleSessionError(stale), true);
  assert.equal(isTransientSaveError(stale), false);
  assert.equal(isStaleSessionError(err(409)), false);
  assert.equal(isStaleSessionError(Object.assign(err(400), { code: 'stale_revision' })), false);
  assert.equal(isStaleSessionError(null), false);
});
