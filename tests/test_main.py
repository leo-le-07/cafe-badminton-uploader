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
    def test_calls_rethumbnail_video_with_resolved_workspace(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(config, "COMPLETED_DIR", tmp_path)
        workspace_dir = tmp_path / "xd_match"
        workspace_dir.mkdir()

        with patch("main.rethumbnail_video") as mock_fn:
            from main import cmd_rethumbnail

            args = type("args", (), {"workspace": "xd_match"})()
            cmd_rethumbnail(args)

        mock_fn.assert_called_once_with(workspace_dir)

    def test_accepts_absolute_path(self, tmp_path):
        workspace_dir = tmp_path / "xd_match"
        workspace_dir.mkdir()

        with patch("main.rethumbnail_video") as mock_fn:
            from main import cmd_rethumbnail

            args = type("args", (), {"workspace": str(workspace_dir)})()
            cmd_rethumbnail(args)

        mock_fn.assert_called_once_with(workspace_dir)

    def test_exits_when_workspace_not_found(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "COMPLETED_DIR", tmp_path)

        from main import cmd_rethumbnail

        args = type("args", (), {"workspace": "nonexistent"})()
        with pytest.raises(SystemExit) as exc:
            cmd_rethumbnail(args)
        assert exc.value.code != 0

    def test_exits_on_file_not_found_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "COMPLETED_DIR", tmp_path)
        workspace_dir = tmp_path / "xd_match"
        workspace_dir.mkdir()

        with patch("main.rethumbnail_video", side_effect=FileNotFoundError("no image")):
            from main import cmd_rethumbnail

            args = type("args", (), {"workspace": "xd_match"})()
            with pytest.raises(SystemExit) as exc:
                cmd_rethumbnail(args)
            assert exc.value.code != 0

    def test_exits_on_runtime_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "COMPLETED_DIR", tmp_path)
        workspace_dir = tmp_path / "xd_match"
        workspace_dir.mkdir()

        with patch(
            "main.rethumbnail_video", side_effect=RuntimeError("no upload record")
        ):
            from main import cmd_rethumbnail

            args = type("args", (), {"workspace": "xd_match"})()
            with pytest.raises(SystemExit) as exc:
                cmd_rethumbnail(args)
            assert exc.value.code != 0
