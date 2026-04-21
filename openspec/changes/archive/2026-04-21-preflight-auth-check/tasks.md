## 1. Auth Service

- [x] 1.1 Add `validate_auth()` to `auth_service.py` — calls `channels().list(mine=True, part="id").execute()` using the existing `get_client()`

## 2. Start Command

- [x] 2.1 Call `validate_auth()` at the top of `cmd_start` in `main.py`, catch exceptions, log a clear error with `uv run main.py auth` guidance, and `sys.exit(1)`

## 3. Tests

- [x] 3.1 Create `tests/test_auth_service.py` — test `validate_auth()`: valid token succeeds, expired/revoked token raises
- [x] 3.2 Create `tests/test_main.py` — test `cmd_start` pre-flight: auth failure exits before any workflow is started
