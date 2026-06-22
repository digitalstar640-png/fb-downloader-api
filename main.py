from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yt_dlp
import requests

app = FastAPI(title="Free FB Downloader & Subtitle Extractor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class URLRequest(BaseModel):
    url: str

@app.post("/api/download")
def download_facebook_video(data: URLRequest):
    try:
        ydl_opts = {'format': 'best', 'quiet': True, 'no_warnings': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(data.url, download=False)
            formats = info.get('formats', [])
            hd_url, sd_url = None, None
            for f in formats:
                fid = f.get('format_id', '')
                fnote = f.get('format_note', '').lower()
                if 'hd' in fid or 'hd' in fnote: hd_url = f.get('url')
                if 'sd' in fid or 'sd' in fnote: sd_url = f.get('url')
            if not sd_url and formats: sd_url = formats[-1].get('url')
            if not hd_url: hd_url = sd_url
            return {"hd_url": hd_url, "sd_url": sd_url}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/transcript")
def extract_fb_subtitles(data: URLRequest):
    try:
        ydl_opts = {'writesubtitles': True, 'writeautomaticsub': True, 'skip_download': True, 'quiet': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(data.url, download=False)
            subtitles = info.get('subtitles') or info.get('automatic_captions')
            if not subtitles: raise HTTPException(status_code=404, detail="No captions found.")
            lang = 'en' if 'en' in subtitles else ('hi' if 'hi' in subtitles else list(subtitles.keys())[0])
            sub_info = subtitles[lang]
            json3_url = next((item['url'] for item in sub_info if item.get('ext') == 'json3'), sub_info[0]['url'])
            sub_res = requests.get(json3_url)
            if sub_res.status_code == 200:
                events = sub_res.json().get('events', [])
                text_list = [seg.get('utf8', '').strip() for ev in events for seg in ev.get('segs', []) if seg.get('utf8', '').strip()]
                full_transcript = " ".join(text_list)
                if not full_transcript.strip(): raise HTTPException(status_code=404, detail="Empty caption text.")
                return {"transcript": full_transcript}
            else: raise HTTPException(status_code=400, detail="Failed to fetch captions.")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
