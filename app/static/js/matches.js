// Match cards of the right-hand column: type buttons, two chip inputs for the
// players with suggestions, tournament, title preview and warnings.
//
// Cards are patched in place, never rebuilt while the user types: an input
// that has focus keeps its value, caret and IME state across re-renders.
// Every edit goes through model.js via dispatch, so it is undoable and saved.

import {
  keptDuration,
  matchProblems,
  previewTitle,
  recordedDate,
  removeMatch,
  selectMatch,
  updateMatch,
} from './model.js';
import { addNames, nameCounts, splitNames, suggestNames } from './names.js';
import { matchColor } from './timeline.js';

const TYPES = ['ms', 'md', 'ws', 'wd', 'xd'];
const SIDES = ['team1', 'team2'];

const pad = (n) => String(n).padStart(2, '0');

function formatLength(sec) {
  const s = Math.round(sec);
  const h = Math.floor(s / 3600);
  const mmss = `${pad(Math.floor(s / 60) % 60)}:${pad(s % 60)}`;
  return h > 0 ? `${h}:${mmss}` : mmss;
}

function today() {
  const d = new Date();
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

// "Chưa có tên người chơi, chưa upload được", as in the mockup.
function warningText(problems) {
  if (problems.length === 0) return '';
  const both = problems.filter((p) => p.startsWith('Thiếu tên')).length === 2;
  const parts = both
    ? ['Chưa có tên người chơi', ...problems.filter((p) => !p.startsWith('Thiếu tên'))]
    : problems;
  const text = parts.map((p, i) => (i === 0 ? p : p[0].toLocaleLowerCase('vi') + p.slice(1))).join(', ');
  return `${text}, chưa upload được`;
}

function setText(el, text) {
  if (el.textContent !== text) el.textContent = text;
}

const sameNames = (a, b) => a && a.length === b.length && a.every((x, i) => x === b[i]);

const typeButtons = TYPES.map((t) => `<button type="button" data-type="${t}">${t.toUpperCase()}</button>`).join('');

const EDITABLE = `
  <div class="hd"><b></b><span class="info"></span><button type="button" class="del" title="Xoá trận">✕</button></div>
  <div class="types">${typeButtons}</div>
  <div class="teams">
    <label class="chips" data-side="team1"><span class="list"></span><input type="text" spellcheck="false" autocomplete="off" aria-label="Đội 1"></label><em>vs</em>
    <label class="chips" data-side="team2"><span class="list"></span><input type="text" spellcheck="false" autocomplete="off" aria-label="Đội 2"></label>
  </div>
  <div class="sugg" hidden></div>
  <div class="row2">Giải: <input class="inp" type="text" spellcheck="false" autocomplete="off" aria-label="Giải"></div>
  <div class="warn" hidden></div>
  <div class="title-prev">Tiêu đề: <span></span></div>`;

const LOCKED = `
  <div class="hd"><b></b><span class="lock" title="Trận đang trong hàng đợi, không sửa được">🔒</span><span class="info"></span></div>
  <div class="types">${typeButtons}</div>
  <div class="teams">
    <div class="chips ro"><span class="list"></span></div><em>vs</em>
    <div class="chips ro"><span class="list"></span></div>
  </div>
  <div class="row2">Giải: <span class="inp ro"></span></div>
  <div class="title-prev">Tiêu đề: <span></span></div>`;

// `deps`: {dispatch, getState, getLocked, getOpenMatchId}.
export function createMatches(container, deps) {
  container.innerHTML = '<h4></h4><div class="cards"></div><p class="hint empty">Chưa có trận nào. Tick một video ở cột trái, rồi bấm <kbd>I</kbd> để bắt đầu giữ trận đầu tiên.</p>';
  const heading = container.querySelector('h4');
  const list = container.querySelector('.cards');
  const empty = container.querySelector('.empty');
  const cards = new Map(); // match id -> card
  let ctx = { players: [], locked: new Set(), recordedDates: {} };
  let state = null;
  let lastSelected = null;
  // Suggestions of the focused chip input: {card, side, items, index}.
  let sugg = null;

  const matchOf = (id) => state.session.matches.find((m) => m.id === id);

  // ------------------------------------------------------------ building

  function build(match, locked) {
    const el = document.createElement('div');
    el.className = 'match';
    el.dataset.id = match.id;
    el.innerHTML = locked ? LOCKED : EDITABLE;
    const q = (sel) => el.querySelector(sel);
    const card = {
      id: match.id,
      el,
      locked,
      title: q('.hd b'),
      info: q('.hd .info'),
      types: [...el.querySelectorAll('.types button')],
      lists: [...el.querySelectorAll('.chips .list')],
      inputs: locked ? [] : [...el.querySelectorAll('.chips input')],
      tournament: q('.row2 .inp'),
      sugg: q('.sugg'),
      warn: q('.warn'),
      preview: q('.title-prev span'),
      shown: {},
    };
    if (locked) for (const b of card.types) b.disabled = true;
    return card;
  }

  function patch(card, match, index) {
    const sel = match.id === state.session.selected_match_id;
    card.el.style.setProperty('--c', matchColor(index));
    card.el.classList.toggle('sel', sel);
    setText(card.title, `Trận ${index + 1}`);
    const marking = state.open && state.open.matchId === match.id;
    setText(card.info, `${match.segments.length} đoạn · ${marking ? 'đang đánh dấu' : formatLength(keptDuration(match))}`);
    for (const b of card.types) b.classList.toggle('on', b.dataset.type === match.match_type);
    SIDES.forEach((side, i) => {
      if (sameNames(card.shown[side], match[side])) return;
      card.shown[side] = match[side];
      card.lists[i].replaceChildren(...match[side].map((name) => {
        const u = document.createElement('u');
        u.textContent = name;
        return u;
      }));
    });
    if (card.locked) setText(card.tournament, match.tournament);
    else if (document.activeElement !== card.tournament && card.tournament.value !== match.tournament) {
      card.tournament.value = match.tournament;
    }
    if (card.warn) {
      const text = warningText(matchProblems(match, deps.getOpenMatchId()));
      setText(card.warn, text);
      card.warn.hidden = !text;
    }
    const date = recordedDate(match, state.session, ctx.recordedDates, today());
    setText(card.preview, previewTitle(match, date));
  }

  // ------------------------------------------------------------ render

  function render(nextState, nextCtx) {
    state = nextState;
    ctx = { ...ctx, ...nextCtx };
    const matches = state.session.matches;
    setText(heading, `Các trận (${matches.length})`);
    empty.hidden = matches.length > 0;
    const seen = new Set();
    matches.forEach((match, index) => {
      seen.add(match.id);
      const locked = ctx.locked.has(match.id);
      let card = cards.get(match.id);
      if (card && card.locked !== locked) {
        const fresh = build(match, locked);
        card.el.replaceWith(fresh.el);
        if (sugg && sugg.card === card) sugg = null;
        card = fresh;
        cards.set(match.id, card);
      }
      if (!card) {
        card = build(match, locked);
        cards.set(match.id, card);
      }
      patch(card, match, index);
      // Only move a card when it is out of place: moving a node drops focus.
      if (list.children[index] !== card.el) list.insertBefore(card.el, list.children[index] ?? null);
    });
    for (const [id, card] of cards) {
      if (!seen.has(id)) {
        card.el.remove();
        cards.delete(id);
        if (sugg && sugg.card === card) sugg = null;
      }
    }
    const selected = state.session.selected_match_id;
    if (selected !== lastSelected) {
      lastSelected = selected;
      const card = cards.get(selected);
      if (card && !card.el.contains(document.activeElement)) card.el.scrollIntoView({ block: 'nearest' });
    }
    if (sugg) showSuggestions(sugg.card, sugg.side, sugg.index);
  }

  // ------------------------------------------------------------ editing

  const locked = () => deps.getLocked();
  const cardOf = (el) => cards.get(el.closest('.match')?.dataset.id);
  const sideOf = (input) => input.closest('.chips').dataset.side;

  function update(id, fields) {
    deps.dispatch((s) => updateMatch(s, id, fields, locked()));
  }

  function addToTeam(card, side, names) {
    deps.dispatch((s) => {
      const m = s.session.matches.find((x) => x.id === card.id);
      if (!m) return s;
      const team = addNames(m, side, names);
      return team === m[side] ? s : updateMatch(s, card.id, { [side]: team }, locked());
    });
  }

  // Turns the text typed so far into chips and empties the input.
  function commitPending(card, input) {
    const names = splitNames(input.value);
    input.value = '';
    if (names.length) addToTeam(card, sideOf(input), names);
  }

  function select(id) {
    deps.dispatch((s) => selectMatch(s, id));
  }

  function remove(card) {
    const m = matchOf(card.id);
    if (!m || locked().has(card.id)) return;
    if (m.segments.length > 0 && !window.confirm('Xoá trận này và các đoạn đã đánh dấu?')) return;
    deps.dispatch((s) => removeMatch(s, card.id, locked()));
  }

  // ------------------------------------------------------------ suggestions

  function showSuggestions(card, side, index = -1) {
    const m = matchOf(card.id);
    const input = card.inputs[SIDES.indexOf(side)];
    if (!m || !input || document.activeElement !== input) return hideSuggestions();
    const counts = nameCounts(ctx.players, state.session.matches);
    const items = suggestNames(input.value, counts, [...m.team1, ...m.team2]);
    if (sugg && sugg.card !== card) sugg.card.sugg.hidden = true;
    sugg = { card, side, items, index: Math.min(index, items.length - 1) };
    const box = card.sugg;
    if (items.length === 0) {
      box.hidden = true;
      return;
    }
    const label = document.createElement('span');
    label.textContent = 'Gợi ý: ';
    box.replaceChildren(label, ...items.map((name, i) => {
      const u = document.createElement('u');
      u.textContent = name;
      u.dataset.name = name;
      if (i === sugg.index) u.className = 'on';
      return u;
    }));
    box.hidden = false;
  }

  function hideSuggestions() {
    if (sugg) sugg.card.sugg.hidden = true;
    sugg = null;
  }

  // ------------------------------------------------------------ events

  container.addEventListener('click', (e) => {
    const card = cardOf(e.target);
    if (!card) return;
    const button = e.target.closest('button');
    if (button) button.blur();
    if (button && button.classList.contains('del')) {
      remove(card);
      return;
    }
    if (button && button.dataset.type && !card.locked) {
      select(card.id);
      update(card.id, { match_type: button.dataset.type });
      return;
    }
    const u = e.target.closest('.sugg u');
    if (u && sugg && sugg.card === card) {
      const input = card.inputs[SIDES.indexOf(sugg.side)];
      input.value = '';
      addToTeam(card, sugg.side, [u.dataset.name]);
      showSuggestions(card, sugg.side);
      return;
    }
    select(card.id);
  });

  // Clicking a suggestion must not take focus away from the input.
  container.addEventListener('mousedown', (e) => {
    if (e.target.closest('.sugg u')) e.preventDefault();
  });

  container.addEventListener('focusin', (e) => {
    const card = cardOf(e.target);
    if (!card || e.target.tagName !== 'INPUT') return;
    select(card.id);
    if (card.inputs.includes(e.target)) showSuggestions(card, sideOf(e.target));
  });

  // IME composition: nothing is split or committed while a syllable is being
  // composed. A blur during composition commits once the composition ends.
  const composing = new Set(); // chip inputs with a composition in progress
  const commitAfterComposition = new Set();

  container.addEventListener('compositionstart', (e) => {
    if (cardOf(e.target)?.inputs.includes(e.target)) composing.add(e.target);
  });

  container.addEventListener('compositionend', (e) => {
    const input = e.target;
    if (!composing.delete(input)) return;
    const card = cardOf(input);
    if (!card) return;
    if (commitAfterComposition.delete(input) || document.activeElement !== input) {
      commitPending(card, input);
      return;
    }
    splitTyped(card, input);
    showSuggestions(card, sideOf(input));
  });

  // Esc throws away the half-typed name; clicking away or Tab keeps it.
  let discarding = null;

  container.addEventListener('focusout', (e) => {
    const card = cardOf(e.target);
    if (!card || !card.inputs.includes(e.target)) return;
    if (discarding === e.target) {
      discarding = null;
      e.target.value = '';
    } else if (composing.has(e.target)) {
      commitAfterComposition.add(e.target);
    } else {
      commitPending(card, e.target);
    }
    if (sugg && sugg.card === card) hideSuggestions();
  });

  // "Tú," makes a chip and keeps typing in the same input.
  function splitTyped(card, input) {
    if (!input.value.includes(',')) return;
    const parts = input.value.split(',');
    const rest = parts.pop().trimStart();
    input.value = rest;
    const names = splitNames(parts.join(','));
    if (names.length) addToTeam(card, sideOf(input), names);
  }

  container.addEventListener('input', (e) => {
    const card = cardOf(e.target);
    if (!card) return;
    if (e.target === card.tournament) {
      update(card.id, { tournament: e.target.value });
      return;
    }
    if (!card.inputs.includes(e.target)) return;
    const input = e.target;
    if (!e.isComposing && !composing.has(input)) splitTyped(card, input);
    showSuggestions(card, sideOf(input));
  });

  container.addEventListener('paste', (e) => {
    const card = cardOf(e.target);
    if (!card || !card.inputs.includes(e.target)) return;
    const text = e.clipboardData ? e.clipboardData.getData('text') : '';
    if (!/[,\n]/.test(text)) return; // a single name is pasted as text
    e.preventDefault();
    const input = e.target;
    const value = input.value.slice(0, input.selectionStart) + text + input.value.slice(input.selectionEnd);
    input.value = '';
    addToTeam(card, sideOf(input), splitNames(value.replace(/\r?\n/g, ',')));
    showSuggestions(card, sideOf(input));
  });

  container.addEventListener('keydown', (e) => {
    const card = cardOf(e.target);
    if (!card || !card.inputs.includes(e.target)) return;
    if (e.isComposing || e.keyCode === 229 || composing.has(e.target)) return; // the IME owns this key
    const input = e.target;
    if (e.key === 'Escape') {
      // main.js blurs; the pending text is dropped instead of committed.
      discarding = input;
      return;
    }
    const side = sideOf(input);
    const own = sugg && sugg.card === card && sugg.side === side ? sugg : null;
    if ((e.key === 'ArrowDown' || e.key === 'ArrowUp') && own && own.items.length) {
      e.preventDefault();
      const n = own.items.length;
      const index = e.key === 'ArrowDown' ? (own.index + 1) % n : (own.index <= 0 ? n - 1 : own.index - 1);
      showSuggestions(card, side, index);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (own && own.index >= 0) {
        input.value = '';
        addToTeam(card, side, [own.items[own.index]]);
      } else {
        commitPending(card, input);
      }
      showSuggestions(card, side);
    } else if (e.key === 'Backspace' && input.value === '') {
      e.preventDefault();
      const m = matchOf(card.id);
      if (m && m[side].length) update(card.id, { [side]: m[side].slice(0, -1) });
      showSuggestions(card, side, own ? own.index : -1);
    } else if (e.key === 'Tab' && !e.altKey && !e.metaKey && !e.ctrlKey) {
      // team 1 -> team 2 -> tournament, and back with Shift.
      const next = e.shiftKey
        ? (side === 'team2' ? card.inputs[0] : null)
        : (side === 'team1' ? card.inputs[1] : card.tournament);
      if (!next) return;
      e.preventDefault();
      next.focus();
    }
  });

  return {
    render,
    // Enter in the editor: put the caret in team 1 of match `id`.
    focusTeam1(id) {
      const card = cards.get(id);
      if (!card || card.locked) return;
      card.el.scrollIntoView({ block: 'nearest' });
      card.inputs[0].focus();
    },
  };
}
