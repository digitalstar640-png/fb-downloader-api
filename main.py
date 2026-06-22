from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yt_dlp
import requests
import time

app = FastAPI(title="Ultimate FB Downloader & Audio Upload Transcriber API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class URLRequest(BaseModel):
    url: str

# अपनी AssemblyAI API Key यहाँ डालें
ASSEMBLY_API_KEY = "ed9f452b687b44d1abaa7902cd1eb822"

# 1. वीडियो डाउनलोड लिंक
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

# 2. फेसबुक कैप्शन स्क्रैपर
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
                return {"transcript": " ".join(text_list)}
            else: raise HTTPException(status_code=400, detail="Failed to fetch captions.")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# 3. फेसबुक वीडियो के लिंक से ऑडियो-टू-टेक्स्ट
@app.post("/api/audio-to-text")
def audio_to_text_transcript(data: URLRequest):
    try:
        ydl_opts = {'format': 'bestaudio', 'quiet': True, 'skip_download': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            audio_url = ydl.extract_info(data.url, download=False).get('url')
        if not audio_url: raise HTTPException(status_code=400, detail="Audio link not found.")
        return process_assemblyai(audio_url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# 4. नया एंडपॉइंट: डायरेक्ट ऑडियो फ़ाइल अपलोड करके टेक्स्ट में बदलना
@app.post("/api/upload-audio")
async def upload_audio_and_transcribe(file: UploadFile = File(...)):
    if not ASSEMBLY_API_KEY or ASSEMBLY_API_KEY == "ed9f452b687b44d1abaa7902cd1eb822":
        raise HTTPException(status_code=500, detail="API Key missing.")
    try:
        # फ़ाइल को सीधे AssemblyAI के सर्वर पर स्ट्रीम (Upload) करना
        headers = {"authorization": ASSEMBLY_API_KEY}
        upload_response = requests.post("https://api.assemblyai.com/v2/upload", headers=headers, data=file.file)
        uploaded_url = upload_response.json().get("upload_url")
        
        if not uploaded_url:
            raise HTTPException(status_code=500, detail="Audio upload failed.")
            
        return process_assemblyai(uploaded_url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# AssemblyAI प्रोसेसिंग का कॉमन फ़ंक्शन
def process_assemblyai(audio_source_url):
    headers = {"authorization": ASSEMBLY_API_KEY, "content-type": "application/json"}
    transcript_request = {"audio_url": audio_source_url, "language_detection": True}
    response = requests.post("https://api.assemblyai.com/v2/transcript", json=transcript_request, headers=headers)
    transcript_id = response.json().get("id")

    if not transcript_id: raise HTTPException(status_code=500, detail="AI Task creation failed.")

    while True:
        res = requests.get(f"https://api.assemblyai.com/v2/transcript/{transcript_id}", headers=headers).json()
        if res.get("status") == "completed": return {"transcript": res.get("text")}
        elif res.get("status") == "error": raise HTTPException(status_code=500, detail=res.get("error"))
        time.sleep(5)
