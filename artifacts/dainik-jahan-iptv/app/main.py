import os
import json
from pathlib import Path
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

CHANNELS = load_json("channels.json")
VOD_ITEMS = load_json("vod.json")
NEWS_ARTICLES = load_json("news.json")
EPG_DATA = load_json("epg.json")
FEDERATION_DATA = load_json("federation.json")

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
        found_doc = next((d for d in VOD_ITEMS if d["id"] == doc), None)
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
                "bitrate": "4200 kbps",
                "audio": "Stereo AAC 48kHz",
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
            "documentaries": VOD_ITEMS,
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
            "documentaries": VOD_ITEMS
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
            "documentaries": VOD_ITEMS
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
            "documentaries": VOD_ITEMS,
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
        "status": "healthy",
        "latency_ms": 28,
        "authorized": True,
        "authorized_by": ch["authorized_by"],
        "protocol": "HLS / HTML5 / Embed",
        "active_source": ch["primary_source"]
    }
    return {"status": "success", "channel": ch, "health": health_status}

@app.get("/iptv-api/health-check")
async def api_health_check():
    return {
        "status": "online",
        "platform": "Dainik Jahan IPTV Broadcast Engine",
        "version": "2.0.0",
        "channels_online": len(CHANNELS),
        "edge_nodes": len(FEDERATION_DATA["nodes"]),
        "policy_compliance": "Strict Anti-Piracy & Authorized Stream Routing"
    }

@app.get("/iptv-api/epg")
async def api_get_epg():
    return {"status": "success", "epg": EPG_DATA}

@app.get("/iptv-api/vod")
async def api_get_vod():
    return {"status": "success", "count": len(VOD_ITEMS), "documentaries": VOD_ITEMS}

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

@app.post("/iptv-api/submissions")
async def api_create_submission(sub: SubmissionRequest):
    tracking_id = save_submission(
        sub.type,
        sub.name,
        sub.email,
        sub.phone,
        sub.organization,
        sub.title,
        sub.details,
        sub.source_url
    )
    return {
        "status": "success",
        "message": "আবেদনটি সফলভাবে সংরক্ষিত হয়েছে",
        "tracking_id": tracking_id
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
