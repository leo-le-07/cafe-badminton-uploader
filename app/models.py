import re
from dataclasses import asdict, dataclass

from constants import (
    CAFE_GAME_THEME,
    DEFAULT_MODE,
    DEFAULT_TOURNAMENT,
    TOURNAMENT_THEMES,
    MATCH_TYPES,
    MAX_TITLE_LENGTH,
    MODES,
)

JOB_STEPS = (
    "metadata",
    "select_thumbnail",
    "render_thumbnail",
    "encode",
    "upload",
    "set_thumbnail",
    "cleanup",
)

_MATCH_ID_PATTERN = re.compile(r"[a-z0-9-]+")


@dataclass
class Segment:
    source: str
    start: float
    end: float

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Segment":
        return cls(source=d["source"], start=float(d["start"]), end=float(d["end"]))


@dataclass
class Match:
    id: str
    match_type: str
    team1: list[str]
    team2: list[str]
    tournament: str
    segments: list[Segment]
    # Thumbnail colour for a tournament other than the default; "" = not
    # picked. See match_theme.
    theme: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Match":
        return cls(
            id=d["id"],
            match_type=d["match_type"],
            team1=list(d["team1"]),
            team2=list(d["team2"]),
            tournament=d["tournament"],
            segments=[Segment.from_dict(s) for s in d["segments"]],
            theme=d.get("theme", ""),
        )


@dataclass
class OpenPoint:
    """Where the segment being kept right now starts (`I` pressed, no `O`
    yet); `time` is local to `source`, like a segment's."""

    match_id: str
    source: str
    time: float

    @classmethod
    def from_dict(cls, d: dict) -> "OpenPoint":
        return cls(match_id=d["match_id"], source=d["source"], time=float(d["time"]))


@dataclass
class Session:
    sources: list[str]
    matches: list[Match]
    selected_match_id: str | None
    open: OpenPoint | None = None
    # Bumped by every stored change; a save must name the revision it was
    # based on, so a stale tab cannot overwrite newer work.
    revision: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Session":
        open = d.get("open")
        return cls(
            sources=list(d["sources"]),
            matches=[Match.from_dict(m) for m in d["matches"]],
            selected_match_id=d.get("selected_match_id"),
            open=OpenPoint.from_dict(open) if open is not None else None,
            revision=int(d.get("revision", 0)),
        )


@dataclass
class Job:
    match: Match
    recorded_date: str
    status: str
    step: str
    progress: float
    error: str | None
    youtube_link: str | None
    queued_at: str
    # The editor's mode when the match was queued; decides the upload privacy.
    mode: str = DEFAULT_MODE

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Job":
        # Jobs saved before modes existed, or with an unknown mode, are "dev":
        # a wrongly private upload is easy to fix, a wrongly public one is not.
        mode = d.get("mode")
        return cls(
            match=Match.from_dict(d["match"]),
            recorded_date=d["recorded_date"],
            status=d["status"],
            step=d["step"],
            progress=float(d["progress"]),
            error=d.get("error"),
            youtube_link=d.get("youtube_link"),
            queued_at=d["queued_at"],
            mode=mode if isinstance(mode, str) and mode in MODES else DEFAULT_MODE,
        )


def _fmt(seconds: float) -> str:
    return f"{seconds:g}s"


def validate_session(session: Session, durations: dict[str, float]) -> list[str]:
    """Return the structural errors that make a session unsaveable.

    Incomplete matches (missing names, no segments) are not errors here;
    see match_problems.
    """
    errors: list[str] = []
    seen_ids: set[str] = set()
    placed: list[tuple[Segment, str]] = []

    for match in session.matches:
        if not _MATCH_ID_PATTERN.fullmatch(match.id):
            errors.append(
                f"Mã trận không hợp lệ: {match.id!r} (chỉ gồm a-z, 0-9 và dấu -)"
            )
        if match.id in seen_ids:
            errors.append(f"Mã trận bị trùng: {match.id!r}")
        seen_ids.add(match.id)

        if match.match_type not in MATCH_TYPES:
            errors.append(
                f"Trận {match.id}: loại trận không hợp lệ: {match.match_type!r}"
            )

        for seg in match.segments:
            where = (
                f"Trận {match.id}: đoạn {seg.source} {_fmt(seg.start)}–{_fmt(seg.end)}"
            )
            if seg.source not in session.sources:
                errors.append(f"{where} thuộc file nguồn chưa được chọn")
                continue
            if seg.source not in durations:
                errors.append(f"{where} thuộc file nguồn không tồn tại")
                continue
            if seg.start >= seg.end:
                errors.append(f"{where} có điểm vào không nhỏ hơn điểm ra")
                continue
            if seg.start < 0 or seg.end > durations[seg.source]:
                errors.append(f"{where} nằm ngoài thời lượng của file nguồn")
                continue
            for other, other_id in placed:
                if (
                    other.source == seg.source
                    and seg.start < other.end
                    and other.start < seg.end
                ):
                    errors.append(
                        f"{where} chồng lên đoạn {_fmt(other.start)}–{_fmt(other.end)}"
                        f" của trận {other_id}"
                    )
            placed.append((seg, match.id))

    errors += _open_point_errors(session, durations)
    return errors


def _open_point_errors(session: Session, durations: dict[str, float]) -> list[str]:
    """An open point inside a segment is allowed: it is harmless (closing it
    with O clips against neighbouring segments) and refusing the save would
    risk losing the user's work. The editor never puts it there anyway."""
    point = session.open
    if point is None:
        return []
    where = (
        f"Đoạn đang mở của trận {point.match_id} ({point.source} {_fmt(point.time)})"
    )
    if point.match_id not in {m.id for m in session.matches}:
        return [f"{where} thuộc trận không có trong phiên làm việc"]
    if point.source not in session.sources:
        return [f"{where} thuộc file nguồn chưa được chọn"]
    if point.source in durations and not 0 <= point.time <= durations[point.source]:
        return [f"{where} nằm ngoài thời lượng của file nguồn"]
    return []


OPEN_SEGMENT_PROBLEM = "Còn một đoạn đang mở — bấm O để đóng"
ANGLE_BRACKET_PROBLEM = "Tên người chơi và giải không được chứa dấu < hoặc >"
# Any date has this length; the title's length does not depend on which.
_DATE_PLACEHOLDER = "0000-00-00"


def title_fields(match: Match) -> tuple[list[str], list[str], str]:
    """Names (trimmed, empty ones dropped) and tournament (the default when
    empty) as they go into the YouTube title and metadata."""

    def names(team: list[str]) -> list[str]:
        return [name.strip() for name in team if name.strip()]

    tournament = match.tournament.strip() or DEFAULT_TOURNAMENT
    return names(match.team1), names(match.team2), tournament


def match_theme(match: Match) -> str:
    """The thumbnail colour: the default tournament's own colour, else the
    picked one (the first choice when none or an unknown one is picked)."""
    tournament = title_fields(match)[2]
    if tournament.casefold() == DEFAULT_TOURNAMENT.casefold():
        return CAFE_GAME_THEME
    return match.theme if match.theme in TOURNAMENT_THEMES else TOURNAMENT_THEMES[0]


def match_title(match: Match, date: str) -> str:
    """The YouTube title, as video_prep.create_title builds it. Mirrored by
    previewTitle in app/static/js/model.js."""
    names1, names2, tournament = title_fields(match)
    return f"{'/'.join(names1)} vs {'/'.join(names2)} | {tournament} ({date})"


def match_problems(match: Match, open_match_id: str | None = None) -> list[str]:
    """Return the reasons a match cannot be queued for upload yet.

    `open_match_id` is the match that owns the session's open segment, which
    must be closed first. Mirrored by matchProblems in app/static/js/model.js.
    """
    problems: list[str] = []
    if not any(name.strip() for name in match.team1):
        problems.append("Thiếu tên người chơi đội 1")
    if not any(name.strip() for name in match.team2):
        problems.append("Thiếu tên người chơi đội 2")
    if not match.segments:
        problems.append("Chưa có đoạn nào")
    if open_match_id == match.id:
        problems.append(OPEN_SEGMENT_PROBLEM)
    if any(
        "<" in text or ">" in text
        for text in [*match.team1, *match.team2, match.tournament]
    ):
        problems.append(ANGLE_BRACKET_PROBLEM)
    length = len(match_title(match, _DATE_PLACEHOLDER))
    if length > MAX_TITLE_LENGTH:
        problems.append(
            f"Tiêu đề dài {length} ký tự, YouTube chỉ nhận tối đa {MAX_TITLE_LENGTH}"
        )
    return problems
