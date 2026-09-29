from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from urllib.parse import urlparse
import yt_dlp, uuid, os

app = FastAPI(title="SaveFlow")
os.makedirs("downloads", exist_ok=True)

ALLOWED_HEIGHTS = {144, 240, 360, 480, 720, 1080, 1440, 2160}


def check_url(url: str) -> str:
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.netloc:
        raise HTTPException(400, "Please enter a valid link starting with http:// or https://")
    return url


@app.get("/api/info")
def info(url: str):
    check_url(url)
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "noplaylist": True}) as ydl:
            data = ydl.extract_info(url, download=False)
    except Exception:
        raise HTTPException(400, "We couldn't read this link. Check that the video is public and the link is complete.")

    heights = sorted(
        {f["height"] for f in data.get("formats", [])
         if f.get("height") and f.get("vcodec") not in (None, "none")},
        reverse=True,
    )
    heights = [h for h in heights if h in ALLOWED_HEIGHTS] or []

    return {
        "title": data.get("title"),
        "thumbnail": data.get("thumbnail"),
        "duration": data.get("duration"),
        "uploader": data.get("uploader"),
        "heights": heights,
    }


@app.get("/api/download")
def download(url: str, kind: str = "mp4", height: int = 720):
    check_url(url)
    if kind not in ("mp4", "mp3"):
        raise HTTPException(400, "Unknown format.")
    file_id = str(uuid.uuid4())
    opts = {
        "outtmpl": f"downloads/{file_id}.%(ext)s",
        "quiet": True,
        "noplaylist": True,
    }

    if kind == "mp3":
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }]
    else:
        if height not in ALLOWED_HEIGHTS:
            raise HTTPException(400, "Unknown quality.")
        opts["format"] = (
            f"bv*[height<={height}][ext=mp4]+ba[ext=m4a]/"
            f"b[height<={height}][ext=mp4]/b[height<={height}]/b"
        )
        opts["merge_output_format"] = "mp4"

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            data = ydl.extract_info(url, download=True)
            path = ydl.prepare_filename(data)
            if kind == "mp3":
                path = os.path.splitext(path)[0] + ".mp3"
            elif not os.path.exists(path):
                path = os.path.splitext(path)[0] + ".mp4"
    except Exception:
        raise HTTPException(400, "Download failed. Try a different quality or another link.")

    safe_title = "".join(c for c in (data.get("title") or "video") if c.isalnum() or c in " -_")[:80].strip() or "video"
    return FileResponse(path, filename=f"{safe_title}.{kind}", background=BackgroundTask(os.remove, path))
app.mount("/", StaticFiles(directory="static", html=True), name="static")
from starlette.background import BackgroundTask