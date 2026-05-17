"""Extract the source URL of a Baseball Savant sporty-videos clip."""

import logging
from typing import Optional

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)


def get_video_src_from_url(url: str) -> Optional[str]:
    """Return the `src` of the `<video id="sporty">` source, or None if missing."""
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    video_tag = soup.find("video", id="sporty")
    if not video_tag:
        log.warning("video tag not found at %s", url)
        return None
    source_tag = video_tag.find("source")
    if not source_tag or not source_tag.get("src"):
        log.warning("source tag missing src at %s", url)
        return None
    return source_tag["src"]
