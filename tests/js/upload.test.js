import test from 'node:test';
import assert from 'node:assert/strict';

import { formatSize, planUploads } from '../../app/static/js/upload.js';

const file = (name) => ({ name });

test('chỉ chép video .mov/.mp4 chưa có trong input', () => {
  const { accepted, skipped } = planUploads(
    [file('IMG_1.MOV'), file('b.mp4'), file('notes.txt'), file('.hidden.mov'), file('a.mov'), file('IMG_1.MOV')],
    ['a.mov'],
  );
  assert.deepEqual(accepted.map((f) => f.name), ['IMG_1.MOV', 'b.mp4']);
  assert.deepEqual(skipped, [
    { name: 'notes.txt', reason: 'chỉ nhận .mov hoặc .mp4' },
    { name: '.hidden.mov', reason: 'chỉ nhận .mov hoặc .mp4' },
    { name: 'a.mov', reason: 'đã có file cùng tên trong input/' },
    { name: 'IMG_1.MOV', reason: 'đã có file cùng tên trong input/' },
  ]);
});

test('kích thước file dễ đọc', () => {
  assert.equal(formatSize(3_456_000_000), '3.5 GB');
  assert.equal(formatSize(250_000_000), '250 MB');
  assert.equal(formatSize(10), '1 MB');
});
