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

// The server refused the save because another tab saved since this one
// loaded (409 with code "stale_revision"): nothing may be saved from this
// tab any more; the page must be reloaded.
export function isStaleSessionError(err) {
  return !!err && err.status === 409 && err.code === 'stale_revision';
}

// Delay before automatic retry number `attempt` (0 = first retry).
export function saveRetryDelay(attempt) {
  return RETRY_DELAYS_MS[Math.min(attempt, RETRY_DELAYS_MS.length - 1)];
}
