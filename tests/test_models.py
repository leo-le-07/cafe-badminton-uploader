from app.models import Match, Segment, Session, match_problems, validate_session

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
