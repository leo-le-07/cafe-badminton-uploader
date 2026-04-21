## ADDED Requirements

### Requirement: Pre-flight YouTube auth validation
`auth_service` SHALL expose a `validate_auth()` function that verifies the current OAuth token is valid by making a minimal YouTube API call before any workflows are started.

#### Scenario: Valid token
- **WHEN** `validate_auth()` is called and `token.json` exists with a valid, non-expired token
- **THEN** the function returns without error

#### Scenario: Expired or revoked token
- **WHEN** `validate_auth()` is called and the token is expired or revoked
- **THEN** the function raises an exception with a message indicating the token is invalid

#### Scenario: Missing token file
- **WHEN** `validate_auth()` is called and `token.json` does not exist
- **THEN** the function raises an exception (inherits from existing `get_client()` behaviour)

### Requirement: cmd_start fails fast on invalid auth
`cmd_start` SHALL call `validate_auth()` before scanning for videos or starting any workflows.

#### Scenario: Invalid auth on start
- **WHEN** the user runs `uv run main.py start` and the YouTube token is invalid
- **THEN** the command exits immediately with a log error message that includes instructions to run `uv run main.py auth`
- **THEN** no Temporal workflows are created

#### Scenario: Valid auth on start
- **WHEN** the user runs `uv run main.py start` and the YouTube token is valid
- **THEN** the command proceeds normally to scan videos and start workflows
