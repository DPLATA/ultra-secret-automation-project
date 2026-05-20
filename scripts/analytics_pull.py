"""One-off analytics snapshot across YouTube, Cloudflare, and MailerLite.

Reads tokens from secrets/analytics.json and reads the e2-micro uploaded
videos list from /tmp/e2_uploads.json. Prints a clean report to stdout.
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parent.parent
SECRETS = json.loads((REPO / "secrets" / "analytics.json").read_text())
UPLOADS = json.loads(Path("/tmp/e2_uploads.json").read_text())

YT_KEY = SECRETS["youtube_api_key"]
CF_TOKEN = SECRETS["cloudflare_token"]
ML_TOKEN = SECRETS["mailerlite_token"]


def hr(label):
    print()
    print("=" * 70)
    print(f"  {label}")
    print("=" * 70)


# -------- YouTube --------

def pull_youtube():
    hr("YOUTUBE")
    # Channel info via public handle lookup
    r = requests.get(
        "https://www.googleapis.com/youtube/v3/channels",
        params={"part": "snippet,statistics,brandingSettings",
                "forHandle": "@mlbsims", "key": YT_KEY},
        timeout=15,
    )
    r.raise_for_status()
    items = r.json().get("items", [])
    if not items:
        print("Channel @mlbsims not found via public handle lookup")
    else:
        c = items[0]
        s = c["statistics"]
        print(f"Channel:     {c['snippet']['title']}")
        print(f"Created:     {c['snippet']['publishedAt'][:10]}")
        print(f"Subscribers: {s.get('subscriberCount', '?')}")
        print(f"Total views: {s.get('viewCount', '?')}")
        print(f"Public videos count: {s.get('videoCount', '?')}")

    # Per-video stats — batch 50 at a time
    video_ids = [u["video_id"] for u in UPLOADS]
    all_stats = []
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i:i+50]
        r = requests.get(
            "https://www.googleapis.com/youtube/v3/videos",
            params={"part": "snippet,statistics,contentDetails",
                    "id": ",".join(chunk), "key": YT_KEY},
            timeout=15,
        )
        r.raise_for_status()
        all_stats.extend(r.json().get("items", []))

    title_by_id = {u["video_id"]: u["title"] for u in UPLOADS}
    upload_at_by_id = {u["video_id"]: u["uploaded_at"] for u in UPLOADS}

    all_stats.sort(key=lambda v: v["snippet"]["publishedAt"], reverse=True)

    print()
    print(f"Per-video stats (newest first, {len(all_stats)} of {len(video_ids)} found):")
    print(f"  {'Published':<19} {'Views':>6} {'Likes':>5} {'Comm':>4} {'Dur':<6} Title")
    print("  " + "-" * 95)
    total_v = total_l = total_c = 0
    short_v = short_count = long_v = long_count = 0
    for v in all_stats:
        s = v.get("statistics", {})
        vid = v["id"]
        title = (title_by_id.get(vid) or v["snippet"]["title"])[:55]
        dur = v.get("contentDetails", {}).get("duration", "?").replace("PT", "")
        views = int(s.get("viewCount", 0))
        likes = int(s.get("likeCount", 0))
        comments = int(s.get("commentCount", 0))
        # Crude Short detection: '#short' in title or duration < 3min vertical
        is_short = ("#short" in v["snippet"].get("title", "").lower()
                    or "recap" in title.lower())
        pub = v["snippet"]["publishedAt"][:16].replace("T", " ")
        print(f"  {pub:<19} {views:>6} {likes:>5} {comments:>4} {dur:<6} {title}")
        total_v += views; total_l += likes; total_c += comments
        if is_short:
            short_v += views; short_count += 1
        else:
            long_v += views; long_count += 1

    print()
    print(f"  TOTALS: {total_v} views, {total_l} likes, {total_c} comments")
    if short_count:
        print(f"  Shorts ({short_count}): {short_v} total views, avg {short_v//max(1,short_count)}")
    if long_count:
        print(f"  Longs  ({long_count}): {long_v} total views, avg {long_v//max(1,long_count)}")


# -------- Cloudflare --------

def cf_get(path, params=None):
    r = requests.get(
        f"https://api.cloudflare.com/client/v4{path}",
        headers={"Authorization": f"Bearer {CF_TOKEN}"},
        params=params or {},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def pull_cloudflare():
    hr("CLOUDFLARE")
    v = cf_get("/user/tokens/verify")
    print(f"Token status: {v['result']['status']}")

    # Go straight to zones (this token is zone-scoped, no account-level access).
    z = cf_get("/zones", params={"name": "mlbsims.com"})
    zones = z["result"]
    if not zones:
        print("Zone mlbsims.com not accessible")
        return
    zone = zones[0]
    zone_id = zone["id"]
    print(f"Zone: mlbsims.com ({zone_id})")
    print(f"Account: {zone['account']['name']}")
    print(f"Plan: {zone['plan']['name']}")
    print(f"Created: {zone['created_on'][:10]}")

    # Last 7 days HTTP requests via GraphQL — zone-level analytics
    if zone_id:
        end = date.today()
        start = end - timedelta(days=7)
        query = """
        query ZoneStats($zoneTag: String!, $start: Date!, $end: Date!) {
          viewer {
            zones(filter: {zoneTag: $zoneTag}) {
              httpRequests1dGroups(
                limit: 8
                filter: {date_geq: $start, date_leq: $end}
                orderBy: [date_ASC]
              ) {
                dimensions { date }
                sum {
                  requests
                  pageViews
                  cachedRequests
                  bytes
                }
                uniq { uniques }
              }
            }
          }
        }"""
        r = requests.post(
            "https://api.cloudflare.com/client/v4/graphql",
            headers={"Authorization": f"Bearer {CF_TOKEN}",
                     "Content-Type": "application/json"},
            json={"query": query, "variables": {
                "zoneTag": zone_id,
                "start": start.isoformat(),
                "end": end.isoformat(),
            }},
            timeout=15,
        )
        body = r.json()
        if body.get("errors"):
            print(f"GraphQL errors: {body['errors']}")
        else:
            try:
                groups = body["data"]["viewer"]["zones"][0]["httpRequests1dGroups"]
            except (KeyError, IndexError):
                groups = []
            if not groups:
                print("(No daily request data in last 7 days)")
            else:
                print()
                print("Last 7 days (mlbsims.com via Cloudflare edge):")
                print(f"  {'Date':<12} {'Requests':>9} {'PageViews':>10} {'Unique':>8} {'MB':>8}")
                total_req = total_pv = total_uniq = total_bytes = 0
                for g in groups:
                    d = g["dimensions"]["date"]
                    rq = g["sum"]["requests"]
                    pv = g["sum"]["pageViews"]
                    uq = g["uniq"]["uniques"]
                    mb = g["sum"]["bytes"] / 1024 / 1024
                    total_req += rq; total_pv += pv; total_uniq += uq; total_bytes += mb
                    print(f"  {d:<12} {rq:>9} {pv:>10} {uq:>8} {mb:>8.1f}")
                print(f"  {'TOTAL':<12} {total_req:>9} {total_pv:>10} {total_uniq:>8} {total_bytes:>8.1f}")


# -------- MailerLite --------

def ml_get(path, params=None):
    r = requests.get(
        f"https://connect.mailerlite.com/api{path}",
        headers={"Authorization": f"Bearer {ML_TOKEN}",
                 "Accept": "application/json"},
        params=params or {},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def pull_mailerlite():
    hr("MAILERLITE")
    s = ml_get("/subscribers", params={"limit": 100, "filter[status]": "active"})
    active_count = s.get("meta", {}).get("total", 0)
    print(f"Active subscribers: {active_count}")

    if active_count > 0:
        recent = s.get("data", [])[:10]
        print(f"\nRecent subscribers (newest first):")
        for sub in recent:
            print(f"  {sub.get('subscribed_at', '?')[:16]}  {sub.get('email', '?')}")

    # Forms — fetch each by ID for full stats
    f = ml_get("/forms/embedded")
    forms = f.get("data", [])
    if forms:
        print(f"\nEmbedded forms ({len(forms)}):")
        for form in forms:
            fid = form["id"]
            detail = ml_get(f"/forms/{fid}").get("data", {})
            opens = detail.get("opens_count", 0)
            conv = detail.get("conversions_count", 0)
            rate = (conv / opens * 100) if opens else 0
            print(f"  '{detail.get('name', '?')}'")
            print(f"    form views (opens): {opens}")
            print(f"    conversions: {conv}")
            print(f"    conversion rate: {rate:.2f}%")
            print(f"    created: {detail.get('created_at', '?')[:10]}")


def main():
    print("# MLB Sims Analytics Snapshot")
    print(f"# Generated: {date.today().isoformat()}")
    try:
        pull_youtube()
    except Exception as e:
        print(f"\nYouTube error: {e}")
    try:
        pull_cloudflare()
    except Exception as e:
        print(f"\nCloudflare error: {e}")
    try:
        pull_mailerlite()
    except Exception as e:
        print(f"\nMailerLite error: {e}")


if __name__ == "__main__":
    main()
