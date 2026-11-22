"""Download reels/videos from an Instagram profile using the logged-in browser.

Instagram's graphql API returns 401 and redirects to the homepage regardless of
session, so Instaloader cannot fetch media any more. The browser session still
works. Playing a reel makes Chrome request its DASH tracks; those requests are
visible in the performance timeline. Each request is a byte range, so stripping
`bytestart`/`byteend` yields the complete track. Video and audio arrive as
separate tracks and are muxed back together with ffmpeg.

Usage:
    python scripts/browser_video_download.py <username> [max_reels] [out_dir]
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlencode, urlparse, parse_qs, urlunparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import requests
import app
from scripts.browser_image_download import cookies_from_session, UA

MEDIA_RE = "/o1/v/t2/"


def full_track_url(url):
    """Drop the byte-range so the CDN returns the whole track, not a fragment."""
    parts = urlparse(url)
    query = parse_qs(parts.query)
    query.pop("bytestart", None)
    query.pop("byteend", None)
    return urlunparse((parts.scheme, parts.netloc, parts.path, parts.params,
                       urlencode(query, doseq=True), parts.fragment))


def probe_kind(path):
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


def collect_reel_links(driver, username, want):
    driver.get("https://www.instagram.com/%s/reels/" % username)
    time.sleep(6)
    links = []
    stale = 0
    while len(links) < want and stale < 12:
        found = driver.execute_script(
            "return Array.from(document.querySelectorAll('a[href*=\"/reel/\"]')).map(a=>a.href)")
        before = len(links)
        for href in found:
            clean = href.split("?")[0]
            if clean not in links:
                links.append(clean)
        stale = 0 if len(links) > before else stale + 1
        driver.execute_script("window.scrollBy(0, document.body.scrollHeight);")
        time.sleep(2.5)
    return links[:want]


def track_urls(driver, link):
    driver.get(link)
    time.sleep(7)
    driver.execute_script(
        "const v=document.querySelector('video'); if(v){v.muted=true;v.play();}")
    time.sleep(6)
    raw = driver.execute_script(
        "return performance.getEntriesByType('resource').map(e=>e.name)"
        ".filter(n=>n.indexOf('%s')>-1)" % MEDIA_RE) or []
    seen = []
    for url in raw:
        full = full_track_url(url)
        key = urlparse(full).path
        if key not in [urlparse(u).path for u in seen]:
            seen.append(full)
    return seen


def download(url, jar, dest):
    r = requests.get(url, headers={"User-Agent": UA,
                                   "Referer": "https://www.instagram.com/"},
                     cookies=jar, timeout=120)
    r.raise_for_status()
    with open(dest, "wb") as fh:
        fh.write(r.content)
    return len(r.content)


def fetch_one(driver, jar, link, out_dir):
    code = link.rstrip("/").split("/")[-1]
    final = os.path.join(out_dir, "%s.mp4" % code)
    if os.path.exists(final):
        return "skip", 0
    urls = track_urls(driver, link)
    if not urls:
        return "no-media", 0
    tmpdir = tempfile.mkdtemp(prefix="igtrack-")
    try:
        best = {}
        for i, url in enumerate(urls):
            part = os.path.join(tmpdir, "t%d" % i)
            try:
                size = download(url, jar, part)
            except Exception:
                continue
            kind = probe_kind(part)
            if kind and size > best.get(kind, (None, 0))[1]:
                best[kind] = (part, size)
        if "video" not in best:
            return "no-video-track", 0
        if "audio" in best:
            subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                            "-i", best["video"][0], "-i", best["audio"][0],
                            "-c", "copy", "-shortest", "-y", final], check=True)
        else:
            subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                            "-i", best["video"][0], "-c", "copy", "-y", final], check=True)
        return "ok", os.path.getsize(final)
    finally:
        for name in os.listdir(tmpdir):
            try:
                os.remove(os.path.join(tmpdir, name))
            except OSError:
                pass
        os.rmdir(tmpdir)


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    username = sys.argv[1]
    want = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    out_dir = sys.argv[3] if len(sys.argv) > 3 else os.path.join(
        app.DOWNLOAD_FOLDER, username)
    os.makedirs(out_dir, exist_ok=True)

    cookies = cookies_from_session()
    jar = dict((c["name"], c["value"]) for c in cookies)
    driver = app._create_driver()
    ok = 0
    failed = 0
    try:
        driver.get("https://www.instagram.com/")
        time.sleep(3)
        for c in cookies:
            try:
                driver.add_cookie(c)
            except Exception:
                pass
        driver.get("https://www.instagram.com/")
        time.sleep(4)
        if driver.execute_script("return !!document.querySelector('input[name=username]')"):
            raise SystemExit("Session cookies rejected; log in again.")

        links = collect_reel_links(driver, username, want)
        print("found %d reels" % len(links), flush=True)
        for i, link in enumerate(links, 1):
            code = link.rstrip("/").split("/")[-1]
            try:
                status, size = fetch_one(driver, jar, link, out_dir)
            except Exception as e:
                status, size = "error:%s" % type(e).__name__, 0
            if status == "ok":
                ok += 1
                print("[%d/%d] %s: %.1fMB" % (i, len(links), code, size / 1e6), flush=True)
            else:
                if status != "skip":
                    failed += 1
                print("[%d/%d] %s: %s" % (i, len(links), code, status), flush=True)
    finally:
        driver.quit()
    print("DONE ok=%d failed=%d dir=%s" % (ok, failed, out_dir), flush=True)


if __name__ == "__main__":
    main()
