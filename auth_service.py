import os

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

TOKEN_FILE = "token.json"
CLIENT_SECRET_FILE = "client_secret.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]
API_SERVICE_NAME = "youtube"
API_VERSION = "v3"


def authenticate_youtube():
    credentials = None
    if os.path.isfile(TOKEN_FILE):
        credentials = Credentials.from_authorized_user_file(TOKEN_FILE)

    else:
        flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)

        credentials = flow.run_local_server(
            open_browser=True,
        )

    youtube = build(API_SERVICE_NAME, API_VERSION, credentials=credentials)

    request = youtube.channels().list(mine=True, part="snippet")
    response = request.execute()

    print(
        f"Successfully authenticated for channel: {response['items'][0]['snippet']['title']}"
    )

    with open(TOKEN_FILE, "w") as f:
        f.write(credentials.to_json())
    return youtube
