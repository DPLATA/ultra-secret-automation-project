"""YouTube auth + resumable upload helper.

Used by both upload_manual.py (one-off, takes a compilation_id) and
upload_daily.py (cron, drains the pending queue under quota).
"""

import logging
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
SECRETS_DIR = Path("secrets")
CLIENT_SECRETS_FILE = SECRETS_DIR / "client_secrets.json"
TOKEN_FILE = SECRETS_DIR / "token.json"
SPORTS_CATEGORY_ID = "17"


def load_credentials() -> Credentials:
    creds: Credentials | None = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        if not CLIENT_SECRETS_FILE.exists():
            sys.exit(
                f"Missing {CLIENT_SECRETS_FILE}. See README for OAuth setup."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRETS_FILE), SCOPES)
        creds = flow.run_local_server(port=0)
    SECRETS_DIR.mkdir(exist_ok=True)
    TOKEN_FILE.write_text(creds.to_json())
    return creds


def build_client():
    return build("youtube", "v3", credentials=load_credentials())


def upload_video(
    youtube,
    file_path: str,
    title: str,
    description: str,
    tags: list[str],
    privacy_status: str = "private",
    progress_cb=None,
) -> str:
    """Resumable upload; returns the new YouTube video ID."""
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": SPORTS_CATEGORY_ID,
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(
        file_path, chunksize=8 * 1024 * 1024, resumable=True, mimetype="video/mp4"
    )
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status and progress_cb is not None:
            progress_cb(int(status.progress() * 100))
    return response["id"]
