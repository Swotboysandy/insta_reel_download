# Instagram Reel Downloader + Video Branding Studio
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from urllib.parse import urlsplit
from werkzeug.exceptions import ClientDisconnected
from werkzeug.utils import secure_filename
import instaloader
import os
import random
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
import uuid
import time
import re
import textwrap
import json
import base64
import mimetypes
import subprocess
import tempfile
from io import BytesIO
from dotenv import load_dotenv

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import sys

# Two different roots, and mixing them up breaks the packaged build:
#   APP_DIR    - where the user's data lives. Next to the .exe when frozen, so
#                downloads/history/.env survive between runs. PyInstaller's
#                __file__ points into a temp folder Windows later deletes.
#   BUNDLE_DIR - read-only files shipped inside the build (the exported UI).
if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(sys.executable)
    BUNDLE_DIR = getattr(sys, '_MEIPASS', APP_DIR)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
    BUNDLE_DIR = APP_DIR

load_dotenv(os.path.join(APP_DIR, ".env"))

app = Flask(__name__)
CORS(app)

DOWNLOAD_FOLDER = os.path.join(APP_DIR, "downloaded_reels")
BRANDED_FOLDER  = os.path.join(APP_DIR, "branded_videos")
HISTORY_FILE = os.path.join(APP_DIR, "download_history.json")
# Statically-exported Next.js UI (frontend/out). Serving it from Flask means one
# process on one port instead of a separate `next dev` server.
FRONTEND_DIR = os.path.join(BUNDLE_DIR, "frontend", "out")
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
MANAGED_VIDEO_FOLDERS = [DOWNLOAD_FOLDER, BRANDED_FOLDER]
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
os.makedirs(BRANDED_FOLDER, exist_ok=True)
HISTORY_LOCK = threading.Lock()

IG_USERNAME = os.getenv("IG_USERNAME", "")
IG_PASSWORD = os.getenv("IG_PASSWORD", "")

# Branding defaults
BRAND_DEFAULTS = {
    "target_width": 1080,
    "target_height": 1920,
    "text_area_height": 420,
    "bg_color": [0, 0, 0],
    "text_color": [255, 255, 255],
    "font_size": 52,
    "text_margin": 60,
    "text_top_padding": 80,
    "line_spacing": 14,

    # ── Layout / branding style (customizable from the UI) ──────────────────
    # style: "watermark" = full-frame video plus a bottom profile/caption row.
    # "header" retains the legacy top bar. Overridable per job via config.
    # Explicit style="header" remains supported for saved jobs.
    "style": "watermark",
    # zoom_factor: centre zoom on the video for reframing. 1.0 = unchanged.
    "zoom_factor": 1.0,

    # ── Per-video variation (so a batch isn't 100 byte-identical uploads) ──
    # audio_pitch: 1.0 = untouched. 1.06 raises pitch ~6% WITHOUT changing
    # duration (asetrate shifts pitch+tempo, atempo puts the tempo back).
    "audio_pitch": 1.0,
    # When true, each video gets its own random pitch/zoom from the ranges below.
    "randomize_variation": False,
    # ±3% — enough to break an audio fingerprint, subtle enough that speech
    # doesn't sound chipmunked. Widen only for music-only clips.
    "pitch_range": [0.97, 1.03],
    "zoom_range": [1.0, 1.05],
    # Profile footer styling (saved watermark keys remain accepted).
    "watermark_opacity": 0.92,
    "watermark_position": "middle-left",  # Legacy key; profile rows now anchor below content.
    "watermark_scale": 1.0,
    "upscale_sharpen": 1.25,
    "fill_blur": 28,
    "watermark_margin": 48,
    # Height of the unchanged profile card directly below the picture.
    "profile_footer_height": 220,
    # Breathing room above the content stack, so the picture does not run into
    # the very top edge of the frame. Also shortens the picture by the same
    # amount. Only applies to the profile-footer style; "header" owns its top.
    "content_top_padding": 260,
    # Matching gap between the bottom of the picture and the profile card, so
    # the picture reads as a centred card rather than something wedged against
    # the branding. Both gaps shorten the picture.
    "content_bottom_gap": 170,
    # Normalized source coordinates [x, y, width, height], before scaling.
    # Example: {"fboy": {"enabled": True, "region": [.85, .25, .15, .08]}}
    "video_watermark_path": "",  # Empty path or position="off" disables it.
    "video_watermark_position": "top-left",
    "video_watermark_width_fraction": 0.22,
    "video_watermark_opacity": 0.14,
    "source_watermarks": {},
    "source_watermark": {"enabled": False},
}

# Add future pages here, or point BRAND_LOGO_PACKS_DIR at another pack root.
BRAND_LOGO_PACKS_DIR = os.getenv("BRAND_LOGO_PACKS_DIR", os.path.join(os.path.dirname(APP_DIR), "Logo Packs"))
BRAND_PRESETS = {
    name: {
        "page_name": name,
        "handle": handle,
        "avatar_image": os.path.join(BRAND_LOGO_PACKS_DIR, name, "avatar-mark-1024.png"),
        "watermark_image": os.path.join(BRAND_LOGO_PACKS_DIR, name, "watermarks", "watermark-white-1024.png"),
    }
    for name, handle in (("epicmemeOclock", "@epicmemeoclock"),
                         ("sandy_dumps_here", "@sandy_dumps_here"))
}


def _resolve_brand_preset(cfg=None, profile_cfg=None):
    """Explicit job fields override preset fields; no preset preserves legacy jobs."""
    cfg = dict(cfg or {})
    profile = dict(profile_cfg or {})
    name = cfg.get("brand_preset")
    if name:
        if name not in BRAND_PRESETS:
            raise ValueError(f"Unknown brand preset: {name}")
        preset = BRAND_PRESETS[name]
        profile = {"page_name": preset["page_name"], "handle": preset["handle"],
                   "logo_path": preset["avatar_image"], **profile}
        cfg.setdefault("video_watermark_path", preset["watermark_image"])
    return cfg, profile


# All batch workers and previews share this process-wide limit.
BRAND_WORKERS = max(1, int(os.getenv("BRAND_WORKERS", "1")))
BRAND_PRESET = os.getenv("BRAND_PRESET", "veryfast")
BRAND_THREADS = int(os.getenv("BRAND_THREADS", "2"))
BRAND_RENDER_SLOTS = threading.BoundedSemaphore(BRAND_WORKERS)

download_tasks = {}
brand_tasks = {}
cleanup_tasks = {}
GLOBAL_LOADER = None

# Parallel download settings.
# 2 workers keeps IG from flagging the account; each gets its own session context.
DOWNLOAD_WORKERS = 2
DOWNLOAD_SLEEP_MIN = 1.0   # seconds between requests per worker
DOWNLOAD_SLEEP_MAX = 1.6
_thread_local = threading.local()   # holds one Instaloader per worker thread

def get_logged_in_loader():
    global GLOBAL_LOADER
    if GLOBAL_LOADER is not None:
        return GLOBAL_LOADER

    print("🔑 Initializing Instaloader with login...")
    loader = instaloader.Instaloader(
        download_videos=True,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        post_metadata_txt_pattern="",
        dirname_pattern=os.path.join(DOWNLOAD_FOLDER, "{profile}")
    )

    session_file = os.path.join(APP_DIR, f"session-{IG_USERNAME}")
    try:
        loader.load_session_from_file(IG_USERNAME, session_file)
        print(f"✅ Loaded existing session for {IG_USERNAME}")
        GLOBAL_LOADER = loader
        return loader
    except Exception as e:
        print(f"⚠️ No existing session: {e}")

    try:
        print(f"🔐 Logging in as {IG_USERNAME}...")
        loader.login(IG_USERNAME, IG_PASSWORD)
        print("✅ Login successful!")
        loader.save_session_to_file(session_file)
        GLOBAL_LOADER = loader
        return loader
    except instaloader.exceptions.TwoFactorAuthRequiredException:
        print("❌ 2FA required! Run insta_reel.py manually first to login.")
        return None
    except Exception as e:
        print(f"❌ Login failed: {e}")
        return None


def _get_thread_loader():
    """Return a per-thread Instaloader instance (creates one the first time a thread calls this).
    Each worker thread gets its own context so they never share HTTP state."""
    if not hasattr(_thread_local, 'loader'):
        loader = instaloader.Instaloader(
            download_videos=True,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            post_metadata_txt_pattern="",
            dirname_pattern=os.path.join(DOWNLOAD_FOLDER, "{profile}")
        )
        session_file = os.path.join(APP_DIR, f"session-{IG_USERNAME}")
        try:
            loader.load_session_from_file(IG_USERNAME, session_file)
        except Exception as e:
            print(f"⚠️ Worker thread: could not load session ({e}); using anonymous context.")
        _thread_local.loader = loader
    return _thread_local.loader


def _download_one(url, target_username, mode):
    """Download a single post. Runs inside a worker thread."""
    shortcode = extract_shortcode(url)
    if not shortcode:
        return {'url': url, 'success': False, 'error': 'no shortcode'}
    loader = _get_thread_loader()
    try:
        post = instaloader.Post.from_shortcode(loader.context, shortcode)
        loader.download_post(post, target=target_username)
        # Capture view count now — it's already on the post object, no extra API call
        views = getattr(post, 'video_view_count', None) if post.is_video else None
        _record_download(shortcode, url, target_username, mode,
                         view_count=views, file_path=_post_file_path(target_username, post))
        time.sleep(random.uniform(DOWNLOAD_SLEEP_MIN, DOWNLOAD_SLEEP_MAX))
        return {'url': url, 'shortcode': shortcode, 'success': True, 'view_count': views}
    except Exception as e:
        return {'url': url, 'shortcode': shortcode, 'success': False, 'error': str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# URL PARSING HELPERS
# ═══════════════════════════════════════════════════════════════════════════════
def extract_shortcode(url):
    if not url:
        return None
    url = url.strip()
    try:
        if '/reel/' in url or '/p/' in url:
            parts = url.rstrip('/').split('/')
            return parts[-1] if parts[-1] else parts[-2]
    except:
        pass
    for pattern in [r'instagram\.com/reel/([A-Za-z0-9_-]+)', r'instagram\.com/p/([A-Za-z0-9_-]+)']:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def extract_username_from_profile(url):
    for pattern in [r'instagram\.com/([A-Za-z0-9_.]+)/reels/?', r'instagram\.com/([A-Za-z0-9_.]+)/?$']:
        match = re.search(pattern, url)
        if match:
            username = match.group(1)
            if username not in ['reel', 'p', 'stories', 'explore', 'accounts', 'direct']:
                return username
    return None

def is_profile_url(url):
    return extract_username_from_profile(url) is not None and extract_shortcode(url) is None


# ═══════════════════════════════════════════════════════════════════════════════
# DOWNLOAD HISTORY (skip already-downloaded shortcodes)
# ═══════════════════════════════════════════════════════════════════════════════
def _load_history():
    """Load the history file. Returns {'version': 1, 'entries': {shortcode: {...}}}."""
    if not os.path.isfile(HISTORY_FILE):
        return {"version": 1, "entries": {}}
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or not isinstance(data.get("entries"), dict):
            return {"version": 1, "entries": {}}
        return data
    except Exception as e:
        print(f"⚠️ Could not load history: {e}")
        return {"version": 1, "entries": {}}


def _save_history(history):
    """Atomically write the history file."""
    try:
        tmp = HISTORY_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
        os.replace(tmp, HISTORY_FILE)
    except Exception as e:
        print(f"⚠️ Could not save history: {e}")


def _record_download(shortcode, url, username, mode, view_count=None, file_path=None):
    """Append a successful download to the history file (thread-safe)."""
    if not shortcode:
        return
    with HISTORY_LOCK:
        history = _load_history()
        history.setdefault("entries", {})[shortcode] = {
            "url": url,
            "username": username or "",
            "mode": mode or "reel",
            "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "view_count": view_count,
            "file_path": file_path or "",
        }
        _save_history(history)


def _post_file_path(username, post):
    """Resolve the file instaloader wrote for a post.
    Its default pattern is {date_utc}_UTC inside downloaded_reels/{profile}/."""
    stamp = post.date_utc.strftime("%Y-%m-%d_%H-%M-%S") + "_UTC"
    folder = os.path.join(DOWNLOAD_FOLDER, username or "")
    for ext in VIDEO_EXTENSIONS:
        candidate = os.path.join(folder, stamp + ext)
        if os.path.isfile(candidate):
            return candidate
    return ""


def _clear_history():
    """Wipe the history file."""
    with HISTORY_LOCK:
        _save_history({"version": 1, "entries": {}})


def _filter_known_urls(urls):
    """Given a list of URLs, return (new_urls, skipped_count)."""
    with HISTORY_LOCK:
        entries = _load_history().get("entries", {})
    new_urls = []
    skipped = 0
    for url in urls:
        sc = extract_shortcode(url)
        if sc and sc in entries:
            skipped += 1
            continue
        new_urls.append(url)
    return new_urls, skipped


# ═══════════════════════════════════════════════════════════════════════════════
# VIDEO PATH ALLOWLIST
# The playback route takes a caller-supplied path, so it must be constrained to
# folders this app actually manages — otherwise it serves any file on the box
# (.env, the Instagram session file, ...) to anyone who can reach the port.
# ═══════════════════════════════════════════════════════════════════════════════
# The list is fixed at startup and can only be widened by editing .env — never
# by an API request. Add extra folders with EXTRA_VIDEO_ROOTS, separated by ';'
# (os.pathsep), e.g.  EXTRA_VIDEO_ROOTS=F:\videos\out;D:\clips
def _build_video_roots():
    roots = {os.path.realpath(DOWNLOAD_FOLDER), os.path.realpath(BRANDED_FOLDER)}
    for raw in os.getenv("EXTRA_VIDEO_ROOTS", "").split(os.pathsep):
        # Strip surrounding quotes inline — this runs at import time, before
        # _clean_path is defined further down the module.
        folder = (raw or "").strip().strip('"').strip("'").strip()
        if not folder:
            continue
        if os.path.isdir(folder):
            roots.add(os.path.realpath(folder))
        else:
            print(f"⚠️ EXTRA_VIDEO_ROOTS entry is not a directory, ignoring: {folder}")
    return frozenset(roots)


VIDEO_ROOTS = _build_video_roots()


def _is_allowed_video_path(path):
    """True only for a video file inside one of the fixed VIDEO_ROOTS."""
    if os.path.splitext(path)[1].lower() not in VIDEO_EXTENSIONS:
        return False
    real = os.path.realpath(path)
    for root in VIDEO_ROOTS:
        try:
            if os.path.commonpath([real, root]) == root:
                return True
        except ValueError:
            continue  # different drive on Windows
    return False


def _is_allowed_video_root(folder):
    """True if a folder is inside the allowlist (used to flag unplayable listings)."""
    if not folder:
        return False
    real = os.path.realpath(folder)
    for root in VIDEO_ROOTS:
        try:
            if os.path.commonpath([real, root]) == root:
                return True
        except ValueError:
            continue
    return False


# ═══════════════════════════════════════════════════════════════════════════════
# TASK LOGGING
# ═══════════════════════════════════════════════════════════════════════════════
MAX_KEPT_TASKS = 20

def _prune_tasks(store):
    """Drop the oldest finished tasks so long-running servers don't grow unbounded."""
    finished = [(t.get('created_at', 0), tid) for tid, t in store.items()
                if t.get('state') == 'completed']
    for _, tid in sorted(finished)[:max(0, len(finished) - MAX_KEPT_TASKS)]:
        store.pop(tid, None)


def log_task(task_id, message, task_store=None):
    store = task_store or download_tasks
    if task_id in store:
        timestamp = time.strftime("[%H:%M:%S]")
        log_entry = f"{timestamp} {message}"
        store[task_id]['logs'].append(log_entry)
        store[task_id]['status'] = message
        print(log_entry)


# ═══════════════════════════════════════════════════════════════════════════════
# CLEANUP: DELETE LOW-VIEW REELS
# ═══════════════════════════════════════════════════════════════════════════════
def cleanup_low_views_runner(task_id, min_views, dry_run=False):
    """Delete downloaded reels whose view count is below min_views.
    Entries missing a view count are fetched from Instagram (one call each, rate-limited)."""
    store = cleanup_tasks
    with HISTORY_LOCK:
        history = _load_history()
    entries = history.get("entries", {})

    store[task_id]['total'] = len(entries)
    log_task(task_id, f"Checking {len(entries)} history entries (threshold: {min_views:,} views)...", store)

    loader = get_logged_in_loader()
    deleted, kept, unknown, fetched = [], 0, 0, 0
    checked = 0

    for shortcode, info in list(entries.items()):
        checked += 1
        store[task_id]['current'] = checked

        views = info.get("view_count")
        path = info.get("file_path") or ""

        # Backfill from Instagram when we lack the view count or the file path
        if (views is None or not path) and loader:
            try:
                post = instaloader.Post.from_shortcode(loader.context, shortcode)
                views = getattr(post, 'video_view_count', None) if post.is_video else None
                path = _post_file_path(info.get("username", ""), post)
                info["view_count"] = views
                info["file_path"] = path
                fetched += 1
                time.sleep(random.uniform(1.0, 2.0))  # be gentle with the API
            except Exception as e:
                err = str(e)
                if "wait" in err.lower() or "401" in err or "429" in err:
                    log_task(task_id, f"⏳ Rate-limited at {checked}/{len(entries)}. Stopping backfill early.", store)
                    break
                log_task(task_id, f"   Skipped {shortcode}: {e}", store)
                unknown += 1
                continue

        if views is None:
            unknown += 1
            continue
        if not path or not os.path.isfile(path):
            continue
        # The path comes out of a JSON file on disk — never delete anything
        # that isn't a video inside a folder this app manages.
        if not _is_allowed_video_path(path):
            log_task(task_id, f"   ⚠️ Skipped {shortcode}: path outside managed folders ({path})", store)
            continue

        if views < min_views:
            if dry_run:
                deleted.append({'shortcode': shortcode, 'views': views, 'path': path})
                log_task(task_id, f"   [dry-run] would delete {os.path.basename(path)} ({views:,} views)", store)
            else:
                try:
                    os.remove(path)
                    entries.pop(shortcode, None)
                    deleted.append({'shortcode': shortcode, 'views': views, 'path': path})
                    log_task(task_id, f"   🗑 Deleted {os.path.basename(path)} ({views:,} views)", store)
                except Exception as e:
                    log_task(task_id, f"   ❌ Could not delete {path}: {e}", store)
        else:
            kept += 1

    # Persist backfilled view counts (and removals) back to history.
    # This loop can run for many minutes, so re-read and merge instead of writing
    # back the snapshot — otherwise any download that finished meanwhile is lost.
    with HISTORY_LOCK:
        fresh = _load_history()
        fresh_entries = fresh.setdefault("entries", {})
        for sc, info in entries.items():
            if sc in fresh_entries:
                fresh_entries[sc]["view_count"] = info.get("view_count")
                fresh_entries[sc]["file_path"] = info.get("file_path", "")
        if not dry_run:
            for item in deleted:
                fresh_entries.pop(item['shortcode'], None)
        _save_history(fresh)

    store[task_id].update({
        'state': 'completed',
        'deleted_count': len(deleted),
        'deleted': deleted,
        'kept_count': kept,
        'unknown_count': unknown,
        'fetched_count': fetched,
        'completed_at': time.time(),
    })
    verb = "Would delete" if dry_run else "Deleted"
    log_task(task_id, f"✅ {verb} {len(deleted)} · kept {kept} · unknown {unknown} · fetched {fetched} from IG", store)


# ═══════════════════════════════════════════════════════════════════════════════
# SELENIUM: FETCH REELS / POSTS FROM PROFILE
# ═══════════════════════════════════════════════════════════════════════════════
# SeleniumBase UC mode defeats Instagram's bot wall, which otherwise serves a
# login/consent shell: the feed never grows past ~985px and only the first dozen
# links are reachable. Plain Selenium stays as the fallback.
USE_SELENIUMBASE = os.getenv("USE_SELENIUMBASE", "1").strip() != "0"
# UC mode is strongest with a real window. Set SB_HEADLESS=1 to hide it.
SB_HEADLESS = os.getenv("SB_HEADLESS", "0").strip() == "1"


def _create_seleniumbase_driver():
    from seleniumbase import Driver
    return Driver(uc=True, headless2=SB_HEADLESS, window_size="1920,1080",
                  agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")


def _create_driver():
    if USE_SELENIUMBASE:
        try:
            return _create_seleniumbase_driver()
        except Exception as e:
            print(f"SeleniumBase UC driver unavailable ({e}); falling back to plain Selenium.")
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    driver = webdriver.Chrome(options=options)
    # Remove the navigator.webdriver flag that Instagram uses to detect headless Chrome
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    return driver

def _instaloader_collect(username, max_items, video_only, task_id):
    """Collect post URLs by injecting Instaloader session cookies into Chrome.
    This hits Instagram's normal web endpoint (not graphql) — avoids API rate limits."""
    loader = get_logged_in_loader()
    if not loader:
        log_task(task_id, "❌ No authenticated session. Check IG_USERNAME/IG_PASSWORD in .env.")
        return []

    # Extract cookies from the instaloader requests session
    ig_cookies = []
    try:
        for c in loader.context._session.cookies:
            # Always use .instagram.com — prevents .www.instagram.com mis-normalization
            ig_cookies.append({
                'name': c.name,
                'value': c.value,
                'domain': '.instagram.com',
                'path': '/',
                'secure': True,
            })
    except Exception as e:
        log_task(task_id, f"❌ Could not read session cookies: {e}")
        return []

    if not ig_cookies:
        log_task(task_id, "❌ Session has no cookies. Try re-logging in.")
        return []

    cookie_names = [c['name'] for c in ig_cookies]
    log_task(task_id, f"   Injecting cookies: {cookie_names}")
    driver = _create_driver()
    try:
        # Must be on the domain before setting cookies
        driver.get("https://www.instagram.com/")
        time.sleep(2)
        for cookie in ig_cookies:
            try:
                driver.add_cookie(cookie)
            except Exception:
                pass

        # Reload so browser applies the new session cookies
        driver.get("https://www.instagram.com/")
        time.sleep(3)

        # Navigate to the profile page — authenticated via cookies
        link_type = "reel" if video_only else "p"
        page_url = (f"https://www.instagram.com/{username}/reels/"
                    if video_only else f"https://www.instagram.com/{username}/")
        driver.get(page_url)

        # Wait up to 15s for the first content link to appear
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located(
                    (By.XPATH, "//a[contains(@href, '/reel/') or contains(@href, '/p/')]")
                )
            )
        except Exception:
            pass  # will log below

        if "login" in driver.current_url or "accounts" in driver.current_url:
            log_task(task_id, "❌ Cookie auth failed — session may be expired. Re-login required.")
            return []

        # Dismiss the "Sign up to see more" modal if present
        for selector in ['[aria-label="Close"]', 'button[tabindex="0"]']:
            try:
                close_btn = driver.find_element(By.CSS_SELECTOR, selector)
                if close_btn.is_displayed():
                    close_btn.click()
                    time.sleep(0.5)
                    break
            except Exception:
                pass

        ph = driver.execute_script("return document.body.scrollHeight")
        total_anchors = len(driver.find_elements(By.TAG_NAME, "a"))
        content_links = len(driver.find_elements(
            By.XPATH, "//a[contains(@href, '/reel/') or contains(@href, '/p/')]"
        ))
        log_task(task_id, f"   Page: {driver.current_url[:60]}")
        log_task(task_id, f"   Height: {ph}px | <a> tags: {total_anchors} | content links: {content_links}")

        if content_links == 0 and ph < 1200:
            # Likely empty reels tab or private/restricted profile
            # Save screenshot so user can see what Chrome is rendering
            try:
                ss_path = os.path.join(APP_DIR, "debug_screenshot.png")
                driver.save_screenshot(ss_path)
                log_task(task_id, f"   Screenshot saved to {ss_path} — check what Chrome sees.")
            except Exception:
                pass
            log_task(task_id, "   ⚠️ No content links found. Profile may have no reels, or may be private/restricted.")

        log_task(task_id, f"   Scrolling @{username}...")
        return _scroll_and_collect(driver, link_type, max_items, task_id)
    except Exception as e:
        log_task(task_id, f"❌ Browser error: {type(e).__name__}: {e}")
        return []
    finally:
        driver.quit()

def fetch_reels_from_profile(username, max_reels=300, task_id=None):
    log_task(task_id, f"🚀 Fetching reels from @{username} (video posts only)...")
    return _instaloader_collect(username, max_reels, video_only=True, task_id=task_id)

def fetch_posts_from_profile(username, max_posts=300, task_id=None):
    log_task(task_id, f"🚀 Fetching all posts from @{username}...")
    return _instaloader_collect(username, max_posts, video_only=False, task_id=task_id)

# Matches both instagram.com/reel/CODE/ and instagram.com/USER/reel/CODE/ (new IG URL format)
_CONTENT_URL_RE = re.compile(r'instagram\.com/(?:[^/]+/)?(?:reel|p)/([A-Za-z0-9_\-]+)/')

def _scroll_and_collect(driver, link_type, max_items, task_id):
    links = set()
    no_new_count = 0
    # Instagram's grid can stall for a while before loading the next batch, so be
    # patient. Each empty round already costs ~6s of polling plus a nudge.
    NO_NEW_LIMIT = 15
    # Seed with actual page height so first nudge comparison is valid
    last_page_height = driver.execute_script("return document.body.scrollHeight")

    for scroll in range(500):
        # Collect both /reel/ and /p/ links — Instagram uses both URL formats for reels.
        # The page we're on (reels tab vs profile tab) already constrains what content is shown.
        anchors = driver.find_elements(
            By.XPATH,
            "//a[contains(@href, '/reel/') or contains(@href, '/p/')]"
        )
        old_count = len(links)
        for a in anchors:
            href = a.get_attribute("href") or ""
            if _CONTENT_URL_RE.search(href):
                links.add(href)
        new_found = len(links) - old_count

        if new_found > 0:
            no_new_count = 0
            log_task(task_id, f"   [{scroll+1}] Found {len(links)} (+{new_found})")
        else:
            no_new_count += 1
            log_task(task_id, f"   [{scroll+1}] No new ({no_new_count}/{NO_NEW_LIMIT})")
            if no_new_count >= NO_NEW_LIMIT:
                log_task(task_id, f"   Stopped: {NO_NEW_LIMIT} consecutive empty scrolls.")
                break

        if len(links) >= max_items:
            log_task(task_id, f"   Reached fetch limit ({max_items}).")
            break

        # Scroll to bottom then poll until page height grows (up to 6 s)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
        grew = False
        for _ in range(12):
            time.sleep(0.5)
            h = driver.execute_script("return document.body.scrollHeight")
            if h > last_page_height:
                last_page_height = h
                grew = True
                break

        if not grew:
            # Re-trigger IG's intersection observer. Repeating one identical action
            # that just failed is pointless, so rotate strategies and back off.
            strategy = no_new_count % 4
            log_task(task_id,
                     f"   [{scroll+1}] Height stuck at {last_page_height}px — nudge #{strategy + 1}...")
            if strategy == 0:
                driver.execute_script("window.scrollBy(0, -900)")
            elif strategy == 1:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.5)")
            elif strategy == 2:
                driver.execute_script("window.scrollTo(0, 0)")   # full reset
            else:
                for _ in range(3):                                # jitter near the bottom
                    driver.execute_script("window.scrollBy(0, -350)")
                    time.sleep(0.25)
                    driver.execute_script("window.scrollBy(0, 350)")
                    time.sleep(0.25)
            time.sleep(0.8)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(2.5 + min(no_new_count * 0.4, 4.0))       # back off as it drags on
            last_page_height = driver.execute_script("return document.body.scrollHeight")

    log_task(task_id, f"🎉 Total found: {len(links)}")
    return list(links)


# ═══════════════════════════════════════════════════════════════════════════════
# DOWNLOAD LOGIC
# ═══════════════════════════════════════════════════════════════════════════════
def download_task(task_id, urls, is_profile=False, max_reels=300, mode='reel'):
    target_username = "unknown"
    if not is_profile:
        get_logged_in_loader()
    if is_profile and len(urls) == 1:
        target_username = extract_username_from_profile(urls[0])
        if target_username:
            download_tasks[task_id]['username'] = target_username
            if mode == 'post':
                fetched = fetch_posts_from_profile(target_username, max_reels, task_id)
            else:
                fetched = fetch_reels_from_profile(target_username, max_reels, task_id)
            if not fetched:
                download_tasks[task_id]['state'] = 'completed'
                download_tasks[task_id]['results'] = []
                download_tasks[task_id]['completed_at'] = time.time()
                log_task(task_id, "❌ Failed to fetch any content.")
                return
            urls = fetched
            download_tasks[task_id]['fetched_count'] = len(urls)
            # Skip URLs we've already downloaded so the user can request "the rest"
            urls, skipped = _filter_known_urls(urls)
            download_tasks[task_id]['skipped_count'] = skipped
            if skipped:
                log_task(task_id, f"⏭  Skipped {skipped} already-downloaded items (in history).")
            if not urls:
                download_tasks[task_id]['state'] = 'completed'
                download_tasks[task_id]['results'] = []
                download_tasks[task_id]['total'] = 0
                download_tasks[task_id]['completed_at'] = time.time()
                log_task(task_id, "✅ Nothing new to download — everything is already in history.")
                return
            download_tasks[task_id]['total'] = len(urls)

    # Download phase — parallel workers, each with its own Instaloader context
    log_task(task_id, f"⬇️ Starting downloads ({mode} mode, {DOWNLOAD_WORKERS} workers)...")
    results = []
    total = len(urls)
    success_count = 0
    completed_count = 0
    save_dir = os.path.join(DOWNLOAD_FOLDER, target_username if target_username != "unknown" else "singles")

    with ThreadPoolExecutor(max_workers=DOWNLOAD_WORKERS) as executor:
        future_map = {
            executor.submit(_download_one, url, target_username, mode): url
            for url in urls
        }
        for future in as_completed(future_map):
            completed_count += 1
            download_tasks[task_id]['current'] = completed_count
            result = future.result()   # _download_one never raises — errors are in the dict
            results.append(result)
            if result['success']:
                success_count += 1
                log_task(task_id, f"✅ {completed_count}/{total}: {result['shortcode']}")
            else:
                log_task(task_id, f"❌ {completed_count}/{total}: {result.get('shortcode', '?')} — {result.get('error', '')}")

    download_tasks[task_id]['state'] = 'completed'
    download_tasks[task_id]['results'] = results
    download_tasks[task_id]['folder'] = save_dir
    download_tasks[task_id]['completed_at'] = time.time()
    log_task(task_id, f"🎉 Done! Downloaded {success_count}/{total}. Saved to: {save_dir}")


# ═══════════════════════════════════════════════════════════════════════════════
# BRANDING LOGIC (FONT + TEXT RENDERING + VIDEO COMPOSITING)
# ═══════════════════════════════════════════════════════════════════════════════
_FONT_CACHE = {}

# Clean, plain UI sans faces — no Impact/poster fonts. Regular for body text,
# semibold only where emphasis is wanted (names, initials).
_FONT_REGULAR = ["Inter-Regular.ttf", "segoeui.ttf", "arial.ttf",
                 "Helvetica.ttc", "DejaVuSans.ttf", "NotoSans-Regular.ttf"]
_FONT_BOLD = ["Inter-SemiBold.ttf", "seguisb.ttf", "segoeuib.ttf", "arialbd.ttf",
              "Helvetica-Bold.ttf", "DejaVuSans-Bold.ttf", "NotoSans-Bold.ttf"]


def _find_font(size=52, bold=False):
    """Load a simple sans-serif font at the given size, cached per (size, weight)."""
    key = (size, bold)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]

    search_dirs = [BUNDLE_DIR, APP_DIR, r"C:\Windows\Fonts",
                   "/usr/share/fonts", "/Library/Fonts", "/System/Library/Fonts"]
    font = None
    for name in (_FONT_BOLD if bold else _FONT_REGULAR):
        for d in search_dirs:
            path = os.path.join(d, name)
            if os.path.isfile(path):
                try:
                    font = ImageFont.truetype(path, size)
                    break
                except (OSError, IOError):
                    continue
        if font:
            break
        try:
            font = ImageFont.truetype(name, size)
            break
        except (OSError, IOError):
            continue

    if font is None:
        # load_default() ignores size on older Pillow, which renders microscopic text.
        try:
            font = ImageFont.load_default(size=size)
        except TypeError:
            font = ImageFont.load_default()

    _FONT_CACHE[key] = font
    return font


def _text_size(draw, text, font):
    """Actual rendered width/height and the y-offset needed to top-align it.
    font.size overestimates height (it ignores real ascender/descender), which
    is what throws vertical centering off."""
    if not text:
        return 0, 0, 0
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    return right - left, bottom - top, top


def _sanitize_text(text):
    """Remove emojis/characters outside the Basic Multilingual Plane that cause missing boxes."""
    if not text:
        return text
    return re.sub(r'[^\u0000-\uFFFF]', '', text)


def _clean_path(value):
    """Strip surrounding quotes/whitespace. Windows 'Copy as path' wraps paths in
    double quotes, which makes os.path.isfile fail."""
    if not value:
        return value
    return value.strip().strip('"').strip("'").strip()


def _contrast_text_color(rgb):
    """Pick black or white text for legibility on the given background color."""
    r, g, b = rgb[0], rgb[1], rgb[2]
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return (0, 0, 0) if luminance > 140 else (255, 255, 255)


def _render_text_image(text, cfg, profile_cfg=None):
    """
    Render Memezar-style profile header + optional caption text.
    profile_cfg keys: page_name, handle, logo_path, logo_color
    Returns numpy array (H, W, 3) and the actual bottom Y coordinate of the rendered content.
    """
    # Ensure cfg has all defaults
    full_cfg = BRAND_DEFAULTS.copy()
    if cfg: full_cfg.update(cfg)
    cfg = full_cfg

    text = _sanitize_text(text)
    width = cfg["target_width"]
    area_h = cfg["text_area_height"]
    margin = cfg["text_margin"]
    top_pad = cfg["text_top_padding"]
    font_size = cfg["font_size"]
    line_sp = cfg["line_spacing"]
    bg = tuple(cfg.get("bg_color", BRAND_DEFAULTS["bg_color"]))
    fg = tuple(cfg.get("text_color", BRAND_DEFAULTS["text_color"]))
    bg_path = _clean_path(cfg.get("bg_path"))
    usable_w = width - 2 * margin

    if bg_path and os.path.isfile(bg_path):
        try:
            bg_img = Image.open(bg_path).convert("RGB")
            # Resize and crop to fill (width, area_h)
            orig_bw, orig_bh = bg_img.size
            ratio = max(width / orig_bw, area_h / orig_bh)
            new_bw, new_bh = int(orig_bw * ratio), int(orig_bh * ratio)
            bg_img = bg_img.resize((new_bw, new_bh), Image.LANCZOS)
            # Crop center
            left = (new_bw - width) // 2
            top = (new_bh - area_h) // 2
            img = bg_img.crop((left, top, left + width, top + area_h))
        except Exception as e:
            print(f"⚠️ Error loading background image: {e}")
            img = Image.new("RGB", (width, area_h), bg)
    else:
        img = Image.new("RGB", (width, area_h), bg)

    draw = ImageDraw.Draw(img)
    y = top_pad

    # ── Profile Header (logo + name + @handle) ──
    if profile_cfg:
        page_name = profile_cfg.get("page_name", "")
        handle = profile_cfg.get("handle", "")
        logo_path = _clean_path(profile_cfg.get("logo_path", ""))
        logo_color = tuple(profile_cfg.get("logo_color", [220, 30, 30]))  # red default
        logo_size = 64

        # Draw logo (use uploaded image or colored circle placeholder)
        logo_x = margin
        logo_y = y
        if logo_path and os.path.isfile(logo_path):
            try:
                logo_img = Image.open(logo_path).resize((logo_size, logo_size), Image.LANCZOS)
                # Make it rounded
                mask = Image.new("L", (logo_size, logo_size), 0)
                mask_draw = ImageDraw.Draw(mask)
                mask_draw.rounded_rectangle([(0, 0), (logo_size, logo_size)], radius=12, fill=255)
                img.paste(logo_img, (logo_x, logo_y), mask)
            except:
                # Fallback: colored rounded rect
                draw.rounded_rectangle(
                    [(logo_x, logo_y), (logo_x + logo_size, logo_y + logo_size)],
                    radius=12, fill=logo_color
                )
        else:
            # Default: colored rounded rect with initials
            draw.rounded_rectangle(
                [(logo_x, logo_y), (logo_x + logo_size, logo_y + logo_size)],
                radius=12, fill=logo_color
            )
            if page_name:
                init_font = _find_font(24)
                initials = page_name[:2].upper()
                ibbox = draw.textbbox((0, 0), initials, font=init_font)
                iw, ih = ibbox[2] - ibbox[0], ibbox[3] - ibbox[1]
                draw.text(
                    (logo_x + (logo_size - iw) // 2, logo_y + (logo_size - ih) // 2),
                    initials, fill=_contrast_text_color(logo_color), font=init_font
                )

        # Page name (bold, next to logo)
        name_x = logo_x + logo_size + 18
        if page_name:
            name_font = _find_font(36)
            draw.text((name_x, logo_y + 4), page_name, fill=fg, font=name_font)
            # Verified badge (blue circle with checkmark)
            nbbox = draw.textbbox((0, 0), page_name, font=name_font)
            badge_x = name_x + (nbbox[2] - nbbox[0]) + 10
            badge_y = logo_y + 12
            badge_r = 12
            draw.ellipse(
                [(badge_x, badge_y), (badge_x + badge_r * 2, badge_y + badge_r * 2)],
                fill=(0, 149, 246)
            )
            # Checkmark
            check_font = _find_font(14)
            draw.text((badge_x + 5, badge_y + 3), "✓", fill=(255, 255, 255), font=check_font)

        # @handle (grey, below name)
        if handle:
            handle_font = _find_font(26)
            handle_text = handle if handle.startswith("@") else f"@{handle}"
            draw.text((name_x, logo_y + 40), handle_text, fill=(130, 130, 130), font=handle_font)

        y = logo_y + logo_size + 30  # Move below profile header

    # ── Caption Text ──
    if text and text.strip():
        caption_font_size = font_size
        while caption_font_size >= 28:
            font = _find_font(caption_font_size)
            chars_per_line = max(int(usable_w / (caption_font_size * 0.55)), 10)

            lines = []
            for paragraph in text.split("\n"):
                if not paragraph.strip():
                    lines.append("")
                    continue
                lines.extend(textwrap.wrap(paragraph, width=chars_per_line))

            line_h = caption_font_size + line_sp
            total_h = line_h * len(lines)
            if total_h <= (area_h - y - 20):
                break
            caption_font_size -= 4
        else:
            font = _find_font(28)
            chars_per_line = max(int(usable_w / (28 * 0.55)), 10)
            lines = []
            for paragraph in text.split("\n"):
                if not paragraph.strip():
                    lines.append("")
                    continue
                lines.extend(textwrap.wrap(paragraph, width=chars_per_line))
            line_h = 28 + line_sp

        for line in lines:
            if line:
                draw.text((margin, y), line, fill=fg, font=font)
            y += line_h

    # Return the image array AND the actual Y coordinate where content ends
    return np.array(img), y


def _render_profile_label(name, font_size=28):
    font = _find_font(font_size)
    tmp = Image.new("RGB", (1, 1))
    draw = ImageDraw.Draw(tmp)
    bbox = draw.textbbox((0, 0), name, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad = 12
    img = Image.new("RGB", (tw + 2 * pad, th + 2 * pad), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((pad, pad), name, fill=(50, 50, 50), font=font)
    return np.array(img)


# Removed _detect_content_box because we now use manual mask sliders


def _render_profile_footer(caption, cfg, profile_cfg):
    """Build the entire dark profile/caption panel once, never per video frame."""
    w, h = int(cfg["target_width"]), int(cfg["profile_footer_height"])
    if not 0 < h < int(cfg["target_height"]):
        raise ValueError("profile_footer_height must fit inside the frame")
    profile = profile_cfg or {}
    scale = max(.25, min(4., float(cfg.get("watermark_scale", 1) or 1)))
    margin = max(12, int(cfg.get("watermark_margin", 48)))
    margin = min(margin, w // 8)
    img = Image.new("RGBA", (w, h), tuple(cfg.get("bg_color", [15, 15, 18])) + (255,))
    d = ImageDraw.Draw(img)
    size = min(round(76 * scale), h - 32)
    y = 24
    color = tuple(profile.get("logo_color", [36, 36, 40]))
    logo = Image.new("RGBA", (size, size), color + (255,))
    logo_path = _clean_path(profile.get("logo_path", ""))
    if logo_path and os.path.isfile(logo_path):
        with Image.open(logo_path) as source:
            logo = ImageOps.fit(source.convert("RGBA"), (size, size), method=Image.Resampling.LANCZOS)
    else:
        ld = ImageDraw.Draw(logo)
        initial = (profile.get("page_name") or profile.get("handle") or "L").lstrip("@")[:1].upper()
        f = _find_font(max(12, size // 2), bold=True)
        box = ld.textbbox((0, 0), initial, font=f)
        ld.text(((size - (box[2]-box[0])) / 2 - box[0], (size - (box[3]-box[1])) / 2 - box[1]), initial, font=f, fill="white")
    mask = Image.new("L", (size, size))
    ImageDraw.Draw(mask).ellipse((0, 0, size-1, size-1), fill=255)
    img.paste(logo, (margin, y), mask)
    x = margin + size + 20
    name = _sanitize_text(profile.get("page_name") or profile.get("handle") or "")
    nf = _find_font(round(36 * scale), bold=True)
    while d.textlength(name, font=nf) > max(1, w - x - margin - 40) and len(name) > 1:
        name = name[:-2] + "?"
    d.text((x, y-2), name, font=nf, fill="white")
    bx = x + round(d.textlength(name, font=nf)) + 12
    if name and profile.get("verified", True):
        d.ellipse((bx, y+7, bx+26, y+33), fill=(29, 155, 240))
        d.line([(bx+6,y+20),(bx+11,y+25),(bx+21,y+14)], fill="white", width=3)
    handle = _sanitize_text(profile.get("handle", ""))
    if handle:
        hf = _find_font(round(28 * scale))
        handle = "@" + handle.lstrip("@")
        while d.textlength(handle, font=hf) > w-x-margin and len(handle) > 1:
            handle = handle[:-2] + "?"
        d.text((x, y+43), handle, font=hf, fill=(150, 150, 158))
    cy = y + size + 20
    cf = _find_font(min(int(cfg.get("font_size", 52)), 38))
    words = _sanitize_text(caption).split()
    lines, line = [], ""
    for word in words:
        candidate = (line + " " + word).strip()
        if line and d.textlength(candidate, font=cf) > w - 2*margin:
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    line_h = cf.size + min(14, int(cfg.get("line_spacing", 14)))
    count = max(0, (h - cy - 16) // line_h)
    for i, line in enumerate(lines[:count]):
        if i == count-1 and len(lines) > count:
            line += "?"
        while d.textlength(line, font=cf) > w-2*margin and len(line)>1:
            line = line[:-2] + "?"
        d.text((margin, cy+i*line_h), line, font=cf, fill=tuple(cfg.get("text_color", [255,255,255])))
    opacity = max(0., min(1., float(cfg.get("watermark_opacity", .92))))
    img.putalpha(round(255 * opacity))
    return img


def _source_framing(video_path):
    stat = os.stat(video_path)
    return _measure_source_framing(video_path, stat.st_size, stat.st_mtime_ns)


@lru_cache(maxsize=128)
def _measure_source_framing(video_path, file_size, modified_ns):
    """Measure embedded black canvas separately from caption and moving picture.

    Sample real source frames once per export, before scaling. A full-frame or
    ambiguous source stays intact; only a clear, wide picture between black
    outer bands is split. Temporal union keeps dark shots from shrinking it.
    """
    info = _source_video_info(video_path)
    sw, sh = info["size"]
    sample_w = min(360, sw)
    sample_h = round(sh * sample_w / sw) // 2 * 2
    rows = []
    for fraction in (.1, .5, .9):
        result = subprocess.run([
            _ffmpeg_exe(), "-v", "error", "-ss", str(info["duration"] * fraction),
            "-threads", "1", "-i", video_path, "-frames:v", "1", "-vf",
            f"scale={sample_w}:{sample_h},format=gray", "-threads", "1",
            "-f", "rawvideo", "pipe:1"], capture_output=True, check=True)
        if len(result.stdout) != sample_w * sample_h:
            return None
        gray = np.frombuffer(result.stdout, np.uint8).reshape(sample_h, sample_w)
        rows.append((gray > 32).mean(axis=1))
    activity = np.max(rows, axis=0)
    dense = activity > .55
    # Bridge short dark regions inside the footage, never the outer canvas.
    indices = np.flatnonzero(dense)
    if not len(indices):
        return None
    for left, right in zip(indices[:-1], indices[1:]):
        if right - left <= round(sample_h * .04):
            dense[left:right] = True
    edges = np.diff(np.r_[False, dense, False].astype(int))
    runs = list(zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)))
    top, bottom = max(runs, key=lambda pair: pair[1] - pair[0])
    if bottom-top < sample_h*.15 or top < sample_h*.02 or bottom > sample_h*.98:
        return None
    # Require truly black bottom canvas, not merely a dark part of a scene.
    if np.mean(activity[bottom+2:] > .02) > .05:
        return None
    ink = np.flatnonzero(activity[:top] > .015)
    caption_top = max(0, int(ink[0])-4) if len(ink) else top
    caption_bottom = min(top, int(ink[-1])+5) if len(ink) else top
    if len(ink) and caption_bottom == top:
        # A caption can straddle the picture boundary. Keep that entire line
        # at caption scale rather than changing its size halfway through it.
        text_rows = activity[:top] > .015
        transitions = np.diff(np.r_[False, text_rows, False].astype(int))
        starts = np.flatnonzero(transitions == 1)
        ends = np.flatnonzero(transitions == -1)
        complete = [end-start for start, end in zip(starts, ends) if end < top]
        line_height = max(complete, default=round(sample_h*.03))
        top = min(bottom-2, top + line_height + 4)
        caption_bottom = top
    def source_y(y):
        return round(y * sh / sample_h / 2) * 2
    return {"top": source_y(top), "bottom": source_y(bottom),
            "caption_top": source_y(caption_top),
            "caption_bottom": source_y(caption_bottom)}


def _composite_video_watermark(panel, cfg, frame_size, footage_rect, panel_y):
    """One static PNG and one FFmpeg overlay, including the existing profile row."""
    path = _clean_path(cfg.get("video_watermark_path", ""))
    position = cfg.get("video_watermark_position", "top-left")
    if not path or position == "off":
        return panel, panel_y
    if position not in {"top-left", "top-right", "bottom-left", "bottom-right"}:
        raise ValueError("video_watermark_position must be a corner or off")
    fraction = float(cfg.get("video_watermark_width_fraction", .22))
    opacity = float(cfg.get("video_watermark_opacity", .5))
    if not 0 < fraction <= 1 or not 0 <= opacity <= 1:
        raise ValueError("Watermark width fraction must be in (0,1], opacity in [0,1]")
    if os.path.basename(path).lower() == "alpha-mask.png":
        raise ValueError("alpha-mask.png is an editing mask, not a watermark")
    with Image.open(path) as source:
        mark = source.convert("RGBA")
        bounds = mark.getchannel("A").getbbox()
        if not bounds:
            raise ValueError("Watermark image is fully transparent")
        mark = mark.crop(bounds)
    x, y, width, height = footage_rect
    margin = min(round(frame_size[0] * .025), max(0, (min(width, height)-2)//2))
    available_w, available_h = width-2*margin, height-2*margin
    ratio = min(frame_size[0]*fraction/mark.width, available_w/mark.width, available_h/mark.height)
    mark = mark.resize((max(1, round(mark.width*ratio)), max(1, round(mark.height*ratio))), Image.Resampling.LANCZOS)
    mark.putalpha(mark.getchannel("A").point(lambda a: round(a*opacity)))
    mx = x+margin if position.endswith("left") else x+width-margin-mark.width
    my = y+margin if position.startswith("top") else y+height-margin-mark.height
    overlay = Image.new("RGBA", frame_size)
    overlay.alpha_composite(panel, (0, panel_y))
    # A subtle static dark edge keeps white lettering readable on light footage.
    # Clip the halo to the mark box so it cannot escape the footage rectangle.
    edge = mark.getchannel("A").filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(.6))
    shadow = Image.new("RGBA", mark.size, (0, 0, 0, 0))
    shadow.putalpha(edge)
    overlay.alpha_composite(shadow, (mx, my))
    overlay.alpha_composite(mark, (mx, my))
    bounds = overlay.getbbox()
    return overlay.crop((0, bounds[1], frame_size[0], bounds[3])), bounds[1]


def _branding_filter(video_path, cfg, caption, profile_cfg, mask_top, mask_bot, overlay_path):
    """The same FFmpeg graph is used for still previews and full exports.

    Separate embedded caption/canvas from footage before allocating the stack.
    Footage covers all space left by the caption and the unchanged profile row.
    Masks only paint pixels.
    """
    w, h = int(cfg["target_width"]), int(cfg["target_height"])
    if w < 2 or h < 2 or w % 2 or h % 2:
        raise ValueError("Target dimensions must be positive even numbers")
    header = cfg.get("style") == "header"
    panel = (Image.fromarray(_render_text_image(caption, cfg, profile_cfg)[0]).convert("RGBA")
             if header else _render_profile_footer(caption, cfg, profile_cfg))
    ph = panel.height
    if ph >= h:
        raise ValueError("Branding panel must fit inside the frame")
    top_pad = 0 if header else max(0, int(cfg.get("content_top_padding", 0) or 0))
    bottom_gap = 0 if header else max(0, int(cfg.get("content_bottom_gap", 0) or 0))
    top_pad -= top_pad % 2
    bottom_gap -= bottom_gap % 2
    if ph+top_pad+bottom_gap >= h:
        raise ValueError("Branding panel and gaps must fit inside the frame")
    area_h = h-ph-top_pad-bottom_gap
    account = os.path.basename(os.path.dirname(os.path.abspath(video_path))).lower()
    accounts = cfg.get("source_watermarks") or {}
    policy = accounts.get(account, cfg.get("source_watermark") or {})
    source_filters = []
    if policy.get("enabled", False):
        region = policy.get("region")
        if not isinstance(region, (list, tuple)) or len(region) != 4:
            raise ValueError("Source watermark region must be [x,y,width,height] in 0..1")
        x,y,rw,rh = map(float, region)
        if not (0 <= x < 1 and 0 <= y < 1 and 0 < rw <= 1-x and 0 < rh <= 1-y):
            raise ValueError("Source watermark region must be inside the source")
        if policy.get("mode", "cover") == "crop":
            # Crop a configured edge strip, then let the normal geometry fit it.
            edge = policy.get("edge", "top")
            crops = {"top": f"crop=iw:ih*(1-{y+rh}):0:ih*{y+rh}",
                     "bottom": f"crop=iw:ih*{y}:0:0",
                     "left": f"crop=iw*(1-{x+rw}):ih:iw*{x+rw}:0",
                     "right": f"crop=iw*{x}:ih:0:0"}
            if edge not in crops:
                raise ValueError("Watermark crop edge must be top/bottom/left/right")
            source_filters.append(crops[edge])
        else:
            source_filters.append(f"drawbox=x=iw*{x}:y=ih*{y}:w=iw*{rw}:h=ih*{rh}:color=black:t=fill")
    source_filters.append("setsar=1")
    graph = ["[0:v]" + ",".join(source_filters) + "[source]"]
    zoom = max(1., float(cfg.get("zoom_factor", 1) or 1))
    framing = _source_framing(video_path) if not policy.get("enabled", False) else None
    caption_h = 0
    if framing:
        ct, cb = framing["caption_top"], framing["caption_bottom"]
        sw = _source_video_info(video_path)["size"][0]
        caption_h = round((cb-ct) * w / sw / 2) * 2
        if caption_h >= area_h-2:
            raise ValueError("Embedded caption leaves no room for footage")
        if caption_h:
            graph += ["[source]split[caption_src][picture_src]",
                      f"[caption_src]crop=iw:{cb-ct}:0:{ct},scale={w}:{caption_h}:flags=lanczos[caption]"]
            source_label = "picture_src"
        else:
            source_label = "source"
        graph.append(f"[{source_label}]crop=iw:{framing['bottom']-framing['top']}:0:{framing['top']}[picture]")
        base_label = "picture"
    else:
        base_label = "source"
    picture_h = area_h-caption_h
    zw, zh = int(w*zoom)//2*2, int(picture_h*zoom)//2*2
    geometry = (f"scale={w}:{picture_h}:force_original_aspect_ratio=increase:flags=lanczos,"
                f"crop={w}:{picture_h}:(iw-ow)/2:0")
    if zoom > 1:
        geometry += f",scale={zw}:{zh}:flags=lanczos,crop={w}:{picture_h}"
    sharp = max(0., min(5., float(cfg.get("upscale_sharpen", 1.25))))
    if sharp:
        geometry += f",unsharp=3:3:{sharp}:3:3:0"
    for fraction, bottom in [(mask_top, False), (mask_bot, True)]:
        pixels = round(picture_h * max(0., min(45., float(fraction))) / 100)
        if pixels:
            geometry += f",drawbox=x=0:y={picture_h-pixels if bottom else 0}:w=iw:h={pixels}:color=black:t=fill"
    graph.append(f"[{base_label}]" + geometry + "[framed]")
    if caption_h:
        graph.append("[caption][framed]vstack=inputs=2[stack]")
        stack_label = "stack"
    else:
        stack_label = "framed"
    content_y = ph if header else top_pad
    graph.append(f"[{stack_label}]pad={w}:{h}:0:{content_y}:color=black[base]")
    panel, overlay_y = _composite_video_watermark(
        panel, cfg, (w, h), (0, content_y+caption_h, w, picture_h),
        0 if header else h-ph)
    panel.save(overlay_path)
    graph.append(f"[base][1:v]overlay=0:{overlay_y}:format=auto,format=yuv420p[out]")
    return ";".join(graph)


def _source_video_info(video_path):
    stat = os.stat(video_path)
    return _read_source_info(video_path, stat.st_size, stat.st_mtime_ns)


@lru_cache(maxsize=128)
def _read_source_info(video_path, file_size, modified_ns):
    import imageio_ffmpeg
    reader = imageio_ffmpeg.read_frames(video_path, input_params=["-threads", "1"])
    try:
        return next(reader)
    finally:
        reader.close()


def _run_brand_ffmpeg(video_path, output_path, caption, cfg, profile_cfg, mask_top=0, mask_bot=0, preview=False, quick=False):
    with BRAND_RENDER_SLOTS:
        return _encode_brand(video_path, output_path, caption, cfg, profile_cfg, mask_top, mask_bot, preview, quick)


def _encode_brand(video_path, output_path, caption, cfg, profile_cfg, mask_top, mask_bot, preview=False, quick=False):
    cfg, profile_cfg = _resolve_brand_preset(cfg, profile_cfg)
    cfg = {**BRAND_DEFAULTS, **cfg}
    if preview and not quick:
        # Decode the actual delivery encode: pre-encode PNGs cannot be pixel
        # identical to a CRF export. Encode the full stream so GOP/lookahead and
        # rate control match export, including frames after the preview stamp.
        with tempfile.TemporaryDirectory(prefix="reel-preview-encode-") as tmp:
            encoded = os.path.join(tmp, "delivery.mp4")
            _encode_brand(video_path, encoded, caption, cfg, profile_cfg, mask_top, mask_bot)
            stamp = min(1., _source_video_info(video_path)["duration"] / 2)
            subprocess.run([_ffmpeg_exe(), "-y", "-v", "error", "-threads", "1", "-i", encoded,
                            "-ss", str(stamp), "-frames:v", "1", "-threads", "1",
                            output_path], check=True, capture_output=True)
        return output_path
    with tempfile.TemporaryDirectory(prefix="reel-brand-") as tmp:
        overlay = os.path.join(tmp, "branding.png")
        graph = _branding_filter(video_path, cfg, caption, profile_cfg, mask_top, mask_bot, overlay)
        cmd = [_ffmpeg_exe(), "-y", "-v", "error", "-filter_complex_threads", "1"]
        if preview:
            stamp = min(1., _source_video_info(video_path)["duration"] / 2)
            cmd += ["-ss", str(stamp)]
        cmd += ["-threads", str(BRAND_THREADS), "-i", video_path, "-threads", "1", "-i", overlay]
        if preview:
            graph += ";[out]scale='min(540,iw)':-2[still]"
            subprocess.run(cmd + ["-filter_complex", graph, "-map", "[still]", "-frames:v", "1",
                                  "-threads", "1", output_path], check=True, capture_output=True)
            return output_path
        cmd += ["-filter_complex", graph, "-map", "[out]"]
        cmd += ["-map", "0:a?", "-c:v", "libx264", "-preset", BRAND_PRESET,
                # Delivery quality: crisp text without lossless upload sizes.
                "-crf", "22", "-pix_fmt", "yuv420p", "-threads", str(BRAND_THREADS),
                "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart"]
        pitch = float(cfg.get("audio_pitch", 1) or 1)
        if abs(pitch-1) >= .001:
            if not .5 <= pitch <= 2:
                raise ValueError("audio_pitch must be between 0.5 and 2")
            cmd += ["-af", f"aresample=44100,asetrate=44100*{pitch},aresample=44100,atempo={1/pitch}"]
        cmd.append(output_path)
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode:
            raise RuntimeError(result.stderr.decode("utf-8", "replace")[-4000:])
    return output_path


def _job_brand_config(video_path, cfg):
    resolved, _ = _resolve_brand_preset(cfg)
    merged = {**BRAND_DEFAULTS, **resolved}
    if merged.get("randomize_variation"):
        # Stable per source/config so preview and render choose the same variation.
        rng = random.Random(os.path.abspath(video_path) + json.dumps(merged, sort_keys=True))
        merged["audio_pitch"] = rng.uniform(*merged["pitch_range"])
        merged["zoom_factor"] = rng.uniform(*merged["zoom_range"])
        merged["randomize_variation"] = False
    return merged


def generate_preview_image(video_path, caption, cfg=None, profile_cfg=None, mask_top=0, mask_bot=0, quick=False):
    """Return a delivery-encoded still, or a single composited frame for the editor."""
    cfg = _job_brand_config(video_path, cfg)
    with tempfile.TemporaryDirectory(prefix="reel-preview-") as tmp:
        path = os.path.join(tmp, "preview.png")
        _run_brand_ffmpeg(video_path, path, caption, cfg, profile_cfg, mask_top, mask_bot, preview=True, quick=quick)
        with open(path, "rb") as image:
            return base64.b64encode(image.read()).decode("utf-8")


def _apply_pitch(path, pitch, task_id=None):
    """Shift the audio pitch of an already-written file, in place.

    Done as a second pass because moviepy stream-copies audio when muxing, and
    ffmpeg refuses to combine a filtergraph with codec copy. Only the audio is
    re-encoded (-c:v copy), so this is fast and doesn't touch video quality.
    asetrate shifts pitch+tempo; atempo puts the tempo back so duration holds.
    """
    if not pitch or abs(float(pitch) - 1.0) < 0.001:
        return
    pitch = float(pitch)
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
        ffmpeg = get_ffmpeg_exe()
    except Exception:
        ffmpeg = "ffmpeg"

    tmp = path + ".pitch.mp4"
    af = f"asetrate=44100*{pitch:.4f},aresample=44100,atempo={1.0 / pitch:.4f}"
    cmd = [ffmpeg, "-y", "-loglevel", "error", "-i", path,
           "-c:v", "copy", "-af", af, "-c:a", "aac", "-b:a", "128k", tmp]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        os.replace(tmp, path)
    except Exception as e:
        # Keep the un-pitched render rather than losing the whole video.
        detail = getattr(e, "stderr", b"")
        if isinstance(detail, bytes):
            detail = detail.decode("utf-8", "replace").strip().splitlines()[-1:] or [""]
            detail = detail[0]
        log_task(task_id, f"   ⚠️ Pitch shift failed, keeping original audio: {detail}", brand_tasks)
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _resolve_variation(cfg):
    """Return (pitch, zoom) for this video, randomised per-video when asked."""
    if cfg.get("randomize_variation"):
        p_lo, p_hi = cfg.get("pitch_range", [0.93, 1.08])
        z_lo, z_hi = cfg.get("zoom_range", [1.0, 1.05])
        return random.uniform(p_lo, p_hi), random.uniform(z_lo, z_hi)
    return float(cfg.get("audio_pitch", 1.0) or 1.0), float(cfg.get("zoom_factor", 1.0) or 1.0)


def _brand_watermark_style(clip, cfg, profile_cfg, output_path, task_id, duration, fps):
    return _write_branded_clip(clip, "", cfg, profile_cfg, output_path, task_id)


def _write_branded_clip(clip, caption, cfg, profile_cfg, output_path, task_id, mask_top=0, mask_bot=0):
    # Compatibility wrapper for callers using the old MoviePy entry point.
    path = clip.filename
    clip.close()
    return _run_brand_ffmpeg(path, output_path, caption, cfg, profile_cfg, mask_top, mask_bot)


def _ffmpeg_exe():
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
        return get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def brand_single_video(video_path, caption, cfg=None, profile_cfg=None, output_path=None, task_id=None, mask_top=0, mask_bot=0, output_folder=None):
    """Render both styles using exactly the same pixels as the preview."""
    cfg = _job_brand_config(video_path, cfg)
    if output_path is None:
        dest = output_folder or BRANDED_FOLDER
        os.makedirs(dest, exist_ok=True)
        base = os.path.splitext(os.path.basename(video_path))[0]
        output_path = os.path.join(dest, f"{base}_branded.mp4")
    log_task(task_id, f"Rendering: {os.path.basename(output_path)}", brand_tasks)
    # Keep unfinished renders out of the upload list and preserve earlier exports on failure.
    with tempfile.TemporaryDirectory(dir=os.path.dirname(os.path.abspath(output_path))) as scratch:
        pending = os.path.join(scratch, os.path.basename(output_path))
        _run_brand_ffmpeg(video_path, pending, caption, cfg, profile_cfg, mask_top, mask_bot)
        os.replace(pending, output_path)
    return output_path


def brand_task_runner(task_id, videos, caption, cfg, profile_cfg, mask_top=0, mask_bot=0, output_folder=None):
    """Background branding task. Renders BRAND_WORKERS videos concurrently."""
    results = []
    total = len(videos)
    done = 0
    lock = threading.Lock()

    def render(vpath):
        try:
            out = brand_single_video(vpath, caption, cfg, profile_cfg=profile_cfg,
                                     task_id=task_id, mask_top=mask_top, mask_bot=mask_bot,
                                     output_folder=output_folder)
            return {'file': os.path.basename(vpath), 'output': out, 'success': True}
        except Exception as e:
            log_task(task_id, f"❌ Error: {os.path.basename(vpath)}: {e}", brand_tasks)
            return {'file': os.path.basename(vpath), 'success': False, 'error': str(e)}

    log_task(task_id,
             f"🎬 Rendering {total} videos · {BRAND_WORKERS} workers · "
             f"preset={BRAND_PRESET} · {BRAND_THREADS} threads each", brand_tasks)

    with ThreadPoolExecutor(max_workers=max(1, BRAND_WORKERS)) as pool:
        for result in pool.map(render, videos):
            with lock:
                done += 1
                brand_tasks[task_id]['current'] = done
            results.append(result)

    brand_tasks[task_id]['state'] = 'completed'
    brand_tasks[task_id]['results'] = results
    brand_tasks[task_id]['completed_at'] = time.time()
    success = sum(1 for r in results if r['success'])
    log_task(task_id, f"🎉 Branded {success}/{total} videos!", brand_tasks)


@app.route('/api/health')
def health():
    return jsonify({
        'service': 'Reel Studio backend',
        'status': 'ok',
        'ui_built': os.path.isfile(os.path.join(FRONTEND_DIR, 'index.html')),
    })


@app.route('/')
def index():
    """Serve the built UI."""
    if os.path.isfile(os.path.join(FRONTEND_DIR, 'index.html')):
        return send_from_directory(FRONTEND_DIR, 'index.html')
    return (
        "<h2>Interface not built yet</h2>"
        "<p>Run <code>npm run build</code> inside <code>frontend/</code>, "
        "or just launch the app with <code>Reel Studio.bat</code>.</p>",
        503,
    )


@app.route('/<path:asset>')
def frontend_asset(asset):
    """Serve the exported UI's static files (/_next/..., favicon, etc.).

    Declared last and guarded so it can never shadow an /api/ route.
    """
    if asset.startswith('api/'):
        return jsonify({'error': 'Unknown API endpoint'}), 404
    candidate = os.path.join(FRONTEND_DIR, asset)
    if os.path.isfile(candidate):
        return send_from_directory(FRONTEND_DIR, asset)
    if os.path.isfile(os.path.join(FRONTEND_DIR, '404.html')):
        return send_from_directory(FRONTEND_DIR, '404.html'), 404
    return jsonify({'error': 'Not found'}), 404

@app.route('/api/download', methods=['POST'])
def start_download():
    data = request.get_json(silent=True) or {}
    urls = data.get('urls', [])
    mode = data.get('mode', 'reel')
    if mode not in ('reel', 'post'):
        return jsonify({'error': "mode must be 'reel' or 'post'"}), 400

    # Validate here — an unusable value otherwise surfaces as a cryptic worker
    # error minutes later, after Chrome has already launched and logged in.
    try:
        max_reels = int(data.get('maxReels', 300))
    except (TypeError, ValueError):
        return jsonify({'error': 'maxReels must be a whole number'}), 400
    if not 1 <= max_reels <= 5000:
        return jsonify({'error': 'maxReels must be between 1 and 5000'}), 400

    if not isinstance(urls, list):
        return jsonify({'error': 'urls must be a list'}), 400
    clean_urls = [u.strip() for u in urls if isinstance(u, str) and u.strip()]
    if not clean_urls:
        return jsonify({'error': 'No URLs provided'}), 400
    is_profile = len(clean_urls) == 1 and is_profile_url(clean_urls[0])
    _prune_tasks(download_tasks)
    task_id = str(uuid.uuid4())[:8]
    download_tasks[task_id] = {
        'id': task_id, 'total': 0, 'current': 0, 'state': 'processing',
        'status': 'Starting...', 'logs': [], 'mode': mode,
        'folder': '', 'results': [], 'created_at': time.time()
    }
    thread = threading.Thread(target=download_task, args=(task_id, clean_urls, is_profile, max_reels, mode))
    thread.daemon = True
    thread.start()
    return jsonify({'task_id': task_id, 'message': 'Started'})

@app.route('/api/download/<task_id>', methods=['GET'])
def get_download_status(task_id):
    if task_id not in download_tasks:
        return jsonify({'error': 'Task not found'}), 404
    return jsonify(download_tasks[task_id])

def _cleanup_empty_dirs(root_dir):
    for current_root, dirnames, filenames in os.walk(root_dir, topdown=False):
        if current_root == root_dir:
            continue
        if dirnames or filenames:
            continue
        try:
            os.rmdir(current_root)
        except OSError:
            pass


def delete_managed_videos():
    deleted_files = []
    skipped_files = []

    for folder in MANAGED_VIDEO_FOLDERS:
        if not os.path.isdir(folder):
            continue

        for root, _, filenames in os.walk(folder):
            for filename in filenames:
                ext = os.path.splitext(filename)[1].lower()
                if ext not in VIDEO_EXTENSIONS:
                    continue

                full_path = os.path.join(root, filename)
                try:
                    os.remove(full_path)
                    deleted_files.append(full_path.replace('\\', '/'))
                except OSError as exc:
                    skipped_files.append({
                        'path': full_path.replace('\\', '/'),
                        'error': str(exc)
                    })

        _cleanup_empty_dirs(folder)

    return {
        'deleted_count': len(deleted_files),
        'deleted_files': deleted_files,
        'skipped_count': len(skipped_files),
        'skipped_files': skipped_files,
        'folders': MANAGED_VIDEO_FOLDERS,
    }


@app.route('/api/videos/delete-all', methods=['POST'])
def delete_all_videos():
    result = delete_managed_videos()
    # Also wipe the download history so subsequent runs treat everything as fresh.
    _clear_history()
    result['history_cleared'] = True
    return jsonify(result)


@app.route('/api/history', methods=['GET'])
def get_history():
    """Return the current download history."""
    with HISTORY_LOCK:
        history = _load_history()
    entries = history.get("entries", {})
    return jsonify({
        'count': len(entries),
        'entries': entries,
    })


@app.route('/api/history/clear', methods=['POST'])
def clear_history():
    """Clear the download history (videos themselves are untouched)."""
    _clear_history()
    return jsonify({'cleared': True})


@app.route('/api/cleanup/low-views', methods=['POST'])
def start_low_view_cleanup():
    """Delete downloaded reels below a view-count threshold."""
    data = request.get_json(silent=True) or {}
    try:
        min_views = int(data.get('minViews', 1000))
    except (TypeError, ValueError):
        return jsonify({'error': 'minViews must be a number'}), 400
    if min_views < 0:
        return jsonify({'error': 'minViews must be >= 0'}), 400
    dry_run = bool(data.get('dryRun', False))

    _prune_tasks(cleanup_tasks)
    task_id = str(uuid.uuid4())[:8]
    cleanup_tasks[task_id] = {
        'id': task_id, 'total': 0, 'current': 0, 'state': 'processing',
        'status': 'Starting cleanup...', 'logs': [], 'deleted': [],
        'min_views': min_views, 'dry_run': dry_run, 'created_at': time.time(),
    }
    thread = threading.Thread(target=cleanup_low_views_runner, args=(task_id, min_views, dry_run))
    thread.daemon = True
    thread.start()
    return jsonify({'task_id': task_id, 'min_views': min_views, 'dry_run': dry_run})


@app.route('/api/cleanup/<task_id>', methods=['GET'])
def get_cleanup_status(task_id):
    if task_id not in cleanup_tasks:
        return jsonify({'error': 'Task not found'}), 404
    return jsonify(cleanup_tasks[task_id])

# --- File Browser APIs ---
IMPORT_FOLDER = os.path.join(DOWNLOAD_FOLDER, 'Imports')
MAX_IMPORT_BYTES = 512 * 1024 * 1024
LOCAL_HOSTS = {'127.0.0.1', '::1', 'localhost'}


@app.route('/api/library/import', methods=['POST'])
def import_local_clip():
    """Stream one clip to the local library and publish it only after the copy finishes."""
    origin = request.headers.get('Origin')
    try:
        local_request = (request.remote_addr in LOCAL_HOSTS and
                         urlsplit(request.host_url).hostname in LOCAL_HOSTS and
                         (not origin or urlsplit(origin).hostname in LOCAL_HOSTS))
    except ValueError:
        local_request = False
    if not local_request:
        return jsonify(error='Open Reel Studio on this PC to import clips.'), 403

    source_name = request.args.get('name', '')
    stem, ext = os.path.splitext(source_name)
    if ext.lower() != '.mp4' or request.mimetype != 'video/mp4':
        return jsonify(error='Choose an MP4 video.'), 415
    length = request.content_length
    if length is None:
        return jsonify(error='The file size is required.'), 411
    if length > MAX_IMPORT_BYTES:
        return jsonify(error='Choose an MP4 of 512 MiB or less.'), 413
    if length < 16:
        return jsonify(error='This file is too short to be an MP4.'), 422

    temp_path = None
    try:
        stream = request.stream
        header = stream.read(16)
        box_size = int.from_bytes(header[:4], 'big')
        if header[4:8] != b'ftyp' or not 16 <= box_size <= length:
            return jsonify(error='This file lacks a valid MP4 file-type header.'), 422
        os.makedirs(IMPORT_FOLDER, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=IMPORT_FOLDER, suffix='.part', delete=False) as out:
            temp_path = out.name
            out.write(header)
            remaining = length - len(header)
            while remaining:
                chunk = stream.read(min(256 * 1024, remaining))
                if not chunk:
                    return jsonify(error='Upload interrupted. Select the clip again.'), 400
                out.write(chunk)
                remaining -= len(chunk)

        # The suffix also keeps branding outputs distinct for clips with matching titles.
        title = secure_filename(stem)[:80] or 'clip'
        filename = f'{title}-{uuid.uuid4().hex[:12]}.mp4'
        final_path = os.path.join(IMPORT_FOLDER, filename)
        os.replace(temp_path, final_path)
        temp_path = None
    except ClientDisconnected:
        return jsonify(error='Upload interrupted. Select the clip again.'), 400
    except OSError:
        app.logger.exception('Could not save the imported clip')
        return jsonify(error='Could not save the clip. Check free disk space and folder access.'), 500
    finally:
        if temp_path is not None:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass

    return jsonify(name=filename, path=final_path.replace('\\', '/'),
                   rel_path=f'Imports/{filename}', size_mb=round(length / 1048576, 2),
                   folder='Imports'), 201


@app.route('/api/files', methods=['GET'])
def list_video_files():
    """List all downloaded video files available for branding."""
    files = []
    for root, dirs, filenames in os.walk(DOWNLOAD_FOLDER):
        for f in sorted(filenames):
            ext = os.path.splitext(f)[1].lower()
            if ext in VIDEO_EXTENSIONS and (root == IMPORT_FOLDER or '_branded' not in f):
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, DOWNLOAD_FOLDER)
                size_mb = os.path.getsize(full_path) / (1024 * 1024)
                files.append({
                    'name': f,
                    'path': full_path.replace('\\', '/'),
                    'rel_path': rel_path.replace('\\', '/'),
                    'size_mb': round(size_mb, 2),
                    'folder': os.path.basename(root) if root != DOWNLOAD_FOLDER else ''
                })
    return jsonify({'files': files, 'base_folder': DOWNLOAD_FOLDER})

@app.route('/api/branded-files', methods=['GET'])
def list_branded_files():
    """List all branded output videos. Optional ?folder= to scan a custom directory."""
    folder = _clean_path(request.args.get('folder', '')) or BRANDED_FOLDER
    if not os.path.isdir(folder):
        return jsonify({'files': [], 'folder': folder, 'playable': False})
    # Files outside the allowlist still list, but can't stream — say so rather
    # than letting the player fail with a silent 404.
    playable = _is_allowed_video_root(folder)
    files = []
    for f in sorted(os.listdir(folder)):
        ext = os.path.splitext(f)[1].lower()
        if ext in VIDEO_EXTENSIONS:
            full_path = os.path.join(folder, f)
            try:
                stat = os.stat(full_path)
            except FileNotFoundError:
                continue
            files.append({
                'name': f,
                'path': full_path.replace('\\', '/'),
                'size_mb': round(stat.st_size / (1024 * 1024), 2),
                'modified': stat.st_mtime
            })
    return jsonify({
        'files': files,
        'folder': folder,
        'playable': playable,
        'note': None if playable else (
            'Videos here are listed but cannot be played in the browser. Add this '
            'folder to EXTRA_VIDEO_ROOTS in your .env and restart the backend.'
        ),
    })

@app.route('/api/brand/presets', methods=['GET'])
def list_brand_presets():
    return jsonify({'presets': [dict(id=name, **preset) for name, preset in BRAND_PRESETS.items()]})


@app.route('/api/brand/preview', methods=['POST'])
def brand_preview():
    """Generate a static preview image of the branded video."""
    data = request.get_json(silent=True) or {}
    video_path = data.get('videoPath', '')
    caption = data.get('caption', '')
    profile_cfg = data.get('profileConfig', None)
    try:
        cfg, profile_cfg = _resolve_brand_preset(data.get('config'), profile_cfg)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    mask_top = data.get('maskTop', 0)
    mask_bot = data.get('maskBot', 0)

    if not video_path or not os.path.isfile(video_path):
        return jsonify({'error': f'Video not found: {video_path}'}), 400

    # Non-blocking so you can still iterate, but say so instead of silently
    # falling back to an initials chip.
    warning = None
    logo = _clean_path((profile_cfg or {}).get('logo_path', ''))
    if logo and not os.path.isfile(logo):
        warning = f'Logo file not found: {logo}'

    try:
        b64 = generate_preview_image(video_path, caption, cfg, profile_cfg, mask_top, mask_bot, quick=data.get("quick") is True)
        return jsonify({'preview': b64, 'warning': warning})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/brand/start', methods=['POST'])
def start_branding():
    """Start branding one or more videos."""
    data = request.get_json(silent=True) or {}
    video_paths = data.get('videoPaths', [])
    caption = data.get('caption', '')
    profile_cfg = data.get('profileConfig', None)
    try:
        cfg, profile_cfg = _resolve_brand_preset(data.get('config'), profile_cfg)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    mask_top = data.get('maskTop', 0)
    mask_bot = data.get('maskBot', 0)
    output_folder = _clean_path(data.get('outputFolder', '')) or None

    if not video_paths:
        return jsonify({'error': 'No videos selected'}), 400

    # Validate / create the output folder early so we fail fast before rendering
    if output_folder:
        try:
            os.makedirs(output_folder, exist_ok=True)
        except Exception as e:
            return jsonify({'error': f'Cannot create output folder: {e}'}), 400
        if not os.access(output_folder, os.W_OK):
            return jsonify({'error': f'Output folder is not writable: {output_folder}'}), 400

    # Validate all source paths
    valid = [p for p in video_paths if os.path.isfile(p)]
    if not valid:
        return jsonify({'error': 'None of the video paths exist'}), 400

    # Fail loudly on a bad logo path — otherwise branding silently falls back to
    # an initials chip and you only notice after the whole batch has rendered.
    logo = _clean_path((profile_cfg or {}).get('logo_path', ''))
    if logo and not os.path.isfile(logo):
        return jsonify({'error': f'Logo file not found: {logo}'}), 400

    _prune_tasks(brand_tasks)
    task_id = str(uuid.uuid4())[:8]
    brand_tasks[task_id] = {
        'id': task_id, 'total': len(valid), 'current': 0, 'state': 'processing',
        'status': 'Starting branding...', 'logs': [], 'results': [],
        'output_folder': output_folder or BRANDED_FOLDER,
        'created_at': time.time()
    }

    thread = threading.Thread(target=brand_task_runner, args=(task_id, valid, caption, cfg, profile_cfg, mask_top, mask_bot, output_folder))
    thread.daemon = True
    thread.start()
    return jsonify({'task_id': task_id, 'message': 'Branding started', 'output_folder': output_folder or BRANDED_FOLDER})

@app.route('/api/brand/<task_id>', methods=['GET'])
def get_brand_status(task_id):
    if task_id not in brand_tasks:
        return jsonify({'error': 'Task not found'}), 404
    return jsonify(brand_tasks[task_id])

# --- Serve video files for preview playback ---
@app.route('/api/video/<path:filepath>')
def serve_video(filepath):
    """Serve a video file for in-browser playback (managed folders only)."""
    # filepath comes URL-encoded, decode it
    full_path = filepath.replace('/', os.sep)
    if not os.path.isfile(full_path):
        return "Not found", 404
    if not _is_allowed_video_path(full_path):
        # Don't confirm existence of files outside the allowlist.
        return "Not found", 404
    directory = os.path.dirname(full_path)
    filename = os.path.basename(full_path)
    mimetype = mimetypes.guess_type(filename)[0] or 'video/mp4'
    return send_from_directory(directory, filename, mimetype=mimetype,
                               as_attachment=request.args.get('download') == '1')


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    print("Starting Instagram Reel Downloader + Branding Studio...")
    # Bind to localhost by default. The old 0.0.0.0 + debug=True combination
    # exposed the Werkzeug debug console (code execution) to the whole LAN.
    # Override deliberately with HOST/PORT/FLASK_DEBUG if you need remote access.
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "").lower() in ("1", "true", "yes")
    url = f"http://{'127.0.0.1' if host in ('0.0.0.0', '') else host}:{port}"

    if not os.path.isfile(os.path.join(FRONTEND_DIR, 'index.html')):
        print("NOTE: UI not built yet — run `npm run build` in frontend/ "
              "(the launcher does this for you).")

    # The packaged .exe is a double-clicked app, so it opens the UI by itself.
    # Running from source stays opt-in (the .bat launcher sets OPEN_BROWSER=1).
    open_default = "1" if getattr(sys, 'frozen', False) else ""
    if os.getenv("OPEN_BROWSER", open_default).lower() in ("1", "true", "yes"):
        import webbrowser
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    print(f"\n  Reel Studio is running at  {url}\n  (press Ctrl+C to stop)\n")
    app.run(host=host, port=port, debug=debug, use_reloader=False)
