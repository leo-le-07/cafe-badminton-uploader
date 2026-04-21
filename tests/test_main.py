import asyncio
import pytest
from unittest.mock import patch

from main import cmd_start


@patch("main.validate_auth", side_effect=Exception("Token expired"))
@patch("main.start_video_workflow")
def test_cmd_start_exits_on_auth_failure(mock_start_workflow, mock_validate_auth):
    with pytest.raises(SystemExit) as exc:
        asyncio.run(cmd_start(None))

    assert exc.value.code == 1
    mock_start_workflow.assert_not_called()
