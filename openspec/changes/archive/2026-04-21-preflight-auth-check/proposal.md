## Why

When `start` is run with an expired YouTube OAuth token, multiple workflows are launched simultaneously and all fail with cryptic Google API errors — giving the user no guidance to re-authenticate. A single pre-flight check before any workflow is created catches this once, clearly, and prevents N parallel failures.

## What Changes

- Add `validate_auth()` to `auth_service.py` — makes a cheap `channels().list()` call to confirm the token is valid
- Call `validate_auth()` at the top of `cmd_start` in `main.py` — exits with a clear message pointing to `uv run main.py auth` if auth fails

## Capabilities

### New Capabilities

- `youtube-auth-validation`: Pre-flight YouTube API auth check used by `cmd_start` before launching any workflows

### Modified Capabilities

<!-- none -->

## Impact

- `auth_service.py`: new `validate_auth()` function
- `main.py`: `cmd_start` calls `validate_auth()` before starting workflows
- No workflow logic, activity code, or retry behaviour changes
