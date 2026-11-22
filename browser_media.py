"""Browser-backed Instagram media fetching.

Instagram's graphql API returns 401 and redirects to the homepage for every
session, so Instaloader can no longer fetch media. A logged-in browser still
works, so everything here drives SeleniumBase UC mode instead:

  * profile pages are scrolled to collect post/reel links
  * a post's image is read straight from the DOM at full resolution
  * playing a reel makes Chrome request its DASH tracks, which appear in the
    performance timeline; each request is a byte range, so stripping
    `bytestart`/`byteend` yields the whole track, and video and audio tracks
    are muxed back together with ffmpeg

This module deliberately takes the driver factory and cookies as arguments so
it can be imported by both the Flask app and the standalone scripts without a
circular import.
"""
import json
import os
import subprocess
import tempfile
import time
from urllib.parse import urlencode, urlparse, parse_qs, urlunparse

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")

TRACK_MARKER = "/o1/v/t2/"

# Instagram renders the post at 1440px wide and the "suggested posts" strip
# below it at 640px tall, so a 700px floor separates them cleanly.
MIN_IMAGE_EDGE = 700

PICK_IMAGES = """
const root = document.querySelector('article') || document;
return Array.from(root.querySelectorAll('img')).map(img => ({
  url: img.currentSrc || img.src || '',
  width: img.naturalWidth || 0,
  height: img.naturalHeight || 0,
  alt: img.alt || ''
})).filter(i => i.url && i.url.indexOf('blob:') !== 0);
"""


def cookie_dicts(loader):
    """Browser-shaped cookies from an authenticated Instaloader session."""
    return [{"name": c.name, "value": c.value, "domain": ".instagram.com",
             "path": "/", "secure": True} for c in loader.context._session.cookies]


def sign_in(driver, cookies):
    """Load instagram.com, inject the session cookies, confirm we are logged in."""
    driver.get("https://www.instagram.com/")
    time.sleep(3)
    for cookie in cookies:
        try:
            driver.add_cookie(cookie)
        except Exception:
            pass
    driver.get("https://www.instagram.com/")
    time.sleep(4)
    return not driver.execute_script(
        "return !!document.querySelector('input[name=username]')")


def collect_links(driver, username, want, kind="post"):
    """Scroll a profile and collect post or reel permalinks."""
    if kind == "reel":
        driver.get("https://www.instagram.com/%s/reels/" % username)
        selector = 'a[href*="/reel/"]'
    else:
        driver.get("https://www.instagram.com/%s/" % username)
        selector = 'a[href*="/p/"]'
    time.sleep(6)
    links = []
    stale = 0
    while len(links) < want and stale < 12:
        found = driver.execute_script(
            "return Array.from(document.querySelectorAll('%s')).map(a=>a.href)" % selector) or []
        before = len(links)
        for href in found:
            clean = href.split("?")[0]
            if clean not in links:
                links.append(clean)
        stale = 0 if len(links) > before else stale + 1
        driver.execute_script("window.scrollBy(0, document.body.scrollHeight);")
        time.sleep(2.5)
    return links[:want]


def image_urls_for_post(driver, url):
    """Full-resolution image URLs for one post, excluding avatars and suggestions."""
    driver.get(url)
    # A fixed sleep is not enough: naturalWidth stays 0 until the image decodes,
    # so poll until a real post image appears rather than guessing a duration.
    items = []
    deadline = time.time() + 20
    while time.time() < deadline:
        time.sleep(1.5)
        items = driver.execute_script(PICK_IMAGES) or []
        if any(max(i.get("width", 0), i.get("height", 0)) >= MIN_IMAGE_EDGE
               and "profile picture" not in i.get("alt", "").lower()
               for i in items):
            break
    out = []
    seen = set()
    for item in items:
        src = item.get("url", "")
        if "profile picture" in item.get("alt", "").lower():
            continue
        if max(item.get("width", 0), item.get("height", 0)) < MIN_IMAGE_EDGE:
            continue
        # The same photo appears twice under different URLs while it loads, so
        # key on dimensions as well to keep one copy per picture.
        key = (item.get("width", 0), item.get("height", 0))
        if src in seen or key in seen:
            continue
        seen.add(src)
        seen.add(key)
        out.append(src)
    return out


def full_track_url(url):
    """Drop the byte-range so the CDN returns the whole track, not a fragment."""
    parts = urlparse(url)
    query = parse_qs(parts.query)
    query.pop("bytestart", None)
    query.pop("byteend", None)
    return urlunparse((parts.scheme, parts.netloc, parts.path, parts.params,
                       urlencode(query, doseq=True), parts.fragment))


def track_urls(driver, link):
    """Play the reel and return one complete URL per distinct media track."""
    driver.get(link)
    time.sleep(7)
    driver.execute_script(
        "const v=document.querySelector('video'); if(v){v.muted=true;v.play();}")
    time.sleep(6)
    raw = driver.execute_script(
        "return performance.getEntriesByType('resource').map(e=>e.name)"
        ".filter(n=>n.indexOf('%s')>-1)" % TRACK_MARKER) or []
    chosen = []
    paths = set()
    for url in raw:
        full = full_track_url(url)
        path = urlparse(full).path
        if path not in paths:
            paths.add(path)
            chosen.append(full)
    return chosen


def _probe_kind(path):
    try:
        out = subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
             "-of", "json", path], stderr=subprocess.DEVNULL)
        kinds = [s["codec_type"] for s in json.loads(out).get("streams", [])]
        if "video" in kinds:
            return "video"
        if "audio" in kinds:
            return "audio"
    except Exception:
        pass
    return None


def _fetch(url, jar, dest, referer="https://www.instagram.com/"):
    r = requests.get(url, headers={"User-Agent": UA, "Referer": referer},
                     cookies=jar, timeout=120)
    r.raise_for_status()
    with open(dest, "wb") as fh:
        fh.write(r.content)
    return len(r.content)


def download_video(driver, jar, link, out_dir):
    """Download one reel as a muxed mp4. Returns (status, path_or_None)."""
    code = link.rstrip("/").split("/")[-1]
    final = os.path.join(out_dir, "%s.mp4" % code)
    if os.path.exists(final):
        return "skip", final
    urls = track_urls(driver, link)
    if not urls:
        return "no-media", None
    tmpdir = tempfile.mkdtemp(prefix="igtrack-")
    try:
        best = {}
        for i, url in enumerate(urls):
            part = os.path.join(tmpdir, "t%d" % i)
            try:
                size = _fetch(url, jar, part)
            except Exception:
                continue
            kind = _probe_kind(part)
            if kind and size > best.get(kind, (None, 0))[1]:
                best[kind] = (part, size)
        if "video" not in best:
            return "no-video-track", None
        args = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                "-i", best["video"][0]]
        if "audio" in best:
            args += ["-i", best["audio"][0], "-c", "copy", "-shortest"]
        else:
            args += ["-c", "copy"]
        subprocess.run(args + ["-y", final], check=True)
        return "ok", final
    finally:
        for name in os.listdir(tmpdir):
            try:
                os.remove(os.path.join(tmpdir, name))
            except OSError:
                pass
        try:
            os.rmdir(tmpdir)
        except OSError:
            pass


def download_images(driver, jar, link, out_dir):
    """Download every full-resolution image of one post. Returns (status, count)."""
    code = link.rstrip("/").split("/")[-1]
    urls = image_urls_for_post(driver, link)
    if not urls:
        return "no-media", 0
    saved = 0
    for n, url in enumerate(urls, 1):
        suffix = "" if n == 1 else "_%d" % n
        path = os.path.join(out_dir, "%s%s.jpg" % (code, suffix))
        if os.path.exists(path):
            continue
        try:
            _fetch(url, jar, path)
            saved += 1
        except Exception:
            continue
    return ("ok" if saved else "no-media"), saved
