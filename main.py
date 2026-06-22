from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yt_dlp
import requests
import time

app = FastAPI(title="Ultimate FB Downloader & Dual Transcriber API")

# CORS पॉलिसी ताकि ब्लॉगर वेबसाइट से रिक्वेस्ट ब्लॉक न हो
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class URLRequest(BaseModel):
    url: str

# अपनी AssemblyAI API Key यहाँ डालें (ऑडियो टू टेक्स्ट के लिए)
ASSEMBLY_API_KEY = "ed9f452b687b44d1abaa7902cd1eb822"

# 1. वीडियो डाउनलोड लिंक निकालने का एंडपॉइंट
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

# 2. ऑप्शन A: पुराना फ्री फेसबुक सबटाइटल्स/कैप्शन स्क्रैपर
@app.post("/api/transcript")
def extract_fb_subtitles(data: URLRequest):
    try:
        ydl_opts = {'writesubtitles': True, 'writeautomaticsub': True, 'skip_download': True, 'quiet': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(data.url, download=False)
            subtitles = info.get('subtitles') or info.get('automatic_captions')
            if not subtitles: 
                raise HTTPException(status_code=404, detail="इस वीडियो में कोई रेडीमेड कैप्शन नहीं मिले। कृपया 'AI Audio to Text' ऑप्शन यूज़ करें।")
            
            lang = 'en' if 'en' in subtitles else ('hi' if 'hi' in subtitles else list(subtitles.keys())[0])
            sub_info = subtitles[lang]
            json3_url = next((item['url'] for item in sub_info if item.get('ext') == 'json3'), sub_info[0]['url'])
            
            sub_res = requests.get(json3_url)
            if sub_res.status_code == 200:
                events = sub_res.json().get('events', [])
                text_list = [seg.get('utf8', '').strip() for ev in events for seg in ev.get('segs', []) if seg.get('utf8', '').strip()]
                full_transcript = " ".join(text_list)
                if not full_transcript.strip(): raise HTTPException(status_code=404, detail="कैप्शन खाली मिले।")
                return {"transcript": full_transcript}
            else: 
                raise HTTPException(status_code=400, detail="कैप्शन फ़ाइल लोड नहीं हो सकी।")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# 3. ऑप्शन B: नया एडवांस एआई (AI) ऑडियो टू टेक्स्ट कन्वर्टर
@app.post("/api/audio-to-text")
def audio_to_text_transcript(data: URLRequest):
    if not ASSEMBLY_API_KEY or ASSEMBLY_API_KEY == "YOUR_ASSEMBLYAI_API_KEY":
        raise HTTPException(status_code=500, detail="सर्वर पर एआई API की (API Key) सेट नहीं है।")
        
    try:
        # वीडियो में से बेस्ट ऑडियो स्ट्रीम का लिंक निकालना
        ydl_opts = {'format': 'bestaudio', 'quiet': True, 'skip_download': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(data.url, download=False)
            audio_url = info.get('url')
        
        if not audio_url:
            raise HTTPException(status_code=400, detail="वीडियो से ऑडियो ट्रैक नहीं निकाला जा सका।")

        # AssemblyAI को भेजना
        headers = {"authorization": ASSEMBLY_API_KEY, "content-type": "application/json"}
        transcript_request = {"audio_url": audio_url, "language_detection": True}
        
        response = requests.post("https://api.assemblyai.com/v2/transcript", json=transcript_request, headers=headers)
        transcript_id = response.json().get("id")

        if not transcript_id:
            raise HTTPException(status_code=500, detail="एआई सर्वर टास्क शुरू करने में विफल रहा।")

        # पोलिंग लूप (लंबे वीडियो के प्रोसेस होने का इंतज़ार)
        polling_endpoint = f"https://api.assemblyai.com/v2/transcript/{transcript_id}"
        attempts = 0
        while attempts < 60:
            polling_response = requests.get(polling_endpoint, headers=headers).json()
            status = polling_response.get("status")

            if status == "completed":
                return {"transcript": polling_response.get("text")}
            elif status == "error":
                raise HTTPException(status_code=500, detail=f"AI एरर: {polling_response.get('error')}")
            
            time.sleep(6)
            attempts += 1

        raise HTTPException(status_code=408, detail="वीडियो बहुत लंबा है, प्रोसेसिंग में अधिक समय लग रहा है।")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
