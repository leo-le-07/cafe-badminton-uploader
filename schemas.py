from dataclasses import dataclass


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
