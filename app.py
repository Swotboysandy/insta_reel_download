# Instagram Reel Downloader + Video Branding Studio
from flask import Flask, request, jsonify, send_file, render_template, send_from_directory
from flask_cors import CORS
import instaloader
import os
import threading
import uuid
import time
import re
import textwrap
import json
import base64
from io import BytesIO
from dotenv import load_dotenv

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy import VideoFileClip, ImageClip, CompositeVideoClip, ColorClip

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

load_dotenv()

app = Flask(__name__)
CORS(app)

DOWNLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "downloaded_reels")
BRANDED_FOLDER  = os.path.join(os.path.dirname(__file__), "branded_videos")
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
MANAGED_VIDEO_FOLDERS = [DOWNLOAD_FOLDER, BRANDED_FOLDER]
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
os.makedirs(BRANDED_FOLDER, exist_ok=True)

IG_USERNAME = os.getenv("IG_USERNAME", "")
IG_PASSWORD = os.getenv("IG_PASSWORD", "")

# Branding defaults
BRAND_DEFAULTS = {
    "target_width": 1080,
    "target_height": 1920,
    "text_area_height": 420,
    "bg_color": [255, 255, 255],
    "text_color": [0, 0, 0],
    "font_size": 52,
    "text_margin": 60,
    "text_top_padding": 80,
    "line_spacing": 14,
}

download_tasks = {}
brand_tasks = {}
GLOBAL_LOADER = None

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

    session_file = os.path.join(os.path.dirname(__file__), f"session-{IG_USERNAME}")
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
# TASK LOGGING
# ═══════════════════════════════════════════════════════════════════════════════
def log_task(task_id, message, task_store=None):
    store = task_store or download_tasks
    if task_id in store:
        timestamp = time.strftime("[%H:%M:%S]")
        log_entry = f"{timestamp} {message}"
        store[task_id]['logs'].append(log_entry)
        store[task_id]['status'] = message
        print(log_entry)


# ═══════════════════════════════════════════════════════════════════════════════
# SELENIUM: FETCH REELS / POSTS FROM PROFILE
# ═══════════════════════════════════════════════════════════════════════════════
def _create_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1200,800")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    return webdriver.Chrome(options=options)

def _selenium_login(driver, task_id=None):
    log_task(task_id, f"🔐 Logging into Instagram as {IG_USERNAME}...")
    driver.get("https://www.instagram.com/accounts/login/")
    time.sleep(3)
    try:
        cookie_buttons = driver.find_elements(By.XPATH, "//button[contains(text(), 'Allow') or contains(text(), 'Accept') or contains(text(), 'Only allow essential')]")
        if cookie_buttons:
            cookie_buttons[0].click()
            time.sleep(1)
    except:
        pass

    wait = WebDriverWait(driver, 20)
    username_field = None
    for by, val in [(By.NAME, "username"), (By.NAME, "email"), (By.CSS_SELECTOR, "input[type='text']")]:
        try:
            username_field = wait.until(EC.presence_of_element_located((by, val)))
            if username_field: break
        except:
            continue
    if not username_field:
        raise Exception("Could not find username field")
    username_field.send_keys(IG_USERNAME)

    password_field = None
    for by, val in [(By.NAME, "password"), (By.NAME, "pass"), (By.CSS_SELECTOR, "input[type='password']")]:
        try:
            password_field = driver.find_element(by, val)
            if password_field: break
        except:
            continue
    if not password_field:
        raise Exception("Could not find password field")
    password_field.send_keys(IG_PASSWORD)

    try:
        driver.find_element(By.XPATH, "//button[@type='submit']").click()
    except:
        password_field.send_keys(Keys.RETURN)
    time.sleep(8)
    for txt in ['Not Now', 'Not now', 'Cancel']:
        try:
            driver.find_element(By.XPATH, f"//button[contains(text(), '{txt}')]").click()
            time.sleep(1)
        except:
            pass

def fetch_reels_from_profile(username, max_reels=300, task_id=None):
    log_task(task_id, f"🚀 Fetching reels from @{username}...")
    driver = _create_driver()
    try:
        _selenium_login(driver, task_id)
        log_task(task_id, f"✅ Logged in! Navigating to @{username}/reels/...")
        driver.get(f"https://www.instagram.com/{username}/reels/")
        time.sleep(5)
        return _scroll_and_collect(driver, "reel", max_reels, task_id)
    except Exception as e:
        log_task(task_id, f"❌ Error: {e}")
        return []
    finally:
        driver.quit()

def fetch_posts_from_profile(username, max_posts=300, task_id=None):
    log_task(task_id, f"🚀 Fetching posts from @{username}...")
    driver = _create_driver()
    try:
        _selenium_login(driver, task_id)
        log_task(task_id, f"✅ Logged in! Navigating to @{username}...")
        driver.get(f"https://www.instagram.com/{username}/")
        time.sleep(5)
        return _scroll_and_collect(driver, "p", max_posts, task_id)
    except Exception as e:
        log_task(task_id, f"❌ Error: {e}")
        return []
    finally:
        driver.quit()

def _scroll_and_collect(driver, link_type, max_items, task_id):
    links = set()
    no_new_count = 0
    for scroll in range(150):
        anchors = driver.find_elements(By.XPATH, f"//a[contains(@href, '/{link_type}/')]")
        old_count = len(links)
        for a in anchors:
            href = a.get_attribute("href")
            if href and f"/{link_type}/" in href:
                links.add(href)
        new_found = len(links) - old_count
        if new_found > 0:
            log_task(task_id, f"   Found {len(links)} (+{new_found})...")
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.END)
        time.sleep(2.5)
        if new_found == 0:
            no_new_count += 1
            if no_new_count >= 5:
                log_task(task_id, "   No new items, stopping.")
                break
        else:
            no_new_count = 0
        if len(links) >= max_items:
            break
    log_task(task_id, f"🎉 Total found: {len(links)}")
    return list(links)


# ═══════════════════════════════════════════════════════════════════════════════
# DOWNLOAD LOGIC
# ═══════════════════════════════════════════════════════════════════════════════
def download_task(task_id, urls, is_profile=False, max_reels=300, mode='reel'):
    target_username = "unknown"
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
            download_tasks[task_id]['total'] = len(urls)
            download_tasks[task_id]['fetched_count'] = len(urls)

    # Download phase
    log_task(task_id, f"⬇️ Starting downloads ({mode} mode)...")
    loader = get_logged_in_loader()
    results = []
    total = len(urls)
    success_count = 0
    save_dir = os.path.join(DOWNLOAD_FOLDER, target_username if target_username != "unknown" else "singles")

    for idx, url in enumerate(urls):
        download_tasks[task_id]['current'] = idx + 1
        shortcode = extract_shortcode(url)
        if not shortcode:
            continue
        try:
            log_task(task_id, f"Downloading {idx+1}/{total}: {shortcode}...")
            post = instaloader.Post.from_shortcode(loader.context, shortcode)
            loader.download_post(post, target=target_username)
            results.append({'url': url, 'success': True})
            success_count += 1
        except Exception as e:
            log_task(task_id, f"❌ Failed {shortcode}: {e}")
            results.append({'url': url, 'success': False})
        time.sleep(1.5)

    download_tasks[task_id]['state'] = 'completed'
    download_tasks[task_id]['results'] = results
    download_tasks[task_id]['folder'] = save_dir
    download_tasks[task_id]['completed_at'] = time.time()
    log_task(task_id, f"🎉 Done! Downloaded {success_count}/{total}. Saved to: {save_dir}")


# ═══════════════════════════════════════════════════════════════════════════════
# BRANDING LOGIC (FONT + TEXT RENDERING + VIDEO COMPOSITING)
# ═══════════════════════════════════════════════════════════════════════════════
def _find_font(size=52):
    preferred = ["Inter-SemiBold.ttf", "arialbd.ttf", "Arial Bold.ttf", "Impact.ttf", "segoeui.ttf", "DejaVuSans-Bold.ttf"]
    search_dirs = [os.path.dirname(__file__), r"C:\Windows\Fonts", "/usr/share/fonts"]
    for name in preferred:
        for d in search_dirs:
            path = os.path.join(d, name)
            if os.path.isfile(path):
                return ImageFont.truetype(path, size)
        try:
            return ImageFont.truetype(name, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _sanitize_text(text):
    """Remove emojis/characters outside the Basic Multilingual Plane that cause missing boxes."""
    if not text:
        return text
    return re.sub(r'[^\u0000-\uFFFF]', '', text)


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
    bg_path = cfg.get("bg_path")
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
        logo_path = profile_cfg.get("logo_path", "")
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
                    initials, fill=(255, 255, 255), font=init_font
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
            wrapped = textwrap.fill(text, width=chars_per_line)
            lines = wrapped.split("\n")
            line_h = caption_font_size + line_sp
            total_h = line_h * len(lines)
            if total_h <= (area_h - y - 20):
                break
            caption_font_size -= 4
        else:
            font = _find_font(28)
            wrapped = textwrap.fill(text, width=int(usable_w / (28 * 0.55)))
            lines = wrapped.split("\n")
            line_h = 28 + line_sp

        for line in lines:
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


def generate_preview_image(video_path, caption, cfg=None, profile_cfg=None, mask_top=0, mask_bot=0):
    """
    Generate a static preview image (PNG) showing how the branded video will look.
    Grabs a frame from the video and composites it like the final output.
    Returns base64 encoded PNG string.
    """
    merged_cfg = BRAND_DEFAULTS.copy()
    if cfg: merged_cfg.update(cfg)
    cfg = merged_cfg

    tw, th = cfg["target_width"], cfg["target_height"]
    text_area_h = cfg["text_area_height"]
    video_area_h = th - text_area_h
    bg = tuple(cfg["bg_color"])

    # Grab first frame from video
    clip = VideoFileClip(video_path)
    frame = clip.get_frame(min(1.0, clip.duration / 2))
    clip.close()

    # Resize frame to fill width, cropping height if needed to fit video_area
    orig_h, orig_w = frame.shape[:2]
    
    scale_fill = max(tw / orig_w, video_area_h / orig_h)
    fill_w, fill_h = int(orig_w * scale_fill), int(orig_h * scale_fill)
    
    frame_img_full = Image.fromarray(frame).resize((fill_w, fill_h), Image.LANCZOS)
    
    # Crop the center to exactly fit tw x video_area_h
    left = (fill_w - tw) // 2
    top = (fill_h - video_area_h) // 2
    frame_img_final = frame_img_full.crop((left, top, left + tw, top + video_area_h))

    # Build canvas
    canvas = Image.new("RGB", (tw, th), bg)

    # Calculate mask size
    mask_top_px = int(video_area_h * (mask_top / 100.0))
    
    # Render text area to get the actual content height
    text_arr, text_content_bottom_y = _render_text_image(caption, cfg, profile_cfg)
    text_img = Image.fromarray(text_arr)
    
    # Crop the text image tightly to its content so it doesn't overwrite the video below it
    text_img = text_img.crop((0, 0, tw, text_content_bottom_y))

    # Calculate dynamic Y-offset for the text block so it sits just above the video content
    # The actual video starts at `text_area_h + mask_top_px`.
    # We want the bottom of the text (`text_content_bottom_y`) to hit that point, minus 30px padding
    # Offset = (Where we want it) - (Where it naturally is)
    target_bottom_y = text_area_h + mask_top_px - 30
    text_y_offset = max(0, target_bottom_y - text_content_bottom_y)
    
    print(f"DEBUG PREVIEW: text_area_h={text_area_h}, mask_top_px={mask_top_px}, target_bottom_y={target_bottom_y}, text_content_bottom_y={text_content_bottom_y}, text_y_offset={text_y_offset}")
    
    # Paste video frame in the video area
    canvas.paste(frame_img_final, (0, text_area_h))

    # Manual white masks to cover baked-in black bars
    draw = ImageDraw.Draw(canvas)
    mask_bot_size = int(video_area_h * (mask_bot / 100.0))
    
    if mask_top_px > 0:
        draw.rectangle([0, text_area_h, tw, text_area_h + mask_top_px], fill=bg)
    if mask_bot_size > 0:
        draw.rectangle([0, th - mask_bot_size, tw, th], fill=bg)
        
    # Paste text area (cropped tightly) on top of the masks at the offset
    canvas.paste(text_img, (0, text_y_offset))

    # Convert to base64 PNG
    buf = BytesIO()
    canvas.save(buf, format="PNG")
    buf.seek(0)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return b64


def brand_single_video(video_path, caption, cfg=None, profile_cfg=None, output_path=None, task_id=None, mask_top=0, mask_bot=0):
    """Brand a single video with meme-style text overlay and manual masking."""
    merged_cfg = BRAND_DEFAULTS.copy()
    if cfg: merged_cfg.update(cfg)
    cfg = merged_cfg

    tw, th = cfg["target_width"], cfg["target_height"]
    text_area_h = cfg["text_area_height"]
    video_area_h = th - text_area_h
    bg = tuple(cfg["bg_color"])

    if output_path is None:
        base = os.path.splitext(os.path.basename(video_path))[0]
        output_path = os.path.join(BRANDED_FOLDER, f"{base}_branded.mp4")

    log_task(task_id, f"📹 Processing: {os.path.basename(video_path)}", brand_tasks)

    clip = VideoFileClip(video_path)
    
    orig_w, orig_h = clip.size
    duration = clip.duration
    fps = clip.fps or 30

    scale_fill = max(tw / orig_w, video_area_h / orig_h)
    new_w, new_h = int(orig_w * scale_fill), int(orig_h * scale_fill)
    clip_resized = clip.resized((new_w, new_h))
    
    # Crop center to match target area exactly
    x_center = new_w / 2
    y_center = new_h / 2
    clip_final = clip_resized.cropped(
        x_center=x_center, y_center=y_center, 
        width=tw, height=video_area_h
    )

    bg_clip = ColorClip(size=(tw, th), color=bg, duration=duration)
    
    # Render text and get actual bottom Y to calculate offset
    text_arr, text_content_bottom_y = _render_text_image(caption, cfg, profile_cfg)
    
    # Crop the numpy array tightly to the text content bound
    text_arr_cropped = text_arr[:text_content_bottom_y, :, :]
    text_clip = ImageClip(text_arr_cropped, duration=duration)

    # Manual White masking bars based on user UI percentages
    mask_t_h = int(video_area_h * (mask_top / 100.0))
    mask_b_h = int(video_area_h * (mask_bot / 100.0))

    # Calculate dynamic Y-offset
    # Text should sit 30px above the visible video content (which starts at text_area_h + mask_t_h)
    target_bottom_y = text_area_h + mask_t_h - 10
    text_y_offset = max(0, target_bottom_y - text_content_bottom_y)

    layers = [
        bg_clip, 
        clip_final.with_position((0, text_area_h)),
    ]
    
    if mask_t_h > 0:
        layers.append(ColorClip(size=(tw, mask_t_h), color=bg, duration=duration).with_position((0, text_area_h)))
    if mask_b_h > 0:
        layers.append(ColorClip(size=(tw, mask_b_h), color=bg, duration=duration).with_position((0, th - mask_b_h)))

    # Add text_clip LAST so it sits on top of everything!
    layers.append(text_clip.with_position((0, text_y_offset)))

    final = CompositeVideoClip(layers, size=(tw, th))
    log_task(task_id, f"✍️ Rendering: {os.path.basename(output_path)}...", brand_tasks)

    final.write_videofile(
        output_path, fps=fps, codec="libx264", audio_codec="aac",
        preset="medium", threads=4, logger="bar"
    )
    clip.close()
    final.close()

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    log_task(task_id, f"✅ Done! ({size_mb:.1f} MB) → {output_path}", brand_tasks)
    return output_path


def brand_task_runner(task_id, videos, caption, cfg, profile_cfg, mask_top=0, mask_bot=0):
    """Background branding task."""
    results = []
    total = len(videos)
    for idx, vpath in enumerate(videos):
        brand_tasks[task_id]['current'] = idx + 1
        try:
            out = brand_single_video(vpath, caption, cfg, profile_cfg=profile_cfg, task_id=task_id, mask_top=mask_top, mask_bot=mask_bot)
            results.append({'file': os.path.basename(vpath), 'output': out, 'success': True})
        except Exception as e:
            log_task(task_id, f"❌ Error: {os.path.basename(vpath)}: {e}", brand_tasks)
            results.append({'file': os.path.basename(vpath), 'success': False, 'error': str(e)})

    brand_tasks[task_id]['state'] = 'completed'
    brand_tasks[task_id]['results'] = results
    brand_tasks[task_id]['completed_at'] = time.time()
    success = sum(1 for r in results if r['success'])
    log_task(task_id, f"🎉 Branded {success}/{total} videos!", brand_tasks)


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/download', methods=['POST'])
def start_download():
    data = request.get_json()
    urls = data.get('urls', [])
    max_reels = data.get('maxReels', 300)
    mode = data.get('mode', 'reel')
    if not urls:
        return jsonify({'error': 'No URLs provided'}), 400
    clean_urls = [u.strip() for u in urls if u.strip()]
    is_profile = len(clean_urls) == 1 and is_profile_url(clean_urls[0])
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
    return jsonify(result)

# --- File Browser APIs ---
@app.route('/api/files', methods=['GET'])
def list_video_files():
    """List all downloaded video files available for branding."""
    files = []
    for root, dirs, filenames in os.walk(DOWNLOAD_FOLDER):
        for f in sorted(filenames):
            ext = os.path.splitext(f)[1].lower()
            if ext in VIDEO_EXTENSIONS and '_branded' not in f:
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
    """List all branded output videos."""
    files = []
    for f in sorted(os.listdir(BRANDED_FOLDER)):
        ext = os.path.splitext(f)[1].lower()
        if ext in VIDEO_EXTENSIONS:
            full_path = os.path.join(BRANDED_FOLDER, f)
            size_mb = os.path.getsize(full_path) / (1024 * 1024)
            files.append({
                'name': f,
                'path': full_path.replace('\\', '/'),
                'size_mb': round(size_mb, 2)
            })
    return jsonify({'files': files, 'folder': BRANDED_FOLDER})

@app.route('/api/brand/preview', methods=['POST'])
def brand_preview():
    """Generate a static preview image of the branded video."""
    data = request.get_json()
    video_path = data.get('videoPath', '')
    caption = data.get('caption', '')
    profile_cfg = data.get('profileConfig', None)
    cfg = BRAND_DEFAULTS.copy()
    if data.get('config'):
        cfg.update(data['config'])
    mask_top = data.get('maskTop', 0)
    mask_bot = data.get('maskBot', 0)

    if not video_path or not os.path.isfile(video_path):
        return jsonify({'error': f'Video not found: {video_path}'}), 400

    try:
        b64 = generate_preview_image(video_path, caption, cfg, profile_cfg, mask_top, mask_bot)
        return jsonify({'preview': b64})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/brand/start', methods=['POST'])
def start_branding():
    """Start branding one or more videos."""
    data = request.get_json()
    video_paths = data.get('videoPaths', [])
    caption = data.get('caption', '')
    profile_cfg = data.get('profileConfig', None)
    cfg = BRAND_DEFAULTS.copy()
    if data.get('config'):
        cfg.update(data['config'])
    mask_top = data.get('maskTop', 0)
    mask_bot = data.get('maskBot', 0)

    if not video_paths:
        return jsonify({'error': 'No videos selected'}), 400

    # Validate all paths
    valid = [p for p in video_paths if os.path.isfile(p)]
    if not valid:
        return jsonify({'error': 'None of the video paths exist'}), 400

    task_id = str(uuid.uuid4())[:8]
    brand_tasks[task_id] = {
        'id': task_id, 'total': len(valid), 'current': 0, 'state': 'processing',
        'status': 'Starting branding...', 'logs': [], 'results': [],
        'created_at': time.time()
    }

    thread = threading.Thread(target=brand_task_runner, args=(task_id, valid, caption, cfg, profile_cfg, mask_top, mask_bot))
    thread.daemon = True
    thread.start()
    return jsonify({'task_id': task_id, 'message': 'Branding started'})

@app.route('/api/brand/<task_id>', methods=['GET'])
def get_brand_status(task_id):
    if task_id not in brand_tasks:
        return jsonify({'error': 'Task not found'}), 404
    return jsonify(brand_tasks[task_id])

# --- Serve video files for preview playback ---
@app.route('/api/video/<path:filepath>')
def serve_video(filepath):
    """Serve a video file for in-browser playback."""
    # filepath comes URL-encoded, decode it
    full_path = filepath.replace('/', os.sep)
    if not os.path.isfile(full_path):
        return "Not found", 404
    directory = os.path.dirname(full_path)
    filename = os.path.basename(full_path)
    return send_from_directory(directory, filename, mimetype='video/mp4')


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    print("🚀 Starting Instagram Reel Downloader + Branding Studio...")
    get_logged_in_loader()
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
