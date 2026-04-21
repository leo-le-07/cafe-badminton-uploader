import pytest
from unittest.mock import patch, MagicMock
from google.auth.exceptions import RefreshError

from auth_service import validate_auth


@patch("auth_service.get_client")
def test_validate_auth_success(mock_get_client):
    mock_youtube = MagicMock()
    mock_youtube.channels().list().execute.return_value = {"items": [{"id": "UC123"}]}
    mock_get_client.return_value = mock_youtube

    validate_auth()  # should not raise


@patch("auth_service.get_client")
def test_validate_auth_raises_on_expired_token(mock_get_client):
    mock_youtube = MagicMock()
    mock_youtube.channels().list().execute.side_effect = RefreshError("Token expired")
    mock_get_client.return_value = mock_youtube

    with pytest.raises(RefreshError):
        validate_auth()


@patch("auth_service.get_client")
def test_validate_auth_raises_when_token_file_missing(mock_get_client):
    mock_get_client.side_effect = RuntimeError("OAuth token not found.")

    with pytest.raises(RuntimeError, match="OAuth token not found"):
        validate_auth()
