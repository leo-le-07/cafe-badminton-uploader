// When a failed session save is tried again. Pure, no DOM.
//
// A 4xx is the server refusing this session (validation, locked match): the
// same session is never re-sent. A network failure (status 0) or a 5xx is
// transient: the autosave retries it on its own with a backoff, and an
// explicit save (before enqueue or archive) always makes a fresh attempt.

const RETRY_DELAYS_MS = [2000, 5000, 10000];

export function isTransientSaveError(err) {
  return !!err && typeof err.status === 'number' && (err.status === 0 || err.status >= 500);
}

// Delay before automatic retry number `attempt` (0 = first retry).
export function saveRetryDelay(attempt) {
  return RETRY_DELAYS_MS[Math.min(attempt, RETRY_DELAYS_MS.length - 1)];
}
