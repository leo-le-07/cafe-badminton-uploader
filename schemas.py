from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class MatchMetadata:
    match_type: str
    team1_names: list[str]
    team2_names: list[str]
    tournament: str
    title: str
    description: str
    category: str
    privacy_status: str


@dataclass(frozen=True)
class UploadedRecord:
    video_id: str
    uploaded_at: str
    thumbnail_set: bool
    youtube_link: str


@dataclass(frozen=True)
class ChannelInfo:
    channel_id: str
    title: str
    description: str
