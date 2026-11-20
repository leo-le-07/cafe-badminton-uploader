import video_prep
from app.models import (
    Match,
    OpenPoint,
    Segment,
    Session,
    match_problems,
    match_title,
    title_fields,
    validate_session,
)

DUR = {"a.mov": 100.0, "b.mov": 50.0}


def _m(id="m1", segs=(("a.mov", 1.0, 5.0),), t1=("Nam",), t2=("Tú",)):
    return Match(
        id=id,
        match_type="ms",
        team1=list(t1),
        team2=list(t2),
        tournament="Cafe Game",
        segments=[Segment(*s) for s in segs],
    )


def test_valid_session_has_no_errors():
    assert validate_session(Session(["a.mov"], [_m()], None), DUR) == []


def test_overlap_across_matches_is_rejected():
    s = Session(
        ["a.mov"], [_m("m1", [("a.mov", 1, 5)]), _m("m2", [("a.mov", 4, 8)])], None
    )
    assert any("chồng" in e for e in validate_session(s, DUR))


def test_touching_segments_are_allowed():
    s = Session(
        ["a.mov"], [_m("m1", [("a.mov", 1, 5)]), _m("m2", [("a.mov", 5, 8)])], None
    )
    assert validate_session(s, DUR) == []


def test_segment_outside_source_or_reversed_is_rejected():
    assert validate_session(
        Session(["a.mov"], [_m(segs=[("a.mov", 90, 101)])], None), DUR
    )
    assert validate_session(Session(["a.mov"], [_m(segs=[("a.mov", 5, 5)])], None), DUR)


def test_segment_of_unselected_source_is_rejected():
    assert validate_session(Session(["a.mov"], [_m(segs=[("b.mov", 1, 2)])], None), DUR)


def test_match_id_must_be_filesystem_safe():
    assert validate_session(Session(["a.mov"], [_m(id="../x")], None), DUR)


def test_match_problems():
    assert match_problems(_m()) == []
    assert match_problems(_m(t2=()))  # thiếu tên một bên
    assert match_problems(_m(segs=()))  # chưa có đoạn


def test_roundtrip_keeps_vietnamese_names():
    m = _m(t1=("Tú", "Hùng"))
    assert Match.from_dict(m.to_dict()) == m


# ---- revision and the open point ------------------------------------------------


def test_old_session_file_has_revision_0_and_no_open_point():
    s = Session.from_dict({"sources": [], "matches": [], "selected_match_id": None})
    assert s.revision == 0 and s.open is None


def test_session_roundtrip_keeps_revision_and_open_point():
    s = Session(["a.mov"], [_m()], "m1", open=OpenPoint("m1", "a.mov", 7.5), revision=3)
    d = s.to_dict()
    assert d["open"] == {"match_id": "m1", "source": "a.mov", "time": 7.5}
    assert d["revision"] == 3
    assert Session.from_dict(d) == s


def _with_open(match_id="m1", source="a.mov", time=7.5, matches=None):
    return Session(
        ["a.mov"], matches or [_m()], "m1", open=OpenPoint(match_id, source, time)
    )


def test_valid_open_point():
    assert validate_session(_with_open(), DUR) == []
    # Right at the end of a segment (where I lands after a closed segment).
    assert validate_session(_with_open(time=5.0), DUR) == []
    assert validate_session(_with_open(time=0.0), DUR) == []


def test_open_point_must_belong_to_a_match_and_a_ticked_source():
    assert validate_session(_with_open(match_id="nope"), DUR)
    assert validate_session(_with_open(source="b.mov"), DUR)


def test_open_point_must_lie_within_its_source():
    assert validate_session(_with_open(time=100.5), DUR)
    assert validate_session(_with_open(time=-1), DUR)


def test_open_point_time_unchecked_when_duration_unknown():
    no_segments = [_m(segs=())]
    assert validate_session(_with_open(time=1e6, matches=no_segments), {}) == []


def test_open_point_cannot_start_inside_a_segment():
    errors = validate_session(_with_open(time=3.0), DUR)
    assert any("đang mở" in e for e in errors)
    other = [_m("m1", segs=()), _m("m2", segs=[("a.mov", 1.0, 5.0)])]
    assert validate_session(_with_open(time=3.0, matches=other), DUR)


def test_match_with_open_point_is_not_ready():
    assert match_problems(_m(), open_match_id="m1") == [
        "Còn một đoạn đang mở — bấm O để đóng"
    ]
    assert match_problems(_m(), open_match_id="m2") == []


# ---- title rules (mirrored in app/static/js/model.js) ---------------------------


def test_empty_tournament_uses_the_default_in_the_title():
    m = _m()
    m.tournament = "  "
    assert match_title(m, "2026-11-20") == "Nam vs Tú | Cafe Game (2026-11-20)"


def test_title_matches_the_uploaded_title():
    m = _m(t1=(" Nam ", "", "Hùng"), t2=("Tú",))
    m.tournament = " Giải Hè "
    names1, names2, tournament = title_fields(m)
    assert match_title(m, "2026-11-20") == video_prep.create_title(
        tournament, names1, names2, "2026-11-20"
    )
    assert (names1, tournament) == (["Nam", "Hùng"], "Giải Hè")


def test_title_longer_than_100_characters_is_a_problem():
    long_name = "Nguyễn Văn " + "A" * 70
    m = _m(t1=(long_name,), t2=("Tú",))
    n = len(match_title(m, "2026-11-20"))
    assert n > 100
    assert match_problems(m) == [f"Tiêu đề dài {n} ký tự, YouTube chỉ nhận tối đa 100"]
    fits = _m(t1=("A" * (long_name.__len__() - (n - 100)),), t2=("Tú",))
    assert len(match_title(fits, "2026-11-20")) == 100
    assert match_problems(fits) == []


def test_angle_brackets_in_names_or_tournament_are_a_problem():
    message = "Tên người chơi và giải không được chứa dấu < hoặc >"
    assert match_problems(_m(t1=("<Nam>",))) == [message]
    m = _m()
    m.tournament = "Cup > 1"
    assert match_problems(m) == [message]
