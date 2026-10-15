"""Muxes the separate video and audio streams of a Reddit video into one MP4, so embeds play with sound."""

import asyncio
import logging
import os
import re
import secrets
import tempfile
import time
import xml.etree.ElementTree as ET
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse

SECRET = os.environ['MUX_SECRET']
CACHE_DIR = Path(tempfile.gettempdir()) / 'mux-cache'
CACHE_TTL = 24 * 60 * 60
# Discord drops the embed when the video takes over 10s, this leaves the worker time to fall back to the silent video
JOB_TIMEOUT = 7
# The best quality whose estimated size stays under this is picked, so the download fits in JOB_TIMEOUT
MAX_SIZE = 50 * 1024 * 1024

VIDEO_ID = re.compile(r'[a-z0-9]{1,20}')
DURATION = re.compile(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:([\d.]+)S)?')
NS = {'mpd': 'urn:mpeg:dash:schema:mpd:2011'}

log = logging.getLogger('uvicorn.error')
client: httpx.AsyncClient
# Discord and the worker can ask for the same video at once, they share one mux
jobs: dict[str, asyncio.Task[Path]] = {}


def parse_duration(value: str) -> float:
    match = DURATION.fullmatch(value)
    if not match:
        return 0
    hours, minutes, seconds = (float(group or 0) for group in match.groups())
    return hours * 3600 + minutes * 60 + seconds


def pick_streams(mpd: str) -> tuple[str, str | None]:
    """File names of the video and audio stream to mux, from the DASH manifest"""
    root = ET.fromstring(mpd)
    duration = parse_duration(root.get('mediaPresentationDuration', ''))

    streams: dict[str, list[tuple[int, str]]] = {'video': [], 'audio': []}
    for adaptation in root.iterfind('.//mpd:AdaptationSet', NS):
        for representation in adaptation.iterfind('mpd:Representation', NS):
            # Older manifests have no contentType and only a mimeType
            mime_type = representation.get('mimeType') or adaptation.get('mimeType') or ''
            kind = adaptation.get('contentType') or mime_type.split('/')[0]
            file = representation.findtext('mpd:BaseURL', namespaces=NS)
            if kind in streams and file:
                streams[kind].append((int(representation.get('bandwidth', 0)), file))

    if not streams['video']:
        raise HTTPException(404)

    audio_bandwidth, audio = max(streams['audio'], default=(0, None))
    fitting = [s for s in streams['video'] if (s[0] + audio_bandwidth) * duration / 8 <= MAX_SIZE]
    _, video = max(fitting) if fitting else min(streams['video'])
    return video, audio


async def download(url: str, path: Path):
    async with client.stream('GET', url) as response:
        response.raise_for_status()
        with path.open('wb') as file:
            async for chunk in response.aiter_bytes(1 << 16):
                file.write(chunk)


async def mux(video_id: str) -> Path:
    start = time.monotonic()
    base_url = f'https://v.redd.it/{video_id}/'
    response = await client.get(base_url + 'DASHPlaylist.mpd')
    # v.redd.it answers 403 for files that don't exist
    if response.status_code in (403, 404):
        raise HTTPException(404)
    response.raise_for_status()
    video, audio = pick_streams(response.text)

    # In the cache dir so the result can be moved into place atomically
    with tempfile.TemporaryDirectory(dir=CACHE_DIR) as tmp:
        video_path, audio_path, out_path = Path(tmp, 'video.mp4'), Path(tmp, 'audio.mp4'), Path(tmp, 'out.mp4')
        args = ['ffmpeg', '-nostdin', '-loglevel', 'error', '-i', str(video_path)]
        if audio:
            await asyncio.gather(download(base_url + video, video_path), download(base_url + audio, audio_path))
            args += ['-i', str(audio_path), '-map', '0:v:0', '-map', '1:a:0']
        else:
            await download(base_url + video, video_path)
        # faststart puts the index at the front, so players can start before the whole file arrived
        args += ['-c', 'copy', '-movflags', '+faststart', str(out_path)]

        process = await asyncio.create_subprocess_exec(*args, stderr=asyncio.subprocess.PIPE)
        _, stderr = await process.communicate()
        if process.returncode:
            raise RuntimeError(f'ffmpeg failed for {video_id}: {stderr.decode()}')

        path = CACHE_DIR / f'{video_id}.mp4'
        out_path.replace(path)

    log.info('Muxed %s (%s + %s) in %.2fs', video_id, video, audio, time.monotonic() - start)
    return path


async def evict_expired():
    while True:
        cutoff = time.time() - CACHE_TTL
        for path in CACHE_DIR.glob('*.mp4'):
            if path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
        await asyncio.sleep(60 * 60)


@asynccontextmanager
async def lifespan(_: FastAPI):
    global client
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    client = httpx.AsyncClient(timeout=JOB_TIMEOUT, follow_redirects=True)
    eviction = asyncio.create_task(evict_expired())
    yield
    eviction.cancel()
    await client.aclose()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.api_route('/{video_id}.mp4', methods=['GET', 'HEAD'])
async def get_video(video_id: str, authorization: str = Header('')):
    if not secrets.compare_digest(authorization.encode(), f'Bearer {SECRET}'.encode()):
        raise HTTPException(401)
    if not VIDEO_ID.fullmatch(video_id):
        raise HTTPException(404)

    path = CACHE_DIR / f'{video_id}.mp4'
    if not path.exists():
        job = jobs.get(video_id)
        if job is None:
            job = jobs[video_id] = asyncio.create_task(mux(video_id))
            job.add_done_callback(lambda _: jobs.pop(video_id, None))
        try:
            # Shielded so a timed out request leaves the mux running and cached for the next one
            path = await asyncio.wait_for(asyncio.shield(job), JOB_TIMEOUT)
        except TimeoutError:
            raise HTTPException(504)

    # Explicitly public, Cloudflare doesn't cache responses to requests with an Authorization header otherwise
    return FileResponse(path, media_type='video/mp4', headers={'Cache-Control': f'public, max-age={CACHE_TTL}'})
