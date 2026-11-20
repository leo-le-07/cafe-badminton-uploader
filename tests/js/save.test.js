import test from 'node:test';
import assert from 'node:assert/strict';

import { isTransientSaveError, saveRetryDelay } from '../../app/static/js/save.js';

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
