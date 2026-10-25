# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FixReddit is a Python (FastAPI) service, hosted on a VPS behind Cloudflare, that proxies Reddit links and transforms them into rich Open Graph and Twitter Card embeds (plus Discord component embeds) for services like Discord. It handles various Reddit post types (images, videos, galleries, polls, external links) and provides specialized handling for embedded content from YouTube, Twitter, Twitch, and Imgur.

It was a Cloudflare Worker in TypeScript until Reddit started blocking requests that don't come from a browser (see "Reddit API Interaction" below). The Python port renders byte-identical HTML.

## Development Commands

```bash
REDDIT_COOKIE='reddit_session=...' uv run uvicorn fxreddit.main:app --port 8000   # Local server (needs ffmpeg)
uvx ruff check fxreddit                                                          # Lint
uvx pyright --pythonpath .venv/bin/python fxreddit                               # Type check
docker build -t fxreddit .                                                       # Production image
```

## Architecture

### Request Flow

1. **Entry Point** ([fxreddit/main.py](fxreddit/main.py)): Routes, bot detection, embed cache, error handling
2. **Reddit Data Fetching** ([fxreddit/reddit.py](fxreddit/reddit.py)): Fetch posts from Reddit's JSON API, resolve share and short links
3. **Data Parsing** ([fxreddit/parse.py](fxreddit/parse.py)): Transform Reddit API responses into `RedditPost` dataclasses
4. **HTML Generation** ([fxreddit/compile.py](fxreddit/compile.py)): Generate HTML with Open Graph/Twitter Card meta tags
5. **Component Embed** ([fxreddit/component_embed.py](fxreddit/component_embed.py)): Discord component embed JSON, must stay within 3000 bytes

### Routing
`main.py` matches the raw (percent-encoded) path against `ROUTES` in order, with the same syntax as the worker's itty-router (`:param`, `:param?`, `*`, trailing slashes allowed). Everything goes through one catch-all FastAPI route.

### Bot Detection and Redirection
- **Bots** (User-Agent contains `bot` or `SteamChatURLLookup`): Receive HTML with meta tags
- **Browsers**: Redirected (302) to the original Reddit URL

Because both get different responses on the same URL, Cloudflare must not cache the pages. `main.py` caches rendered embeds and share link targets in memory for 24 hours instead.

### Reddit API Interaction
- Uses Reddit's JSON API (append `.json` to a post URL), with `sr_detail=1` (subreddit icon) and `limit=1` (skip the comment tree)
- Since May 2026, Reddit rejects unauthenticated `.json` requests, and logged-in requests unless the client looks like a browser. [fxreddit/clients.py](fxreddit/clients.py) has two clients: `clients.reddit` (curl_cffi, impersonating Chrome's TLS fingerprint, sending `REDDIT_COOKIE`) for every Reddit request, and `clients.web` (httpx) for everything else
- `reddit.check_cookie_forever()` alerts `DISCORD_WEBHOOK_URL` when `/api/me.json` rejects the cookie
- Post fetch timeout: 2s

### Post Type Handling
The `post_hint` field determines embed behavior:
- `image`: Single image posts
- `hosted:video`: Reddit-hosted videos, linked through `/v/...` for sound
- `link` and others: External links, may have domain-specific handlers in `compile.py:get_domain_handler()` (implementations in [fxreddit/embeds.py](fxreddit/embeds.py)):
  - YouTube: Direct video stream through the koutube.com API, clips through the clip page's player
  - Twitch: Clip embed player
  - Twitter/X: Content from fxtwitter.com
  - Imgur: Image embed

### Video Processing
Reddit serves video and audio as separate DASH streams, so `fallback_url` never has sound. [fxreddit/video.py](fxreddit/video.py) muxes them:
1. For videos with `has_audio`, the embed links `/v/<video id>/<fallback file>`
2. The server downloads both streams and muxes them with ffmpeg (stream copy), cached on disk for 24h, served directly since Discord doesn't play videos behind redirects
3. If muxing fails or takes over 7s, it proxies the silent `v.redd.it/<id>/<fallback file>` uncached instead (Discord gives up after 10s)

### Gallery Handling
- Galleries combine `media_metadata` and `gallery_data.items` from Reddit API, in the order of `gallery_data.items`
- Discord shows at most 4 images from OG tags, galleries include a "🖼️ Gallery: N Images" indicator

### Error Handling Strategy
In `main.py:handle_error()`:
- **403 Forbidden**: Silently handled (likely NSFW content)
- **429 Rate Limit**: Returns a rate limit response
- **5xx Server Errors**: Passed through from Reddit
- **Timeouts**: Returns 502
- **Other Errors**: 10% chance of showing an error embed (to avoid caching errors), 90% returns 500

### HTML Generation
[fxreddit/markup.py](fxreddit/markup.py) `Head` collects the `<head>` elements:
- `.meta(property, content)`: Add an Open Graph/Twitter meta tag
- `.image(url, width, height, type)` / `.video(url, width, height, type)`: Add both `og:*` and `twitter:*` tags

Attribute values only escape quotes (Reddit's JSON already escapes `&`, `<` and `>`) and drop backslashes, matching the node-html-parser output of the worker version.

## Important Implementation Notes

- Python 3.14, dependencies managed with uv
- Code style: 4-space indentation, single quotes
- `CUSTOM_DOMAIN` (rxddit.com) in [fxreddit/constants.py](fxreddit/constants.py) is still upstream's domain, used in the oEmbed link

## Common Pitfalls

### Spoiler URLs
Reddit URLs can end with `||` for spoiler content. Always use `clean_spoiler()` from [fxreddit/reddit.py](fxreddit/reddit.py) when processing URL parameters.

### Comment Handling
Comments are embedded in the same JSON response as the post. `find_comment()` recursively searches the comment tree to locate specific comment IDs. Comments are attached to posts as `post.comment`.

### Poll Data
Polls may have `None` options if data is broken. Always check before processing. See `compile.py:compile_poll_data()`.

### JavaScript Semantics
The port keeps the worker's output: `component_embed.js_round()` rounds halves up like `Math.round`, and `\w` in regexes is spelled `[A-Za-z0-9_]` since JavaScript's is ASCII-only.

### Crosspost Handling
Crossposts inherit media from the parent post. The parser recursively parses `crosspost_parent_list[0]` and falls back to parent data when the crosspost lacks media.
