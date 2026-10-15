# fxreddit video server

Reddit serves video and audio as separate streams, so embeds of the video file alone have no sound. This server downloads both streams of a `v.redd.it` video and muxes them into one MP4 with ffmpeg (copying the streams, no re-encoding).

`GET /<video id>.mp4` with `Authorization: Bearer <MUX_SECRET>` returns the muxed video.

- Picks the best quality whose estimated size stays under 50 MB, and gives up after 7s with a 504 (Discord drops embeds whose video takes over 10s). A timed out mux keeps running and is cached for the next request.
- Results are cached on disk in `/tmp/mux-cache` for 24 hours.

## Run

```bash
docker build -t fxreddit-video-server .
docker run -d --restart unless-stopped -p 8000:8000 -e MUX_SECRET=<secret> fxreddit-video-server
```

Locally without Docker (needs ffmpeg installed):

```bash
MUX_SECRET=<secret> uv run uvicorn main:app --port 8000
```

## Connect the worker

Set the worker's secrets to the server's public URL and the same secret:

```bash
npx wrangler secret put VIDEO_SERVER_URL      # e.g. https://video.example.com
npx wrangler secret put VIDEO_SERVER_SECRET
```
