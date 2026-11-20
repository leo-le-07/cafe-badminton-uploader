from pathlib import Path

import pytest
from unittest.mock import MagicMock, patch
from google.auth.exceptions import RefreshError

import auth_service
from auth_service import authenticate, get_client, parse_channel_response
from schemas import ChannelInfo


class TestParseChannelResponse:
    def test_returns_channel_info(self):
        response = {
            "items": [
                {
                    "id": "UC123",
                    "snippet": {"title": "My Channel", "description": "A channel"},
                }
            ]
        }
        result = parse_channel_response(response)
        assert isinstance(result, ChannelInfo)
        assert result.channel_id == "UC123"
        assert result.title == "My Channel"
        assert result.description == "A channel"

    def test_description_defaults_to_empty_string(self):
        response = {"items": [{"id": "UC123", "snippet": {"title": "My Channel"}}]}
        result = parse_channel_response(response)
        assert result.description == ""

    def test_raises_if_items_missing(self):
        with pytest.raises(ValueError, match="missing items"):
            parse_channel_response({})

    def test_raises_if_items_empty(self):
        with pytest.raises(ValueError, match="empty"):
            parse_channel_response({"items": []})


class TestGetClient:
    def test_raises_when_token_file_missing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with pytest.raises(RuntimeError, match="OAuth token not found"):
            get_client()

    def test_returns_youtube_client_when_token_present(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "token.json").write_text("{}", encoding="utf-8")
        mock_creds = MagicMock()
        mock_youtube = MagicMock()
        with (
            patch(
                "auth_service.Credentials.from_authorized_user_file",
                return_value=mock_creds,
            ),
            patch("auth_service.build", return_value=mock_youtube),
        ):
            result = get_client()
        assert result is mock_youtube


class TestAuthenticate:
    def test_raises_when_client_secret_missing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with pytest.raises(FileNotFoundError, match="client_secret.json"):
            authenticate()

    def test_runs_flow_and_saves_token(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "client_secret.json").write_text("{}", encoding="utf-8")

        mock_creds = MagicMock()
        mock_creds.to_json.return_value = '{"token": "abc"}'
        mock_flow = MagicMock()
        mock_flow.run_local_server.return_value = mock_creds
        mock_youtube = MagicMock()
        mock_youtube.channels.return_value.list.return_value.execute.return_value = {
            "items": [{"id": "UC123", "snippet": {"title": "My Channel"}}]
        }

        with (
            patch(
                "auth_service.InstalledAppFlow.from_client_secrets_file",
                return_value=mock_flow,
            ),
            patch("auth_service.build", return_value=mock_youtube),
        ):
            authenticate()

        assert (tmp_path / "token.json").read_text() == '{"token": "abc"}'


class TestAuthStatus:
    @pytest.fixture(autouse=True)
    def fresh_cache(self, monkeypatch):
        self.now = 1000.0
        monkeypatch.setattr(auth_service, "_clock", lambda: self.now)
        auth_service.clear_auth_status_cache()
        yield
        auth_service.clear_auth_status_cache()

    @staticmethod
    def channel_client():
        youtube = MagicMock()
        youtube.channels.return_value.list.return_value.execute.return_value = {
            "items": [{"id": "UC123", "snippet": {"title": "Cafe Badminton"}}]
        }
        return youtube

    def test_reports_channel_when_token_works(self):
        youtube = self.channel_client()
        with patch("auth_service.get_client", return_value=youtube):
            assert auth_service.auth_status() == {
                "ok": True,
                "channel": "Cafe Badminton",
            }
        youtube.channels.return_value.list.assert_called_once_with(
            mine=True, part="snippet"
        )

    @pytest.mark.parametrize(
        "error", [RuntimeError("OAuth token not found."), RefreshError("expired")]
    )
    def test_reports_signed_out_instead_of_raising(self, error):
        with patch("auth_service.get_client", side_effect=error):
            assert auth_service.auth_status() == {"ok": False, "channel": None}

    def test_reports_signed_out_when_api_call_fails(self):
        youtube = MagicMock()
        youtube.channels.return_value.list.return_value.execute.side_effect = (
            RefreshError("revoked")
        )
        with patch("auth_service.get_client", return_value=youtube):
            assert auth_service.auth_status() == {"ok": False, "channel": None}

    def test_result_is_cached_for_60_seconds(self):
        with patch("auth_service.get_client", side_effect=RuntimeError("no token")):
            auth_service.auth_status()
        with patch(
            "auth_service.get_client", return_value=self.channel_client()
        ) as get_client:
            self.now += 59
            assert auth_service.auth_status()["ok"] is False
            get_client.assert_not_called()
            self.now += 2
            assert auth_service.auth_status()["ok"] is True

    def test_clearing_the_cache_checks_again(self):
        with patch("auth_service.get_client", side_effect=RuntimeError("no token")):
            auth_service.auth_status()
        auth_service.clear_auth_status_cache()
        with patch("auth_service.get_client", return_value=self.channel_client()):
            assert auth_service.auth_status()["ok"] is True


class TestAuthenticateTimeout:
    @pytest.fixture
    def flow(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "client_secret.json").write_text("{}", encoding="utf-8")
        mock_flow = MagicMock()
        with patch(
            "auth_service.InstalledAppFlow.from_client_secrets_file",
            return_value=mock_flow,
        ):
            yield mock_flow

    def test_waits_at_most_five_minutes(self, flow):
        flow.run_local_server.side_effect = RuntimeError("stop here")
        with pytest.raises(RuntimeError):
            authenticate()
        assert flow.run_local_server.call_args.kwargs["timeout_seconds"] == 300

    def test_timeout_raises_login_timeout(self, flow):
        # google_auth_oauthlib gets no redirect on timeout and then fails
        # reading the missing request URI.
        flow.run_local_server.side_effect = AttributeError(
            "'NoneType' object has no attribute 'replace'"
        )
        with pytest.raises(auth_service.LoginTimeoutError):
            authenticate()
        assert not Path("token.json").exists()


class TestLoginErrorMessage:
    def test_timeout(self):
        message = auth_service.login_error_message(auth_service.LoginTimeoutError())
        assert "Hết thời gian" in message

    def test_missing_client_secret(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with pytest.raises(FileNotFoundError) as error:
            authenticate()
        message = auth_service.login_error_message(error.value)
        assert "client_secret.json" in message and "Không tìm thấy" in message

    def test_other_error_keeps_its_text(self):
        message = auth_service.login_error_message(RuntimeError("access_denied"))
        assert (
            message.startswith("Đăng nhập YouTube thất bại")
            and "access_denied" in message
        )
