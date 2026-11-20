// Player names: pure helpers for the name chips and their suggestions.
// No DOM; inputs are never mutated.

const SUGGESTION_LIMIT = 5;

const lower = (s) => s.toLocaleLowerCase('vi');

// Lower case without Vietnamese diacritics, for prefix matching: NFD splits a
// letter from its marks, which are then dropped; đ has no decomposition.
export function foldName(s) {
  return lower(s).normalize('NFD').replace(/\p{M}/gu, '').replace(/đ/g, 'd');
}

// Usage weight of every known name, as Map name -> number. `history` is the
// server's list sorted by usage (most used first), or an object name -> count.
// Names typed in this session's matches add one per use, so a name typed for
// one match is suggested for the next straight away. Names that differ only in
// case count as one, under the first spelling seen.
export function nameCounts(history, matches) {
  const counts = new Map();
  const spelling = new Map(); // lower case -> spelling kept
  const add = (name, n) => {
    const key = lower(name);
    const kept = spelling.get(key) ?? name;
    spelling.set(key, kept);
    counts.set(kept, (counts.get(kept) ?? 0) + n);
  };
  if (Array.isArray(history)) history.forEach((name, i) => add(name, history.length - i));
  else for (const [name, n] of Object.entries(history ?? {})) add(name, n);
  for (const m of matches) {
    for (const name of [...m.team1, ...m.team2]) if (name.trim()) add(name.trim(), 1);
  }
  return counts;
}

// Names starting with `query` (case- and diacritic-insensitive), without the
// names in `exclude` (case-insensitive), most used first, then alphabetical.
export function suggestNames(query, counts, exclude = [], limit = SUGGESTION_LIMIT) {
  const q = foldName(query.trim());
  const taken = new Set(exclude.map(lower));
  return [...counts]
    .filter(([name]) => !taken.has(lower(name)) && foldName(name).startsWith(q))
    .sort(([a, x], [b, y]) => y - x || a.localeCompare(b, 'vi'))
    .slice(0, limit)
    .map(([name]) => name);
}

// "A, B" -> ['A', 'B'].
export function splitNames(text) {
  return text.split(',').map((s) => s.trim()).filter(Boolean);
}

// Team `side` ('team1' | 'team2') of `match` with `names` appended, skipping
// empty names and names already in either team (case-insensitive). Returns
// the same array when nothing is added.
export function addNames(match, side, names) {
  const taken = new Set([...match.team1, ...match.team2].map(lower));
  const added = [];
  for (const raw of names) {
    const name = raw.trim();
    if (!name || taken.has(lower(name))) continue;
    taken.add(lower(name));
    added.push(name);
  }
  return added.length ? [...match[side], ...added] : match[side];
}
