import os
from pathlib import Path
from typing import Any

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from logger import get_logger
from schemas import ChannelInfo

TOKEN_FILE = "token.json"
CLIENT_SECRET_FILE = "client_secret.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]
API_SERVICE_NAME = "youtube"
API_VERSION = "v3"

logger = get_logger(__name__)


def parse_channel_response(response: dict[str, Any]) -> ChannelInfo:
    if "items" not in response or not response["items"]:
        raise ValueError("Channel response missing items or items list is empty")
    
    item = response["items"][0]
    snippet = item.get("snippet", {})
    
    return ChannelInfo(
        channel_id=item["id"],
        title=snippet["title"],
        description=snippet.get("description", ""),
    )


def authenticate() -> None:
    if not Path(CLIENT_SECRET_FILE).exists():
        raise FileNotFoundError(
            f"Client secret file not found: {CLIENT_SECRET_FILE}. "
            "Please ensure client_secret.json exists in the project root."
        )

    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
    credentials = flow.run_local_server(open_browser=True)

    youtube = build(API_SERVICE_NAME, API_VERSION, credentials=credentials)
    request = youtube.channels().list(mine=True, part="snippet")
    response = request.execute()

    channel_info = parse_channel_response(response)
    logger.info(f"Successfully authenticated for channel: {channel_info.title}")

    with open(TOKEN_FILE, "w") as f:
        f.write(credentials.to_json())
    logger.info(f"Token saved to {TOKEN_FILE}")


def get_client():
    if not Path(TOKEN_FILE).exists():
        raise RuntimeError(
            "OAuth token not found. Run auth setup manually before starting workers."
        )

    credentials = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    youtube = build(API_SERVICE_NAME, API_VERSION, credentials=credentials)
    return youtube
