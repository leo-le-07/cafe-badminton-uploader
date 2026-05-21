import asyncio
import pytest
from unittest.mock import patch

import config
from main import cmd_start


@patch("main.validate_auth", side_effect=Exception("Token expired"))
@patch("main.start_video_workflow")
def test_cmd_start_exits_on_auth_failure(mock_start_workflow, mock_validate_auth):
    with pytest.raises(SystemExit) as exc:
        asyncio.run(cmd_start(None))

    assert exc.value.code == 1
    mock_start_workflow.assert_not_called()


class TestCmdRethumbnail:
    def test_calls_rethumbnail_video_for_each_workspace(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "COMPLETED_DIR", tmp_path)
        workspaces = [tmp_path / "ws1", tmp_path / "ws2"]

        with (
            patch(
                "main.scan_completed_workspaces", return_value=workspaces
            ) as mock_scan,
            patch("main.rethumbnail_video") as mock_fn,
        ):
            from main import cmd_rethumbnail

            cmd_rethumbnail(object())

        mock_scan.assert_called_once_with(config.COMPLETED_DIR)
        assert mock_fn.call_count == 2

    def test_does_nothing_when_no_workspaces_found(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "COMPLETED_DIR", tmp_path)

        with (
            patch("main.scan_completed_workspaces", return_value=[]),
            patch("main.rethumbnail_video") as mock_fn,
        ):
            from main import cmd_rethumbnail

            cmd_rethumbnail(object())

        mock_fn.assert_not_called()

    def test_continues_on_error_for_one_workspace(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "COMPLETED_DIR", tmp_path)
        ws1 = tmp_path / "ws1"
        ws2 = tmp_path / "ws2"

        def side_effect(ws):
            if ws == ws1:
                raise FileNotFoundError("no image")

        with (
            patch("main.scan_completed_workspaces", return_value=[ws1, ws2]),
            patch("main.rethumbnail_video", side_effect=side_effect) as mock_fn,
        ):
            from main import cmd_rethumbnail

            cmd_rethumbnail(object())

        assert mock_fn.call_count == 2
