## Context

`cmd_start` in `main.py` launches N Temporal workflows simultaneously without checking if the YouTube OAuth token is valid. The token lives in `token.json` and is loaded by `auth_service.get_client()` only when an activity actually makes an API call — deep inside `upload_video_activity`. If the token is expired, all N workflows fail with cryptic Google API errors and no guidance to re-authenticate.

## Goals / Non-Goals

**Goals:**
- Fail once, clearly, before any workflow is created
- Print an actionable error message pointing to `uv run main.py auth`

**Non-Goals:**
- Automatic token refresh or re-auth flow inside `cmd_start`
- Activity-level auth error handling or retry suppression
- Handling token expiry mid-run (after workflows are already running)

## Decisions

**Single pre-flight call in `cmd_start`, not per-activity**

Auth is global shared state — if the token is dead, it's dead for all workflows. Checking once before starting any workflow is sufficient and prevents N parallel failures.

Alternative considered: catching `google.auth.exceptions.RefreshError` in each activity and raising `ApplicationError(non_retryable=True)`. Rejected — adds complexity to activity code for an edge case already handled by the pre-flight. Mid-run expiry is rare enough that normal Temporal timeout behaviour is acceptable.

**`validate_auth()` uses `channels().list(mine=True, part="id")`**

Cheapest possible YouTube API call — returns only the channel ID. Confirms the token is valid and has the correct scope without fetching or modifying any data.

## Risks / Trade-offs

- Token expires in the window between pre-flight check and an activity making its first API call → workflow fails with a cryptic error as before. Acceptable: the window is seconds, this is an extremely unlikely race.
