import test from 'node:test';
import assert from 'node:assert/strict';

import {
  addNames,
  foldName,
  nameCounts,
  splitNames,
  suggestNames,
} from '../../app/static/js/names.js';

const counts = (obj) => new Map(Object.entries(obj));

test('foldName bỏ dấu tiếng Việt, đổi đ thành d và không phân biệt hoa thường', () => {
  assert.equal(foldName('Tú'), 'tu');
  assert.equal(foldName('Đức'), 'duc');
  assert.equal(foldName('đẶNG Hùng'), 'dang hung');
  assert.equal(foldName('Nguyễn'), 'nguyen');
});

test('gợi ý theo tiền tố không phân biệt dấu: "tu" ra "Tú", "d" ra "Đức"', () => {
  const c = counts({ 'Tú': 3, 'Tuấn': 1, 'Đức': 2, 'Nam': 5 });
  assert.deepEqual(suggestNames('tu', c), ['Tú', 'Tuấn']);
  assert.deepEqual(suggestNames('d', c), ['Đức']);
  assert.deepEqual(suggestNames('Đ', c), ['Đức']);
  assert.deepEqual(suggestNames('TÚ', c), ['Tú', 'Tuấn']);
  assert.deepEqual(suggestNames('x', c), []);
});

test('gợi ý bỏ tên đã có ở một trong hai đội, so sánh không phân biệt hoa thường', () => {
  const c = counts({ 'Tú': 3, 'Tuấn': 1, 'Nam': 2 });
  assert.deepEqual(suggestNames('t', c, ['tú']), ['Tuấn']);
  assert.deepEqual(suggestNames('', c, ['Nam', 'Tuấn']), ['Tú']);
});

test('gợi ý xếp theo số lần dùng rồi theo chữ cái, tối đa 5', () => {
  const c = counts({ 'Bình': 1, 'An': 1, 'Châu': 4, 'Dũng': 2, 'Em': 1, 'Giang': 1, 'Hà': 9 });
  assert.deepEqual(suggestNames('', c), ['Hà', 'Châu', 'Dũng', 'An', 'Bình']);
  assert.equal(suggestNames('', c, [], 3).length, 3);
});

test('nameCounts gộp lịch sử với tên đã gõ trong phiên', () => {
  // The server sends the history as a list sorted by usage.
  const c = nameCounts(['Nam', 'Tú', 'Hùng'], [
    { team1: ['Linh', 'nam'], team2: ['Tú'] },
    { team1: ['Linh'], team2: [] },
  ]);
  assert.deepEqual([...c.keys()], ['Nam', 'Tú', 'Hùng', 'Linh']);
  assert.ok(c.get('Nam') > c.get('Tú'));
  assert.ok(c.get('Tú') > c.get('Hùng'));
  assert.equal(c.get('Linh'), 2);
  // A name typed only in this session is suggested right away.
  assert.deepEqual(suggestNames('li', c), ['Linh']);
  // An object of counts is accepted too.
  const o = nameCounts({ 'Tú': 4, 'Nam': 1 }, [{ team1: ['Nam'], team2: ['  '] }]);
  assert.deepEqual(Object.fromEntries(o), { 'Tú': 4, 'Nam': 2 });
});

test('splitNames tách theo dấu phẩy, cắt khoảng trắng, bỏ phần rỗng', () => {
  assert.deepEqual(splitNames('A, B'), ['A', 'B']);
  assert.deepEqual(splitNames(' Tú ,, ,Hùng,'), ['Tú', 'Hùng']);
  assert.deepEqual(splitNames('   '), []);
});

test('addNames bỏ tên rỗng và tên trùng trong cùng trận, không phân biệt hoa thường', () => {
  const m = { team1: ['Nam'], team2: ['Tú'] };
  assert.deepEqual(addNames(m, 'team1', ['Hùng']), ['Nam', 'Hùng']);
  assert.deepEqual(addNames(m, 'team1', ['nam', 'TÚ', ' ', 'Long', 'long']), ['Nam', 'Long']);
  assert.equal(addNames(m, 'team2', ['tú']), m.team2);
  assert.deepEqual(addNames(m, 'team2', ['  Linh  ']), ['Tú', 'Linh']);
});
