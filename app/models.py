import re
from dataclasses import asdict, dataclass

from constants import MATCH_TYPES

JOB_STATUSES = ("queued", "running", "waiting_quota", "error", "done")
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
        )


@dataclass
class Session:
    sources: list[str]
    matches: list[Match]
    selected_match_id: str | None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Session":
        return cls(
            sources=list(d["sources"]),
            matches=[Match.from_dict(m) for m in d["matches"]],
            selected_match_id=d.get("selected_match_id"),
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

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Job":
        return cls(
            match=Match.from_dict(d["match"]),
            recorded_date=d["recorded_date"],
            status=d["status"],
            step=d["step"],
            progress=float(d["progress"]),
            error=d.get("error"),
            youtube_link=d.get("youtube_link"),
            queued_at=d["queued_at"],
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

    return errors


def match_problems(match: Match) -> list[str]:
    """Return the reasons a match cannot be queued for upload yet."""
    problems: list[str] = []
    if not any(name.strip() for name in match.team1):
        problems.append("Thiếu tên người chơi đội 1")
    if not any(name.strip() for name in match.team2):
        problems.append("Thiếu tên người chơi đội 2")
    if not match.segments:
        problems.append("Chưa có đoạn nào")
    return problems
