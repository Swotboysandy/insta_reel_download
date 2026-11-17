# Reel Studio: Instagram Downloader & Branding Automator

This project contains:

- A Python/Flask backend in [`app.py`](./app.py) for Instagram download, preview generation, and branding/video processing.
- A Next.js frontend in [`frontend`](./frontend) for the UI.

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

- Downloaded videos go to `downloaded_reels/`.
- Branded outputs go to `branded_videos/`.
- `download_history.json` records which shortcodes have been downloaded so profile crawls can skip them. Wiped automatically when "Delete All Videos" is clicked.
