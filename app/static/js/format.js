// Small text helpers shared by the editor modules. Pure, no DOM.

// Escapes text for use inside HTML, attribute values included.
export const esc = (s) => String(s).replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

export const pad = (n) => String(n).padStart(2, '0');

// Seconds as M:SS, or H:MM:SS from one hour.
export function formatLength(sec) {
  const s = Math.round(sec);
  const h = Math.floor(s / 3600);
  const mmss = `${pad(Math.floor(s / 60) % 60)}:${pad(s % 60)}`;
  return h > 0 ? `${h}:${mmss}` : mmss;
}
