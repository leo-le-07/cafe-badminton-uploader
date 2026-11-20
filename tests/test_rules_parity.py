"""The editor (app/static/js/model.js) and the server (app/models.py) must
report the same problems, word for word, and preview the title YouTube gets."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.models import Match, match_problems, match_title

MODEL_JS = Path(__file__).resolve().parent.parent / "app" / "static" / "js" / "model.js"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node not installed"
)


def _m(team1, team2, tournament="Cafe Game", segments=True):
    return {
        "id": "m1",
        "match_type": "md",
        "team1": team1,
        "team2": team2,
        "tournament": tournament,
        "segments": [{"source": "a.mov", "start": 0, "end": 1}] if segments else [],
    }


CASES = [
    (_m(["Nam"], ["Tú"]), None),
    (_m([], ["  "], segments=False), None),
    (_m(["Nam"], ["Tú"], tournament=""), None),
    (_m([" Nam ", "", "Hùng"], ["Tú", "Long"], tournament=" Giải Hè "), None),
    (_m(["Nam"], ["Tú"]), "m1"),
    (_m(["Nam"], ["Tú"]), "m2"),
    (_m(["<b>Nam"], ["Tú"], tournament="Cup > 1"), None),
    (_m(["Nguyễn Văn " + "A" * 70], ["Trần Thị Bích"]), "m1"),
    (_m(["A" * 70], ["B"]), None),
    (_m(["A" * 71], ["B"]), None),
]

SCRIPT = """
import { matchProblems, previewTitle } from %s;
let input = '';
process.stdin.on('data', (d) => { input += d; });
process.stdin.on('end', () => {
  const out = JSON.parse(input).map(([m, open]) => [matchProblems(m, open), previewTitle(m, '2026-11-20')]);
  process.stdout.write(JSON.stringify(out));
});
"""


def test_problems_and_title_are_identical_in_python_and_js():
    result = subprocess.run(
        ["node", "--input-type=module", "-e", SCRIPT % json.dumps(MODEL_JS.as_uri())],
        input=json.dumps(CASES),
        capture_output=True,
        text=True,
        check=True,
    )
    js = json.loads(result.stdout)
    python = [
        [
            match_problems(Match.from_dict(m), open),
            match_title(Match.from_dict(m), "2026-11-20"),
        ]
        for m, open in CASES
    ]
    assert js == python
    # The cases cover every rule.
    every = {p for problems, _ in python for p in problems}
    assert any(p.startswith("Tiêu đề dài") for p in every)
    assert any("< hoặc >" in p for p in every)
    assert any("đang mở" in p for p in every)
