// The Dev / Production switch in the top bar. The mode only decides the
// YouTube privacy of the matches queued while it is selected (app/server.py,
// PUT /api/mode); the server remembers the last choice.

// Holds the current mode. `save(mode)` stores it on the server; the mode
// changes here only once that succeeded, so the page never shows a mode the
// server does not have.
export function createModeState(initial, save) {
  let mode = initial;
  let saving = false;
  return {
    get: () => mode,
    busy: () => saving,
    // Resolves true once `next` is the current mode, false if it is not.
    async set(next) {
      if (saving) return false;
      if (next === mode) return true;
      saving = true;
      try {
        await save(next);
        mode = next;
        return true;
      } catch {
        return false;
      } finally {
        saving = false;
      }
    },
  };
}

const LABELS = { dev: 'Dev', production: 'Production' };

// Draws one button per mode into `el`. `onChange()` runs after each change.
export function createModeToggle(el, { modes, state, onChange }) {
  const buttons = new Map();
  for (const [mode, privacy] of Object.entries(modes)) {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = `${LABELS[mode] ?? mode} · ${privacy}`;
    button.addEventListener('click', () => choose(mode));
    buttons.set(mode, button);
    el.append(button);
  }

  function render() {
    el.dataset.mode = state.get();
    for (const [mode, button] of buttons) {
      button.setAttribute('aria-pressed', String(mode === state.get()));
      button.disabled = state.busy();
    }
  }

  async function choose(mode) {
    const before = state.get();
    const pending = state.set(mode);
    render();
    const ok = await pending;
    el.title = ok ? '' : 'Chưa đổi được chế độ, hãy thử lại';
    render();
    if (state.get() !== before) onChange();
  }

  render();
}
