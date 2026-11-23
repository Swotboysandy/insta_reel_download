"""Write keys.json next to the branded videos.

Each branded file carries an `instalaz_key` comment tag derived from the
untouched source clip, so it survives re-rendering. Instalaz reads this sidecar
to recognise a clip it has already posted even after the whole library has been
re-encoded; without it, re-encoding changes the bytes and every old clip looks
brand new.

Usage:
    python scripts/write_keys_sidecar.py <folder>
"""
import glob
import json
import os
import subprocess
import sys


def key_for(path):
    try:
        out = subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format_tags=comment",
             "-of", "default=nw=1:nk=1", path],
            text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None
    prefix = "instalaz_key="
    return out[len(prefix):] if out.startswith(prefix) else None


def main():
    folder = sys.argv[1] if len(sys.argv) > 1 else "."
    mapping = {}
    missing = []
    for path in sorted(glob.glob(os.path.join(folder, "*.mp4"))):
        name = os.path.basename(path)
        key = key_for(path)
        if key:
            mapping[name] = key
        else:
            missing.append(name)
    out = os.path.join(folder, "keys.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(mapping, fh, indent=2, sort_keys=True)
    print("keys written: %d" % len(mapping))
    print("without a key: %d" % len(missing))
    for name in missing[:5]:
        print("  missing:", name)
    print("sidecar:", out)


if __name__ == "__main__":
    main()
