# Reel Studio — Handoff

_Last updated: 2026-09-13._

**Legend:** ✅ verified at time of writing (code or tool inspected on 2026-09-13) · 🕘 historical (observed earlier, not re-run) · ❓ unverified / assumption.

> **Read first — highest risks**
> 1. **All work since commit `58abcd9` is uncommitted** (9 files, +2410/−2149) and **no backup exists** — an earlier scratchpad snapshot was lost. ✅
> 2. **Captions no longer match videos** in the `memepageassets` repo: 51 captions (last edited 2026-08-10) vs 86 videos pushed 2026-09-10. ✅
> 3. `dist/ReelStudio/` contains copies of `.env` (Instagram password) and the Instagram session file. **Never share or zip that folder as-is.** ✅

---

## 1. Purpose

Local desktop tool for a meme page ("epicmemeoclock"):

1. **Download** Instagram reels from a reel URL or a whole profile.
2. **Brand** them: 1080×1920 canvas, header bar (logo + page name + @handle + optional caption), top mask, per-video audio pitch and zoom variation so uploads are not byte-identical.
3. **Publish** branded videos to a GitHub-backed asset repo (currently a **manual** process — see §11).

Runs locally only. No server, domain, or cloud hosting.

## 2. Owner preferences (from the conversation)

- **Branding recipe used for the current batch** 🕘: page name `epicmemeoclock`, handle `@epicmemeoclock`, logo `F:\tf.jpg` (150×150 JPEG; the original logo `F:\525248497_…jpg` no longer exists), style `header`, caption empty, `maskTop=3`, `maskBot=0`, `randomize_variation=true`.
- **Variation:** pitch **±3%** (`0.97–1.03`), zoom `1.00–1.05`, randomized per video. ±8% was rejected as audible.
- **Output target:** `F:\Sandy\S+Study\CODING\memepageassets\memepageassets\vid`, files named `vid (N).mp4`, plus `manifest.json` (a flat JSON array of filenames). Keep `manifest.json`.
- **Future publishing (decided, not built):** *Append* (continue numbering and append to the manifest), triggered by a **manual Publish button** (no auto-publish), allowed targets `memepageassets`, `ruthless_assets`, `vidDrafts`.
- **Repo history — unresolved:** the owner wants old videos force-deleted from GitHub history so the repo stops growing, which conflicts with *Append*. A clarifying question was interrupted. **Do not force-push anything until the owner explicitly confirms scope.**
- **Video playback allowlist:** locked to a fixed list (`.env`), never widened by API requests.
- **UI:** minimal and subtle, dark. The owner disliked the earlier glossy gradient UI.
- **Wants:** a double-click app (exe), speed, and **≥100 reels per batch** (currently 86).
- **Git:** commit or push only when asked. Per the owner's global `CLAUDE.md`, **never add a `Co-Authored-By: Claude` trailer**.
- The owner types fast with typos — interpret intent, and confirm destructive or outward-facing actions.

## 3. Current state

| Item | State |
|---|---|
| App deliverable | `dist\ReelStudio\ReelStudio.exe` (PyInstaller onedir), built 2026-09-12 04:18 ✅ |
| Downloaded reels | 86 in `downloaded_reels\` (`fboy` 44, `love4infiny` 42) ✅ |
| Branded outputs | 86 in `branded_videos\` (345 MB) ✅ |
| Download history | `download_history.json`, 214 entries ✅ |
| `memepageassets` | HEAD `301f951` == `origin/master`, 86 mp4, manifest has 86 entries, `.git` is 1.8 GB ✅ |
| UI | Minimal redesign, served by Flask from `frontend\out` ✅ |
| Publish feature | **Not implemented** (design decisions only) |
| Tests / CI | **None exist** ✅ |

## 4. Architecture & data flow

```
Browser ──HTTP──▶ Flask app.py @ 127.0.0.1:5000
                   ├─ "/" and "/<path:asset>"  → static Next.js export (frontend/out)
                   ├─ /api/*                   → JSON API
                   └─ background threads, state in in-memory dicts
                        download_tasks / brand_tasks / cleanup_tasks   (lost on restart)
```

- **Backend:** single file `app.py` (~1900 lines), Flask 3.0.0.
- **Frontend:** Next.js 15.5 App Router, `output: "export"`, one client component `frontend/app/page.js`, styles in `frontend/app/globals.css`. It calls `NEXT_PUBLIC_API_BASE_URL` (default `http://127.0.0.1:5000`, **baked in at build time**).
- **Two filesystem roots** ✅ (`app.py` header):
  - `APP_DIR` holds user data (`downloaded_reels`, `branded_videos`, `download_history.json`, `.env`, `session-*`). This is the exe's folder when frozen, otherwise the script folder.
  - `BUNDLE_DIR` holds read-only bundled files (`frontend/out`). This is `sys._MEIPASS` when frozen.
  - **Consequence:** the exe and a source run keep **separate** data directories. History was copied into `dist` at build time and will diverge.

### Download flow
`POST /api/download` → `download_task`
1. **Profile URL:** `_instaloader_collect`. The name is misleading — it drives **Selenium headless Chrome**, not the Instaloader API.
   - Injects the Instaloader session cookies (domain `.instagram.com`) and opens `/<user>/reels/`.
   - `_scroll_and_collect` gathers anchors matching `instagram.com/(<user>/)?(reel|p)/<code>/`.
2. `_filter_known_urls` skips shortcodes already in history.
3. `ThreadPoolExecutor(2)` runs `_download_one`: `Post.from_shortcode` → `download_post`, then sleeps a random 1.0–1.6 s.
4. `_record_download` writes the shortcode, url, username, mode, `view_count`, and `file_path` to history.

### Branding flow
`POST /api/brand/start` → `brand_task_runner`, which runs `ThreadPoolExecutor(BRAND_WORKERS)` over `brand_single_video`.
- **Header style (default)** — `_brand_header_ffmpeg`:
  - PIL renders the header PNG.
  - One ffmpeg `filter_complex`: scale → center-crop → overlay onto a colored 1080×1920 canvas → `drawbox` mask bars → overlay the header.
  - Audio via `-af asetrate=44100*p,aresample=44100,atempo=1/p`; video via `libx264 -preset $BRAND_PRESET -crf 23`.
  - If ffmpeg fails, it falls back to the moviepy path.
- **Watermark style:** moviepy composite (`_brand_watermark_style`), then the `_apply_pitch` ffmpeg post-pass, which copies video and re-encodes audio.
- **Preview** (`POST /api/brand/preview`): moviepy grabs one frame, PIL composites it, and the result is returned as base64 PNG.

### Other flows
- **Low-view cleanup** (`POST /api/cleanup/low-views`): backfills missing view counts via Instaloader (rate-limited), deletes files under the threshold, and merges results back into history under a lock.
- **Playback** (`GET /api/video/<path>`): serves only video files inside `VIDEO_ROOTS` = `downloaded_reels` + `branded_videos` + `EXTRA_VIDEO_ROOTS`. Anything else returns 404.

## 5. Key algorithms (✅ from code)

- **Header geometry** (1080×1920, `text_area_height=420`): `video_area_h = 1500`, `scale = max(1080/w, 1500/h) * zoom`, center crop, `mask_t_h = 1500 * maskTop%`, `text_y = max(0, 420 + mask_t_h − 10 − header_bottom)`.
- **Pitch without duration change:** `asetrate=44100*p` shifts pitch and tempo together, then `atempo=1/p` restores tempo. **The 44100 Hz rate is hard-coded** (see bug B5).
- **Scroll crawl:**
  - Each round polls page height for up to 6 s.
  - On a stall it rotates 4 nudge strategies (scroll up 900 px / jump to 50% / reset to top / jitter) with increasing back-off.
  - Stops after 15 consecutive empty rounds (`NO_NEW_LIMIT`) or on reaching the limit; hard ceiling of 500 rounds.
- **Task pruning:** keep 20 finished tasks per store (`MAX_KEPT_TASKS`).

## 6. Configuration

**`.env` in `APP_DIR`** — names only, never commit values:

| Variable | Default | Purpose |
|---|---|---|
| `IG_USERNAME`, `IG_PASSWORD` | — | Instagram login (secret). A session file `session-<IG_USERNAME>` is preferred and reused |
| `EXTRA_VIDEO_ROOTS` | `""` | `;`-separated extra playable folders (currently the memepageassets `vid` folder) |
| `HOST` / `PORT` | `127.0.0.1` / `5000` | Bind address. Bound to localhost on purpose |
| `FLASK_DEBUG` | off | Never enable together with a non-local `HOST` |
| `OPEN_BROWSER` | on when frozen, off from source | Auto-open the UI |
| `BRAND_WORKERS` / `BRAND_PRESET` / `BRAND_THREADS` | `3` / `veryfast` / `max(2, cores//workers)` | Render parallelism |

**Frontend:** `frontend/.env.local.example` → `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:5000`.

**Hard-coded** ✅:
- Download: `DOWNLOAD_WORKERS=2`, sleep 1.0–1.6 s, Chrome `--window-size=1920,1080`.
- `BRAND_DEFAULTS`: `style="header"`, `pitch_range=[0.97,1.03]`, `zoom_range=[1.0,1.05]`, `audio_pitch=1.0`, `randomize_variation=False` (the UI and API send `true` per job).
- Frontend `localStorage` keys: `reelStudio.brandForm.v1`, `reelStudio.downloadForm.v1`. `CAPTION_LIMIT=280`.

## 7. API (✅ 16 routes in `app.py`)

| Method | Route | Notes |
|---|---|---|
| GET | `/api/health` | `{status, ui_built}` |
| GET | `/`, `/<path:asset>` | Built UI. The catch-all returns a JSON 404 for unknown `api/*` |
| POST | `/api/download` | `{urls[], maxReels 1–5000, mode reel\|post}`. Validated |
| GET | `/api/download/<id>` | Task status, logs, `fetched_count`, `skipped_count` |
| POST | `/api/brand/preview` | Returns `{preview (b64), warning}`. The warning covers a missing logo |
| POST | `/api/brand/start` | `{videoPaths[], caption, maskTop, maskBot, profileConfig, config, outputFolder}`. Returns 400 if the logo is missing |
| GET | `/api/brand/<id>` | Task status and results |
| GET | `/api/files`, `/api/branded-files?folder=` | Listings. Branded listing includes `playable` + `note` |
| GET | `/api/video/<path>` | Allowlisted playback only |
| GET/POST | `/api/history`, `/api/history/clear` | |
| POST/GET | `/api/cleanup/low-views`, `/api/cleanup/<id>` | `{minViews, dryRun}` |
| POST | `/api/videos/delete-all` | Deletes managed videos and clears history |

## 8. Files & repositories

**Project:** `F:\Sandy\S+Study\CODING\insta_reel_down` → `https://github.com/Swotboysandy/insta_reel_download.git`, branch `main`, HEAD `58abcd9` ✅

| Path | Role |
|---|---|
| `app.py` | Entire backend |
| `frontend/app/page.js`, `globals.css`, `layout.js` | UI |
| `frontend/next.config.mjs` | `output:"export"`, `outputFileTracingRoot` (silences the parent-lockfile warning) |
| `frontend/package.json`, `package-lock.json` | Frontend dependencies and lockfile |
| `requirements.txt` | Python dependencies |
| `Reel Studio.bat` | Source launcher (untracked). Builds `frontend/out` if missing, then runs `python app.py` with `OPEN_BROWSER=1` |
| `ReelStudio.spec` | PyInstaller recipe (git-ignored, preserved) |
| `Inter-SemiBold.ttf` | **Tracked font, loaded at runtime by name** in `_find_font`. Not bundled into the exe |
| `dist/ReelStudio/` | Latest exe deliverable (plus copied `.env`, session, history) |
| `frontend/out/` | Built UI. Flask serves it, and the exe build consumes it |
| `downloaded_reels/`, `branded_videos/`, `download_history.json`, `session-*`, `.env` | User data and secrets (git-ignored) |
| `.claude/worktrees/quirky-pascal-d00b99/` | **Nested git worktree** on branch `claude/quirky-pascal-d00b99` @ `58abcd9`, with **1 uncommitted change** (`page.js` swaps default bg/text colors). From an older session. Preserved |

**Uncommitted changes vs HEAD** ✅: `.gitignore`, `README.md`, `app.py` (+1354), `frontend/app/globals.css` (full rewrite), `frontend/app/page.js`, `frontend/next.config.mjs`, `requirements.txt`, plus deletions of `dl_font.py` and `templates/index.html` (both intentional; the Flask template UI was replaced). `Reel Studio.bat` is untracked. **Nothing is backed up.**

**Related repositories (outside this project — never delete):**

| Repo | Path | Remote / branch | State |
|---|---|---|---|
| memepageassets | `F:\Sandy\S+Study\CODING\memepageassets\memepageassets` | `github.com/Swotboysandy/memepageassets`, `master` | `301f951` in sync, clean. Contains `generate_captions.py` and `memepage_updated_captions.txt` (51 lines, stale). No LFS in use, although git-lfs 3.5.1 is installed ✅ |
| ruthless_assets | `F:\Sandy\S+Study\CODING\ruthless_assets` | `github.com/Swotboysandy/ruthless_assets` | Chosen publish target. Layout **not inspected** ❓ |
| vidDrafts | `F:\Sandy\S+Study\CODING\vidDrafts` | `github.com/Swotboysandy/vidDrafts` | Chosen publish target. Layout **not inspected** ❓ |

## 9. Environment & dependencies (✅ versions installed)

- Windows 11, 12 logical cores.
- Python 3.10.6, Node v22.22.0, PyInstaller 6.22.2.
- Python packages: flask 3.0.0, flask-cors 4.0.0, instaloader 4.15.3, selenium 4.16.0, moviepy 2.2.1, imageio-ffmpeg 0.6.0 (ships its own ffmpeg), numpy 2.2.6, pillow 12.3.0, python-dotenv 1.2.2.
- Frontend: next 15.5.0, react/react-dom 19.1.1, lucide-react, tailwindcss/postcss 4.
- External: Google Chrome at `C:\Program Files\Google\Chrome\Application\chrome.exe` ✅. chromedriver is resolved by Selenium Manager ❓ (not checked on another machine).
- Services: Instagram (web page + Instaloader) and GitHub over HTTPS using local git credentials.

## 10. Build · run · test · debug · release

```bash
# one-time setup
pip install -r requirements.txt
cd frontend && npm install

# run from source (single process, UI + API on :5000)
"Reel Studio.bat"                                  # or:
cd frontend && npx next build && cd .. && python app.py   # then open http://127.0.0.1:5000

# frontend hot-reload development (API stays on :5000)
cd frontend && npm run dev                          # http://localhost:3000  ❓ not re-run since output:"export" was added

# build the exe (run from project root; the spec uses relative paths)
cd frontend && npx next build && cd ..
python -m PyInstaller --noconfirm ReelStudio.spec
cp .env session-* download_history.json dist/ReelStudio/   # runtime files the exe needs beside it

# refresh ONLY the UI inside an existing exe (no PyInstaller rebuild)
cd frontend && npx next build && cd ..
rm -rf dist/ReelStudio/_internal/frontend/out && cp -r frontend/out dist/ReelStudio/_internal/frontend/out
```

- **Checks** (there are no automated tests): `python -m pyflakes app.py`, `npx next build`, endpoint smoke tests (`curl http://127.0.0.1:5000/api/health`), and a browser visual check.
- **Debug:**
  - The exe console shows logs. Set `PYTHONIOENCODING=utf-8` when running from a Windows console, because logs contain emoji.
  - When a crawl finds 0 links, `APP_DIR\debug_screenshot.png` captures what Chrome saw.
- **Exe build pitfalls already solved** 🕘:
  - `jedi` (pulled in via moviepy→IPython) causes a file-vs-directory collision → excluded.
  - `imageio` needs package metadata → `--copy-metadata`.
  - The build prints 2 benign warnings (`pycparser.lextab/yacctab` not found).
- **AI-session tooling notes** 🕘: in this Git Bash, `cp` prompts before overwriting and `>` refuses to overwrite (noclobber). Use `rm` first, or `>|`.
- **Release:**
  - There is no versioning or release process. The frontend `package.json` says 0.1.0. **No git tags exist**, locally or on `origin` ✅.
  - The artifact is the whole `dist\ReelStudio\` folder. To distribute it, first remove `.env` and `session-*` from it.

## 11. Publishing to memepageassets (manual procedure used 2026-09-10) 🕘

This batch **replaced** the folder's videos; future publishes should *append*.

1. Delete `vid\*.mp4`, keeping `vid\manifest.json`.
2. Copy `branded_videos\*.mp4` into `vid\`.
3. Rename in sorted source-filename order to `vid (1).mp4 … vid (86).mp4`, and rewrite `manifest.json` as the list of those names.
4. Verify byte sizes match the source, then `git add -A vid`, `git commit`, `git push origin master` (**no force**).

## 12. Tested vs untested

**Tested:**
- Profile crawl by cookie injection (fboy 44, love4infiny 42) 🕘. Download of 86 reels 🕘; counts ✅.
- ffmpeg header branding: 86/86 succeeded with 0 fallbacks 🕘; a 100 s clip rendered in 20.7 s (moviepy took >7 min) 🕘.
- A rendered frame was inspected: 1080×1920, correct header and logo, audio present, duration preserved (100.6 s) 🕘. The evidence file was removed in cleanup; this is the record.
- Pitch values across 86 renders fell within 0.971–1.030 🕘 (from in-memory logs, not persisted).
- memepageassets push is in sync ✅.
- Path-traversal fix: `win.ini`, `.env`, `app.py`, and the session file all returned 404, while an allowlisted video returned 200 🕘. Code present ✅.
- `/api/download` rejects bad `maxReels`, `mode`, blank URLs, and an empty body with 400 🕘. Code present ✅.
- Missing logo is rejected on brand start and warned in preview 🕘. Code present ✅.
- Exe: starts, reuses the session (no 2FA prompt), serves `/api/health`, `/`, `/api/history` (214), `/api/branded-files`, and CSS 🕘. Bundled CSS hash `0fe66a571fd4ad88` matches the source build ✅.
- Minimal UI visually checked on the Download and Brand tabs, including the file list 🕘.
- `python -m pyflakes app.py` is clean ✅.

**Not tested / unverified ❓:**
- Watermark-style **full render** (only its preview was checked).
- Low-view cleanup **real deletion** (only a partial dry run).
- Posts mode.
- The Outputs tab after the redesign.
- Pitch correctness on 48 kHz sources.
- The exe on another PC.
- `npm run dev` since the export change.
- Whether any tool pairs captions with `vid (N).mp4`.
- Whether other machines or bots pull the asset repos (relevant to any force-push).
- A light theme (none exists; dark only).

## 13. Known bugs & issues

| # | Issue | Severity |
|---|---|---|
| B1 | All work uncommitted, no backup | High |
| B2 | memepageassets captions (51, stale) don't match the 86 videos | High if a posting tool uses them |
| B3 | ~44 reels per profile ceiling: Instagram revokes the session mid-scroll and the page collapses to the logged-out ~985 px layout. Re-runs return the same items 🕘 | High (blocks the ≥100 goal) |
| B4 | `subprocess.run` for ffmpeg has **no timeout** (2 calls) ✅ — a hung ffmpeg blocks a worker forever | Medium |
| B5 | Pitch filter hard-codes 44100 Hz; a 48 kHz source would get an extra ~8% pitch drop ❓ | Medium |
| B6 | Tasks live in memory and there is no cancel endpoint. A restart loses running jobs (UI shows "Task lost") | Medium |
| B7 | moviepy paths drop `*TEMP_MPY_wvf_snd.mp4` into the working directory when killed (4 were removed in cleanup) | Low |
| B8 | Brand progress uses `pool.map`, so it advances in submission order (chunky) | Low |
| B9 | Preview decodes with moviepy (slow for large files) | Low |
| B10 | memepageassets `.git` is 1.8 GB and grows with every batch; the history strategy is undecided | Medium |
| B11 | `README.md` is stale: no mention of single-port serving, the exe, or env vars, and it still calls the button "Delete All Videos" | Low |
| B12 | The exe doesn't bundle `Inter-SemiBold.ttf`, so exe renders may use a fallback font ❓ | Low |
| B13 | `.gitignore` keeps an obsolete `video_roots.json` entry | Trivial |

## 14. Next steps (prioritized)

**P0**
1. **Commit the working tree** to a branch after the owner approves. `build/`, `dist/`, `frontend/out/`, and `*.spec` are already ignored. No `Co-Authored-By` trailer.
2. **Fix the captions mismatch** in memepageassets before anything posts: inspect `generate_captions.py` and whatever consumes it, then regenerate or re-pair.

**P1**

3. **Resolve the history strategy** with the owner — one-time purge then append, wipe on every publish, or clear the folder. Check whether other clones pull the repo. **Get explicit confirmation before any force-push.**
4. **Build the Publish feature** using the decisions already made (append, manual button, 3 allowlisted targets):
   - Inspect `ruthless_assets` and `vidDrafts` layouts first.
   - Targets come from `.env` only.
   - `git pull --rebase --autostash`, add only the new files plus the manifest, never force by default.
   - Consider a new `publisher.py` module.
5. **Get past 86 → ≥100 reels:** download a third profile (history dedupes across profiles), and/or rework the crawl to read the page's GraphQL/XHR responses instead of DOM anchors ❓.

**P2**

6. Add timeouts to ffmpeg `subprocess.run` calls.
7. Probe the source sample rate and use it in the pitch filter.
8. Switch the brand runner to `as_completed`.
9. Generate previews with an ffmpeg single-frame seek.
10. Add cancel endpoints and task persistence.
11. Update `README.md`; bundle `Inter-SemiBold.ttf` into the exe; visually check the Outputs tab; consider an installer, icon, and versioning.
12. **Optionally resume the stopped improvement-analysis workflow** (read-only analysis of download, branding, UI, and publish; its findings are unverified):
    - Run `wf_d99066ef-d93`; script at `C:\Users\sunny\.claude\projects\F--Sandy-S-Study-CODING-insta-reel-down\1a447296-7640-43db-933c-16227a8a6573\workflows\scripts\reel-studio-improvement-plan-wf_d99066ef-d93.js`.
    - Its journal shows 28 agent results cached and 26 agents cut off at session end; synthesis never completed.

## 15. Cleanup record (2026-09-13)

_Findings were extracted from these files before removal:_
- **`debug_screenshot.png`** (2026-09-05): Chrome showed Instagram's logged-out "Sign up to see more" wall. That evidence led to the cookie-injection crawl.
- **`verify_frame.png`**: see §12, the frame inspection.
- **`preview_test.png`**: preview with the `F:\tf.jpg` logo rendered correctly.
- **`build_log.txt`**: the build completed with 2 benign pycparser warnings.
- **`frontend/dev.log`**: a stale `EADDRINUSE :3001` from an old dev-server attempt.
- **`*TEMP_MPY_wvf_snd.mp4`**: moviepy temp audio from killed renders (bug B7).

**Removed — 12 items, 90,789,794 bytes (86.6 MiB).** Every path was resolved and confirmed to sit inside the project; none were symlinks; 0 failures.

| Bytes | Path | Why it was disposable |
|---:|---|---|
| 57,888,649 | `frontend/.next/` | Next.js build cache. Not used at runtime (Flask serves `frontend/out`); `next build` recreates it |
| 28,942,662 | `build/` | PyInstaller intermediate cache; the next exe build recreates it |
| 1,644,091 | `2026-09-03_17-49-06_UTC_brandedTEMP_MPY_wvf_snd.mp4` | moviepy temp audio from a killed render (B7) |
| 991,967 | `2026-09-03_19-48-51_UTC_brandedTEMP_MPY_wvf_snd.mp4` | same |
| 466,641 | `verify_frame.png` | test frame; finding kept in §12 |
| 419,986 | `preview_test.png` | test render; finding kept above |
| 249,126 | `2026-09-04_03-28-44_UTC_brandedTEMP_MPY_wvf_snd.mp4` | moviepy temp audio |
| 96,908 | `vid (100)_brandedTEMP_MPY_wvf_snd.mp4` | moviepy temp audio |
| 49,623 | `__pycache__/` | bytecode cache; recreated when `app.py` is *imported* (not when run as a script) |
| 22,203 | `debug_screenshot.png` | crawl diagnostic; the app rewrites it when needed |
| 17,084 | `build_log.txt` | PyInstaller log; findings kept in §10 |
| 854 | `frontend/dev.log` | stale dev-server log |

**Preserved deliberately:**
- `dist/ReelStudio/` — the latest deliverable. The exe is byte-identical after cleanup (8,509,627 bytes). Its empty `downloaded_reels/` and `branded_videos/` are the exe's own data folders, which it recreates at launch.
- `frontend/out/` — the UI that Flask serves, and the input to the exe build.
- `frontend/node_modules/`, `frontend/package-lock.json` — dependencies and lockfile.
- `Inter-SemiBold.ttf` — tracked, and loaded at runtime by name. It has no import referencing it, so an import scan would wrongly call it unused.
- `ReelStudio.spec` — git-ignored, but it is the recipe for an identical rebuild.
- `Reel Studio.bat`, `HANDOFF.md`, `README.md`, and all source and config.
- `downloaded_reels/`, `branded_videos/`, `download_history.json`, `.env`, `session-*` — user data and secrets.
- `.claude/` — contains the nested worktree `quirky-pascal-d00b99` (holds an uncommitted change) and `settings.local.json`.
- Nothing outside the project was touched: memepageassets is still at HEAD `301f951` with 0 dirty files.

**Validation after cleanup** ✅ (2026-09-13):
- Every preserved item is present and the exe size is unchanged. Reels 86/86, branded 86/86, history 214/214.
- The nested worktree is still registered, with its 1 uncommitted change.
- `git status`: tracked modifications are identical to before cleanup; the only new untracked file is `HANDOFF.md`.
- No stray moviepy or ffmpeg temp files remain.
- `python -m pyflakes app.py` is clean and `app.py` parses.
- **Source runtime smoke test** (`python app.py`): `/api/health`, `/`, `/api/files`, `/api/branded-files`, `/api/history`, and a `/_next` CSS asset all returned HTTP 200. The server was stopped afterwards.
- **Deliberately not re-run:** `npx next build` (it would immediately recreate the 56 MB `.next` cache) and the exe (none of its files changed).

**Remaining issues:** unchanged by the cleanup — see §13 and §14.
