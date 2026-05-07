import asyncio
import os
import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import httpx
import yt_dlp
from starlette.background import BackgroundTask

app = FastAPI(title="Batch Adult Downloader - 0KB Fixed")

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
BIN_DIR = BASE_DIR / "bin"

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def home():
    with open(STATIC_DIR / "index.html", "r", encoding="utf-8") as f:
        return f.read()


def _is_ts_response(content_type: str, source_url: str) -> bool:
    content_type_lower = (content_type or "").lower()
    if any(token in content_type_lower for token in ("video/mp2t", "application/mp2t", "mpegts", "video/vnd.dlna.mpeg-tts")):
        return True

    source_url_lower = (source_url or "").lower()
    return "application/octet-stream" in content_type_lower and ".ts" in source_url_lower


def _sanitize_filename(title: str, ext: str) -> str:
    safe_title = (title or "video").replace('"', "").replace("'", "").replace("/", "-").strip()
    if not safe_title:
        safe_title = "video"
    return f"{safe_title}.{ext}"


def _resolve_ffmpeg_binary() -> str | None:
    env_path = (os.getenv("FFMPEG_PATH") or "").strip()
    candidates = []
    if env_path:
        candidates.append(env_path)

    candidates.extend(
        [
            str(BIN_DIR / "ffmpeg"),
            "/var/task/bin/ffmpeg",
            "ffmpeg",
        ]
    )

    for candidate in candidates:
        if not candidate:
            continue

        has_path_separator = (os.path.sep in candidate) or (os.path.altsep and os.path.altsep in candidate)
        if has_path_separator:
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
            continue

        resolved = shutil.which(candidate)
        if resolved:
            return resolved

    return None


def _extract_videos_sync(urls):
    results = []
    failed = []
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "nocheckcertificate": True,
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "format_sort": ["res", "ext:mp4", "size"],
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
        },
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        for raw_url in urls:
            url = (raw_url or "").strip()
            if not url:
                continue

            try:
                info = ydl.extract_info(url, download=False)
                if not info:
                    failed.append({"url": url, "error": "Metadata tidak ditemukan"})
                    continue

                formats = [
                    f
                    for f in info.get("formats", [])
                    if f.get("url") and f.get("ext") == "mp4" and ".m3u8" not in f.get("url", "")
                ]
                formats = sorted(
                    formats,
                    key=lambda x: (x.get("height") or 0, x.get("filesize") or 0),
                    reverse=True,
                )

                best = formats[0] if formats else None
                if not best:
                    failed.append({"url": url, "error": "Format MP4 tidak tersedia"})
                    continue

                results.append(
                    {
                        "title": info.get("title", "Video").replace("/", "-").replace("\\", "-"),
                        "thumbnail": info.get("thumbnail"),
                        "referer": info.get("webpage_url", "https://www.xnxx.com/"),
                        "best_format": {
                            "url": best.get("url"),
                            "quality": f"{best.get('height')}p",
                            "ext": "mp4",
                            "filesize": best.get("filesize") or best.get("filesize_approx"),
                        },
                    }
                )
            except Exception as exc:
                failed.append({"url": url, "error": str(exc)})

    return results, failed


@app.post("/extract")
async def extract(request: Request):
    data = await request.json()
    urls = data.get("urls", [])

    if not urls:
        return JSONResponse({"error": "Masukkan minimal 1 link"}, status_code=400)

    results, failed = await asyncio.to_thread(_extract_videos_sync, urls)
    return {"videos": results, "failed": failed, "total": len(urls)}


@app.get("/drive-config")
async def drive_config():
    return {
        "google_client_id": (os.getenv("GOOGLE_CLIENT_ID") or "").strip(),
        "google_drive_folder_id": (os.getenv("GOOGLE_DRIVE_FOLDER_ID") or "").strip(),
    }


@app.get("/download")
async def download_video(
    url: str = Query(...),
    title: str = Query("video"),
    referer: str = Query("https://www.xnxx.com/"),
):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
        "Accept": "video/mp4,video/*,*/*",
        "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": referer,
        "Origin": "https://www.xnxx.com",
        "Sec-Fetch-Site": "cross-site",
        "Sec-Fetch-Mode": "no-cors",
        "Sec-Fetch-Dest": "video",
        "Sec-Ch-Ua": '"Chromium";v="134", "Not;A=Brand";v="24", "Google Chrome";v="134"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Connection": "keep-alive",
        "Pragma": "no-cache",
        "Cache-Control": "no-cache",
        "Range": "bytes=0-",
    }

    client = httpx.AsyncClient(follow_redirects=True, timeout=180.0)
    response = None

    try:
        request = client.build_request("GET", url, headers=headers)
        response = await client.send(request, stream=True)

        if response.status_code not in (200, 206):
            body = await response.aread()
            await response.aclose()
            await client.aclose()
            return JSONResponse(
                {
                    "error": f"CDN blocked {response.status_code}",
                    "detail": body.decode(errors="ignore")[:300],
                },
                status_code=response.status_code,
            )

        filename_mp4 = _sanitize_filename(title, "mp4")
        filename_ts = _sanitize_filename(title, "ts")
        source_url = str(response.url)
        content_type = response.headers.get("content-type", "video/mp4")

        if _is_ts_response(content_type, source_url):
            ffmpeg_bin = _resolve_ffmpeg_binary()

            if not ffmpeg_bin:
                async def stream_ts_body():
                    try:
                        async for chunk in response.aiter_bytes(chunk_size=1024 * 1024):
                            yield chunk
                    finally:
                        await response.aclose()
                        await client.aclose()

                return StreamingResponse(
                    stream_ts_body(),
                    media_type=content_type,
                    headers={
                        "Content-Disposition": f'attachment; filename="{filename_ts}"',
                        "Content-Type": content_type,
                        "X-Remux-Status": "skipped_ffmpeg_unavailable",
                        "X-Remux-Note": "FFMPEG_PATH or ffmpeg binary not found; serving original TS stream",
                    },
                )

            temp_dir = tempfile.mkdtemp(prefix="xdownloader_remux_")
            input_ts_path = os.path.join(temp_dir, "input.ts")
            output_mp4_path = os.path.join(temp_dir, "output.mp4")

            try:
                with open(input_ts_path, "wb") as temp_ts_file:
                    async for chunk in response.aiter_bytes(chunk_size=1024 * 1024):
                        temp_ts_file.write(chunk)
            finally:
                await response.aclose()
                await client.aclose()

            ffmpeg_cmd = [
                ffmpeg_bin,
                "-y",
                "-i",
                input_ts_path,
                "-map",
                "0",
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                output_mp4_path,
            ]
            process = await asyncio.create_subprocess_exec(
                *ffmpeg_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await process.communicate()

            if process.returncode != 0 or not os.path.exists(output_mp4_path) or os.path.getsize(output_mp4_path) == 0:
                shutil.rmtree(temp_dir, ignore_errors=True)
                return JSONResponse(
                    {
                        "error": "FFmpeg remux TS ke MP4 gagal",
                        "detail": stderr.decode(errors="ignore")[-500:],
                        "hint": "Pastikan binary ffmpeg tersedia (FFMPEG_PATH) dan ukuran file tidak melebihi batas /tmp Vercel.",
                    },
                    status_code=502,
                )

            return FileResponse(
                path=output_mp4_path,
                media_type="video/mp4",
                filename=filename_mp4,
                background=BackgroundTask(shutil.rmtree, temp_dir, True),
                headers={
                    "X-Remux-Status": "success",
                    "X-Remux-Tool": ffmpeg_bin,
                },
            )

        async def stream_body():
            try:
                async for chunk in response.aiter_bytes(chunk_size=1024 * 1024):
                    yield chunk
            finally:
                await response.aclose()
                await client.aclose()

        response_headers = {
            "Content-Disposition": f'attachment; filename="{filename_mp4}"',
            "Content-Type": content_type,
            "X-Remux-Status": "not_needed",
        }

        content_length = response.headers.get("content-length")
        if content_length:
            response_headers["Content-Length"] = content_length

        return StreamingResponse(
            stream_body(),
            media_type=content_type,
            headers=response_headers,
        )
    except Exception as e:
        if response is not None:
            await response.aclose()
        await client.aclose()
        return JSONResponse({"error": f"Proxy error: {str(e)}"}, status_code=500)
