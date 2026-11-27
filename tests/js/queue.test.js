import test from 'node:test';
import assert from 'node:assert/strict';

import { cleanLabel, connectionLost, doneCount, goBlocked, goLabel, jobPrivacy, rowActions } from '../../app/static/js/queue.js';

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

test('nút upload ghi rõ privacy', () => {
  assert.equal(goLabel(3, 'public'), 'Xử lý & upload 3 trận · public');
  assert.equal(goLabel(0, 'private'), 'Xử lý & upload 0 trận · private');
});

test('nhãn privacy của một trận theo mode của nó, thiếu thì private', () => {
  const modes = { dev: 'private', production: 'public' };
  assert.equal(jobPrivacy({ mode: 'production' }, modes), 'public');
  assert.equal(jobPrivacy({ mode: 'dev' }, modes), 'private');
  assert.equal(jobPrivacy({}, modes), 'private');
  assert.equal(jobPrivacy({ mode: 'prod' }, modes), 'private');
  assert.equal(jobPrivacy({ mode: 'toString' }, modes), 'private');
});

test('không upload được khi mode đang được lưu hoặc vừa đổi thất bại', () => {
  const ok = { busy: false, n: 2, signedIn: true, stale: false, modeBusy: false, modeFailed: false };
  assert.equal(goBlocked(ok), false);
  assert.equal(goBlocked({ ...ok, modeBusy: true }), true);
  assert.equal(goBlocked({ ...ok, modeFailed: true }), true);
  assert.equal(goBlocked({ ...ok, n: 0 }), true);
  assert.equal(goBlocked({ ...ok, signedIn: false }), true);
  assert.equal(goBlocked({ ...ok, stale: true }), true);
  assert.equal(goBlocked({ ...ok, busy: true }), true);
});

test('nút dọn đếm các trận đã xong trong hàng đợi', () => {
  const jobs = [{ status: 'done' }, { status: 'queued' }, { status: 'done' }, { status: 'error' }];
  assert.equal(doneCount(jobs), 2);
  assert.equal(doneCount([]), 0);
  assert.equal(cleanLabel(2), 'Dọn 2 trận đã xong');
});
