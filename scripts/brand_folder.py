"""Brand every video in a folder with a given brand preset.

Captions are read from the sibling .txt file's "Title:" line when present, so
YouTube Shorts keep their real titles instead of a shared placeholder.

Usage:
    python scripts/brand_folder.py <source_dir> <preset> [output_dir]
"""
import glob
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app

FALLBACK_CAPTION = "We post daily follow for more"


def caption_for(video_path):
    sidecar = os.path.splitext(video_path)[0] + ".txt"
    if os.path.isfile(sidecar):
        with open(sidecar, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.startswith("Title:"):
                    return line.split(":", 1)[1].strip()
    stem = os.path.splitext(os.path.basename(video_path))[0]
    stem = re.sub(r"\s*\[[^\]]+\]$", "", stem).strip()
    return stem if len(stem) > 12 else FALLBACK_CAPTION


def safe_name(video_path):
    stem = os.path.splitext(os.path.basename(video_path))[0]
    return re.sub(r"[^A-Za-z0-9._-]+", "_", stem)[:70]


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    source_dir = sys.argv[1]
    preset = sys.argv[2]
    out_dir = sys.argv[3] if len(sys.argv) > 3 else app.BRANDED_FOLDER
    os.makedirs(out_dir, exist_ok=True)

    videos = sorted(glob.glob(os.path.join(source_dir, "*.mp4")))
    print("%d videos to brand with preset %s" % (len(videos), preset), flush=True)
    ok = 0
    fail = 0
    for i, video in enumerate(videos, 1):
        out = os.path.join(out_dir, "%s_branded.mp4" % safe_name(video))
        started = time.time()
        try:
            app.brand_single_video(video, caption_for(video),
                                   {"brand_preset": preset}, None, output_path=out)
            mb = os.path.getsize(out) / 1e6
            ok += 1
            print("[%d/%d] OK %s | %.1fMB | %.0fs"
                  % (i, len(videos), safe_name(video)[:45], mb, time.time() - started),
                  flush=True)
        except Exception as e:
            fail += 1
            print("[%d/%d] FAIL %s | %s: %s"
                  % (i, len(videos), safe_name(video)[:45], type(e).__name__, str(e)[:150]),
                  flush=True)
    print("DONE ok=%d fail=%d dir=%s" % (ok, fail, out_dir), flush=True)


if __name__ == "__main__":
    main()
