import os
import json
import re
import hmac
import hashlib
import asyncio
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from typing import Optional, List
from fastapi import FastAPI, Request, HTTPException, Query, Body, status
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.database import (
    save_submission, 
    get_submissions, 
    save_node_registration, 
    get_published_video_submissions,
    report_submission,
    init_db
)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

app = FastAPI(
    title="দৈনিক জাহান আইপিটিভি (Dainik Jahan IPTV)",
    description="Official Digital Broadcasting Platform of Dainik Jahan",
    version="2.0.0"
)

# Mount static assets
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# Jinja2 Templates
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Load datasets
def load_json(filename):
    filepath = DATA_DIR / filename
    if filepath.exists():
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

YOUTUBE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{11}$")

def extract_youtube_video_id(source_url):
    if not source_url:
        return None
    try:
        parsed = urlparse(source_url.strip())
    except ValueError:
        return None
    if parsed.scheme != "https":
        return None

    hostname = (parsed.hostname or "").lower()
    video_id = None
    if hostname in {"youtu.be", "www.youtu.be"}:
        video_id = parsed.path.strip("/").split("/")[0]
    elif hostname in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [None])[0]
        else:
            path_parts = [part for part in parsed.path.split("/") if part]
            if len(path_parts) >= 2 and path_parts[0] in {"embed", "shorts", "live"}:
                video_id = path_parts[1]
    return video_id if video_id and YOUTUBE_ID_PATTERN.fullmatch(video_id) else None

async def verify_public_youtube_video(video_id):
    def fetch_metadata():
        url = (
            "https://www.youtube.com/oembed?url="
            f"https://www.youtube.com/watch?v={video_id}&format=json"
        )
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "DainikJahanIPTV/1.0"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return (
            payload.get("type") == "video"
            and bool(payload.get("title"))
            and bool(payload.get("author_name"))
        )

    try:
        return await asyncio.to_thread(fetch_metadata)
    except urllib.error.HTTPError as error:
        if error.code in {400, 401, 403, 404, 410}:
            return False
        return None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None

def is_configured_stream(source):
    if not isinstance(source, str) or not source.strip():
        return False
    if "/static/images/sample_media/" in source:
        return False
    try:
        parsed = urlparse(source.strip())
    except ValueError:
        return False
    if parsed.scheme != "https":
        return False

    hostname = (parsed.hostname or "").lower()
    if hostname in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtu.be"}:
        return extract_youtube_video_id(source) is not None
    if hostname == "youtube-nocookie.com" or hostname.endswith(".youtube-nocookie.com"):
        video_id = parsed.path.rstrip("/").split("/")[-1]
        return bool(YOUTUBE_ID_PATTERN.fullmatch(video_id))
    if hostname == "player.vimeo.com":
        return parsed.path.startswith("/video/") and parsed.path.removeprefix("/video/").split("/")[0].isdigit()
    return parsed.path.lower().endswith((".m3u8", ".mp4", ".m4v", ".webm", ".ogg"))

def get_all_documentaries():
    community_items = []
    for submission in get_published_video_submissions():
        video_id = extract_youtube_video_id(submission.get("source_url"))
        if not video_id:
            continue
        title = submission.get("title") or "Community documentary"
        details = submission.get("details") or ""
        language = submission.get("content_language") or "Unknown"
        community_items.append({
            "id": submission["id"],
            "title_bn": title,
            "title_en": title,
            "broadcaster": submission.get("organization") or "Community submission",
            "source_type": "Community YouTube submission",
            "category": "Community documentary",
            "sub_category": language,
            "year": str(submission.get("created_at", ""))[:4],
            "duration": "",
            "resolution": "Source quality",
            "official_url": submission["source_url"],
            "embed_url": f"https://www.youtube-nocookie.com/embed/{video_id}",
            "fallback_video": "",
            "thumbnail": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
            "synopsis_bn": details,
            "synopsis_en": details,
            "featured": False,
            "tags": ["Community", language],
            "is_community": True,
        })
    verified_catalog_items = [item for item in VOD_ITEMS if item.get("source_verified")]
    return verified_catalog_items + community_items

CHANNELS = load_json("channels.json")
VOD_ITEMS = load_json("vod.json")
NEWS_ARTICLES = load_json("news.json")
EPG_DATA = load_json("epg.json")
FEDERATION_DATA = load_json("federation.json")
for channel in CHANNELS:
    channel["source_configured"] = any(
        is_configured_stream(channel.get(source_key))
        for source_key in ("primary_source", "secondary_source", "fallback_source")
    )
    channel["resolution"] = (
        "Source quality not verified"
        if channel["source_configured"]
        else "Source not configured"
    )
    channel["bitrate"] = "Source-provided"
    channel["audio"] = "Source-provided"

# Policy Titles map
POLICY_TITLES = {
    "copyright": "কপিরাইট সুরক্ষা ও বৌদ্ধিক স্বত্ব (Copyright Protection)",
    "privacy": "গোপনীয়তা নীতিমালা (Privacy Policy)",
    "editorial": "সম্পাদকীয় নীতিমালা (Editorial Policy)",
    "distribution": "কনটেন্ট ও বিতরণ নীতিমালা (Content & Distribution Policy)",
    "governance": "কমিউনিটি পরিচালনা বিধিমালা (Community Governance)",
    "federation": "ফেডারেশন নীতিমালা (Federation Policy)",
    "security": "তথ্য ও সিস্টেম নিরাপত্তা (Security Policy)",
    "terms": "ব্যবহারের সাধারণ শর্তাবলী (Terms of Use)",
    "opensource": "উন্মুক্ত সোর্স নীতিমালা (Open-Source Policy)",
    "contact": "যোগাযোগ ও প্রধান কার্যালয় (Contact & Headquarters)"
}

# --------------------------------------------------------------------------
# HTML PAGES
# --------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def home_page(
    request: Request,
    channel: Optional[str] = None,
    doc: Optional[str] = None,
    video: Optional[str] = None,
):
    selected_ch = CHANNELS[0]
    if channel:
        found = next((c for c in CHANNELS if c["id"] == channel), None)
        if found:
            selected_ch = found
    elif doc:
        found_doc = next((d for d in get_all_documentaries() if d["id"] == doc), None)
        if found_doc:
            selected_ch = {
                "id": found_doc["id"],
                "name": found_doc["title_bn"],
                "name_en": found_doc["title_en"],
                "user_content_type": "vod",
                "category": "Documentary",
                "category_bn": "প্রামাণ্যচিত্র",
                "authorized_by": found_doc["broadcaster"],
                "resolution": found_doc["resolution"],
                "bitrate": "Source-provided",
                "audio": "Source-provided",
                "stream_type": "embed" if found_doc["embed_url"] else "video",
                "primary_source": found_doc["embed_url"] or found_doc["fallback_video"],
                "secondary_source": found_doc["fallback_video"],
                "fallback_source": found_doc["fallback_video"],
                "federation_node": "DJ-DOC-ARCH-01",
                "description_bn": found_doc["synopsis_bn"],
                "description_en": found_doc["synopsis_en"],
                "is_bangladesh": True
            }
    elif video:
        found_video = next(
            (
                article
                for article in NEWS_ARTICLES
                if article["id"] == video and article.get("has_video") and article.get("video_url")
            ),
            None,
        )
        if found_video:
            video_url = found_video["video_url"]
            lower_url = video_url.lower()
            is_embed = "youtube.com" in lower_url or "youtu.be" in lower_url or "vimeo.com" in lower_url
            selected_ch = {
                "id": found_video["id"],
                "name": found_video.get("video_title") or found_video["title"],
                "name_en": found_video.get("title_en", ""),
                "user_content_type": "news",
                "category": "News",
                "category_bn": found_video["category"],
                "authorized_by": found_video.get("author", "Dainik Jahan Newsdesk"),
                "resolution": "1080p HD",
                "bitrate": "3800 kbps",
                "stream_type": "embed" if is_embed else "video",
                "primary_source": video_url,
                "secondary_source": video_url,
                "fallback_source": video_url,
                "description_bn": found_video.get("summary", found_video["title"]),
                "description_en": found_video.get("title_en", ""),
                "is_bangladesh": True,
            }

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "active_page": "home",
            "default_channel": selected_ch,
            "channels": CHANNELS,
            "documentaries": get_all_documentaries(),
            "news_articles": NEWS_ARTICLES
        }
    )

@app.get("/epg", response_class=HTMLResponse)
async def epg_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="epg.html",
        context={
            "active_page": "epg",
            "epg_data": EPG_DATA,
            "channels": CHANNELS
        }
    )

@app.get("/documentaries", response_class=HTMLResponse)
async def documentaries_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="documentaries.html",
        context={
            "active_page": "documentaries",
            "documentaries": get_all_documentaries()
        }
    )

@app.get("/news", response_class=HTMLResponse)
async def news_page(request: Request, category: Optional[str] = None):
    news_categories = sorted(
        {article.get("category", "") for article in NEWS_ARTICLES if article.get("category")}
    )
    selected_category = category if category in news_categories else None
    visible_news = [
        article
        for article in NEWS_ARTICLES
        if selected_category is None or article.get("category") == selected_category
    ]
    return templates.TemplateResponse(
        request=request,
        name="news.html",
        context={
            "active_page": "news",
            "news_articles": visible_news,
            "news_categories": news_categories,
            "selected_news_category": selected_category,
        }
    )

@app.get("/discovery", response_class=HTMLResponse)
async def discovery_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="discovery.html",
        context={
            "active_page": "discovery",
            "channels": CHANNELS
        }
    )

@app.get("/vod", response_class=HTMLResponse)
async def vod_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="vod.html",
        context={
            "active_page": "vod",
            "documentaries": get_all_documentaries()
        }
    )

@app.get("/favorites", response_class=HTMLResponse)
async def favorites_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="favorites.html",
        context={
            "active_page": "favorites",
            "channels": CHANNELS,
            "documentaries": get_all_documentaries(),
            "news_articles": NEWS_ARTICLES,
        }
    )

@app.get("/submissions", response_class=HTMLResponse)
async def submissions_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="submissions.html",
        context={
            "active_page": "submissions"
        }
    )

@app.get("/federation", response_class=HTMLResponse)
async def federation_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="federation.html",
        context={
            "active_page": "federation",
            "fed_data": FEDERATION_DATA
        }
    )

@app.get("/contact", response_class=HTMLResponse)
async def contact_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="contact.html",
        context={
            "active_page": "contact"
        }
    )

@app.get("/policy/{policy_slug}", response_class=HTMLResponse)
async def policy_page(request: Request, policy_slug: str):
    slug = policy_slug.lower()
    if slug not in POLICY_TITLES:
        slug = "copyright"
    return templates.TemplateResponse(
        request=request,
        name="policy.html",
        context={
            "active_page": "policy",
            "policy_slug": slug,
            "policy_title": POLICY_TITLES[slug]
        }
    )

# --------------------------------------------------------------------------
# REST API ENDPOINTS
# --------------------------------------------------------------------------

@app.get("/iptv-api/channels")
async def api_get_channels(
    category: Optional[str] = None,
    country: Optional[str] = None,
    language: Optional[str] = None,
    search: Optional[str] = None
):
    results = CHANNELS
    if category and category.lower() != "all":
        results = [c for c in results if c["category"].lower() == category.lower()]
    if country and country.lower() != "all":
        results = [c for c in results if country.lower() in c["country"].lower()]
    if language and language.lower() != "all":
        results = [c for c in results if language.lower() in c["language"].lower()]
    if search:
        q = search.lower()
        results = [c for c in results if q in c["name"].lower() or q in c["name_en"].lower() or q in c["category"].lower()]
    return {"status": "success", "count": len(results), "channels": results}

@app.get("/iptv-api/channels/{channel_id}")
async def api_get_channel(channel_id: str):
    ch = next((c for c in CHANNELS if c["id"] == channel_id), None)
    if not ch:
        raise HTTPException(status_code=404, detail="চ্যানেল পাওয়া যায়নি")
    
    health_status = {
        "status": "configured" if ch.get("source_configured") else "unavailable",
        "latency_ms": None,
        "authorized": None,
        "authorization_status": "not_independently_verified",
        "authorization_claim": ch.get("authorized_by"),
        "protocol": "configured source" if ch.get("source_configured") else None,
        "active_source": next(
            (
                ch.get(source_key)
                for source_key in ("primary_source", "secondary_source", "fallback_source")
                if is_configured_stream(ch.get(source_key))
            ),
            None,
        ),
    }
    return {"status": "success", "channel": ch, "health": health_status}

@app.get("/iptv-api/health-check")
async def api_health_check():
    configured_streams = sum(1 for channel in CHANNELS if channel.get("source_configured"))
    return {
        "status": "online",
        "platform": "Dainik Jahan IPTV Broadcast Engine",
        "version": "2.0.0",
        "channels_online": None,
        "configured_streams": configured_streams,
        "edge_nodes": len(FEDERATION_DATA["nodes"]),
        "authorization_validation": "not performed",
        "policy_compliance": "Automated URL checks and submitter declarations do not establish legal compliance."
    }

@app.get("/iptv-api/epg")
async def api_get_epg():
    return {"status": "success", "epg": EPG_DATA}

@app.get("/iptv-api/vod")
async def api_get_vod():
    documentaries = get_all_documentaries()
    return {"status": "success", "count": len(documentaries), "documentaries": documentaries}

@app.get("/iptv-api/news")
async def api_get_news():
    return {"status": "success", "count": len(NEWS_ARTICLES), "news": NEWS_ARTICLES}

class SubmissionRequest(BaseModel):
    type: str
    name: str
    email: str
    phone: Optional[str] = ""
    organization: Optional[str] = ""
    title: str
    details: str
    source_url: Optional[str] = ""
    country: Optional[str] = ""
    content_language: Optional[str] = "English"
    rights_confirmed: bool = False

@app.post("/iptv-api/submissions")
async def api_create_submission(sub: SubmissionRequest):
    publication_status = "pending"
    moderation_note = ""
    if sub.type == "documentary_submission":
        if not sub.country or not sub.country.strip():
            raise HTTPException(status_code=422, detail="Country or jurisdiction is required.")
        if not sub.rights_confirmed:
            raise HTTPException(status_code=422, detail="Confirm that you hold the required rights.")
        video_id = extract_youtube_video_id(sub.source_url)
        if not video_id:
            raise HTTPException(
                status_code=422,
                detail="Only valid HTTPS YouTube video links can be published automatically.",
            )
        video_is_public = await verify_public_youtube_video(video_id)
        if video_is_public:
            publication_status = "published"
        else:
            moderation_note = (
                "YouTube could not verify a public embeddable video. The submission is held automatically."
            )

    tracking_id = save_submission(
        sub.type,
        sub.name,
        sub.email,
        sub.phone,
        sub.organization,
        sub.title,
        sub.details,
        sub.source_url,
        sub.country,
        sub.content_language,
        sub.rights_confirmed,
        moderation_note,
        publication_status,
    )
    if publication_status == "published":
        message = (
            "The public YouTube video link passed the automated availability check and is now published. "
            "The check does not verify ownership or legal compliance."
        )
    elif sub.type == "documentary_submission":
        message = (
            "The video was held automatically because its public YouTube availability could not be verified. "
            "It is not visible in the library."
        )
    else:
        message = "Your submission was received but is not published."
    return {
        "status": "success",
        "message": message,
        "tracking_id": tracking_id,
        "content_status": publication_status,
        "moderation_note": moderation_note or None,
    }

@app.post("/iptv-api/community/{submission_id}/report")
async def api_report_community_video(submission_id: str, request: Request):
    forwarded_for = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    reporter_address = forwarded_for or (request.client.host if request.client else "unknown")
    report_secret = os.getenv("SESSION_SECRET", "dainik-jahan-reporting")
    fingerprint = hmac.new(
        report_secret.encode("utf-8"),
        reporter_address.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    result = report_submission(submission_id, fingerprint)
    if result is None:
        raise HTTPException(status_code=404, detail="Published community content was not found.")
    return {
        "status": "hidden" if result["hidden"] else "reported",
        **result,
    }

class NodeRegRequest(BaseModel):
    name: str
    operator: str
    endpoint_url: str
    region: str
    channels_count: Optional[int] = 1

@app.post("/iptv-api/federation/register")
async def api_register_node(reg: NodeRegRequest):
    node_id = save_node_registration(
        reg.name,
        reg.operator,
        reg.endpoint_url,
        reg.region,
        reg.channels_count
    )
    return {
        "status": "success",
        "message": "কমিউনিটি নোড সফলভাবে নিবন্ধিত হয়েছে",
        "node_id": node_id
    }

@app.get("/iptv-api/federation")
async def api_get_federation():
    return FEDERATION_DATA

@app.on_event("startup")
async def startup_event():
    init_db()
    print("Dainik Jahan IPTV Platform Engine started.")
