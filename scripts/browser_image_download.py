"""Download post images from an Instagram profile using the logged-in browser.

Instagram's graphql API now redirects to the homepage regardless of session, so
Instaloader can no longer fetch media. The browser session still works, so this
drives SeleniumBase UC mode: scroll the profile, open each post, read the <img>
source straight from the DOM, then fetch the bytes with the browser's cookies.

Usage:
    python scripts/browser_image_download.py <username> [max_posts] [out_dir]
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import requests
import app

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")


def cookies_from_session():
    loader = app.get_logged_in_loader()
    if not loader:
        raise SystemExit("No Instagram session. Check IG_USERNAME in .env.")
    return [{"name": c.name, "value": c.value, "domain": ".instagram.com",
             "path": "/", "secure": True} for c in loader.context._session.cookies]


def collect_post_links(driver, username, want):
    driver.get("https://www.instagram.com/%s/" % username)
    time.sleep(6)
    links = []
    stale = 0
    while len(links) < want and stale < 12:
        found = driver.execute_script(
            "return Array.from(document.querySelectorAll('a[href*=\"/p/\"]')).map(a=>a.href)")
        before = len(links)
        for href in found:
            clean = href.split("?")[0]
            if clean not in links:
                links.append(clean)
        stale = 0 if len(links) > before else stale + 1
        driver.execute_script("window.scrollBy(0, document.body.scrollHeight);")
        time.sleep(2.5)
    return links[:want]


# Instagram serves the post image at full resolution in the DOM and provides no
# srcset, so `src` is already the original. Scope to the first <article>, drop
# avatars by their alt text, and require real post dimensions so that suggested
# -post thumbnails further down the page are never picked up.
PICK_IMAGES = """
const root = document.querySelector('article') || document;
return Array.from(root.querySelectorAll('img')).map(img => ({
  url: img.currentSrc || img.src || '',
  width: img.naturalWidth || 0,
  height: img.naturalHeight || 0,
  alt: img.alt || ''
})).filter(i => i.url && i.url.indexOf('blob:') !== 0);
"""

# Instagram renders the post itself at 1440px wide and the "suggested posts"
# strip below it at 640px tall, so a 700px floor separates them cleanly.
MIN_EDGE = 700


def image_urls_for_post(driver, url):
    driver.get(url)
    # A fixed sleep is not enough: naturalWidth stays 0 until the image decodes,
    # so poll until a real post image appears rather than guessing a duration.
    items = []
    deadline = time.time() + 20
    while time.time() < deadline:
        time.sleep(1.5)
        items = driver.execute_script(PICK_IMAGES) or []
        if any(max(i.get("width", 0), i.get("height", 0)) >= MIN_EDGE
               and "profile picture" not in i.get("alt", "").lower()
               for i in items):
            break
    out = []
    seen = set()
    for item in items:
        src = item.get("url", "")
        if "profile picture" in item.get("alt", "").lower():
            continue
        if max(item.get("width", 0), item.get("height", 0)) < MIN_EDGE:
            continue
        # The same photo appears twice under different URLs while it loads, so
        # key on dimensions rather than URL to keep one copy per picture.
        key = (item.get("width", 0), item.get("height", 0))
        if src in seen or key in seen:
            continue
        seen.add(src)
        seen.add(key)
        out.append(src)
    return out


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    username = sys.argv[1]
    want = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    out_dir = sys.argv[3] if len(sys.argv) > 3 else os.path.join(
        app.DOWNLOAD_FOLDER, "%s-images" % username)
    os.makedirs(out_dir, exist_ok=True)

    cookies = cookies_from_session()
    driver = app._create_driver()
    saved = 0
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

        links = collect_post_links(driver, username, want)
        print("found %d posts" % len(links), flush=True)

        jar = dict((c["name"], c["value"]) for c in cookies)
        headers = {"User-Agent": UA,
                   "Referer": "https://www.instagram.com/%s/" % username}
        for i, link in enumerate(links, 1):
            code = link.rstrip("/").split("/")[-1]
            try:
                urls = image_urls_for_post(driver, link)
                if not urls:
                    print("[%d/%d] %s: no image found" % (i, len(links), code), flush=True)
                    failed += 1
                    continue
                for n, u in enumerate(urls, 1):
                    suffix = "" if n == 1 else "_%d" % n
                    path = os.path.join(out_dir, "%s%s.jpg" % (code, suffix))
                    if os.path.exists(path):
                        continue
                    r = requests.get(u, headers=headers, cookies=jar, timeout=40)
                    r.raise_for_status()
                    with open(path, "wb") as fh:
                        fh.write(r.content)
                    saved += 1
                print("[%d/%d] %s: %d image(s)" % (i, len(links), code, len(urls)), flush=True)
            except Exception as e:
                failed += 1
                print("[%d/%d] %s: FAIL %s %s" % (i, len(links), code, type(e).__name__,
                                                  str(e)[:90]), flush=True)
    finally:
        driver.quit()
    print("DONE saved=%d failedPosts=%d dir=%s" % (saved, failed, out_dir), flush=True)


if __name__ == "__main__":
    main()
