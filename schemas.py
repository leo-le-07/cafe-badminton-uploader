from typing import TypedDict


class MatchMetadata(TypedDict):
    matchType: str
    team1Names: list[str]
    team2Names: list[str]
    tournament: str
    title: str
    description: str
    category: str
    privacyStatus: str
