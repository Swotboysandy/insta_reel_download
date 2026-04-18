# Reel Studio: Instagram Downloader & Branding Automator

This project now contains:

- A Python/Flask backend in [`app.py`](./app.py) for Instagram download, preview generation, and branding/video processing.
- A new Next.js frontend in [`frontend`](./frontend) that replaces the old server-rendered UI without removing any Python code.
- The legacy Flask template in [`templates/index.html`](./templates/index.html), which is still present as a reference during the migration.

## Stack

### Backend
- Flask
- Instaloader
- Selenium
- MoviePy
- Pillow

### Frontend
- Next.js
- React
- lucide-react

## Run The Backend

1. Install Python dependencies:
   `pip install -r requirements.txt`
2. Start Flask:
   `python app.py`
3. The API will be available at:
   `http://127.0.0.1:5000`

## Run The Next.js Frontend

1. Open a second terminal.
2. Go into the frontend folder:
   `cd frontend`
3. Install frontend dependencies:
   `npm install`
4. Copy `.env.local.example` to `.env.local` if you need to change the API URL.
5. Start the frontend:
   `npm run dev`
6. Open:
   `http://127.0.0.1:3000`

By default the frontend calls the Flask API at `http://127.0.0.1:5000` through `NEXT_PUBLIC_API_BASE_URL`.

## Notes

- No Python processing code was removed or rewritten.
- Downloaded videos still come from `downloaded_reels`.
- Branded outputs still go to `branded_videos`.
- If you want, the next step can be cleaning up Flask so it serves only the API while Next owns the UI completely.
