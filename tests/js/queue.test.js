import test from 'node:test';
import assert from 'node:assert/strict';

import { connectionLost, rowActions } from '../../app/static/js/queue.js';

test('mất kết nối chỉ báo sau 2 lần hỏi hàng đợi thất bại liên tiếp', () => {
  assert.equal(connectionLost(0), false);
  assert.equal(connectionLost(1), false);
  assert.equal(connectionLost(2), true);
  assert.equal(connectionLost(5), true);
});

test('nút của từng dòng theo trạng thái', () => {
  assert.deepEqual(rowActions({ status: 'queued' }), ['unqueue']);
  assert.deepEqual(rowActions({ status: 'running' }), []);
  assert.deepEqual(rowActions({ status: 'error' }), ['retry', 'unqueue']);
  assert.deepEqual(rowActions({ status: 'waiting_quota' }), ['retry', 'unqueue']);
  assert.deepEqual(rowActions({ status: 'done' }), []);
  // Đã có video trên YouTube: không đưa về chỉnh sửa được.
  assert.deepEqual(rowActions({ status: 'error', youtube_link: 'https://youtu.be/x' }), ['retry']);
});
