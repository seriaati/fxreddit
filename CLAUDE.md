# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FixReddit (rxddit.com) is a Cloudflare Worker service that proxies Reddit links and transforms them into rich Open Graph and Twitter Card embeds for services like Discord. The service handles various Reddit post types (images, videos, galleries, polls, external links) and provides specialized handling for embedded content from YouTube, Twitter, Twitch, and other platforms.

## Development Commands

### Local Development
```bash
pnpm start              # Start local development server with wrangler dev
```

### Deployment
```bash
pnpm run deploy         # Deploy to Cloudflare Workers
```

### Code Quality
```bash
npx eslint .            # Run ESLint (4-space indent, single quotes, semicolons required)
npx tsc --noEmit        # Type check without emitting files
```

## Architecture

### Request Flow

1. **Entry Point** ([src/worker.ts](src/worker.ts)): Main worker event listener and router configuration
2. **Route Handlers** ([src/endpoints/](src/endpoints/)): Handle different URL patterns
3. **Reddit Data Fetching** ([src/endpoints/post.ts](src/endpoints/post.ts)): Fetch posts from Reddit's JSON API
4. **Data Parsing** ([src/reddit/parse.ts](src/reddit/parse.ts)): Transform Reddit API responses into normalized `RedditPost` objects
5. **HTML Generation** ([src/reddit/compile.ts](src/reddit/compile.ts)): Generate HTML with Open Graph/Twitter Card meta tags

### Key Architectural Patterns

#### Bot Detection and Redirection
The service distinguishes between bots and regular browsers:
- **Bots** (detected via User-Agent): Receive HTML with Open Graph/Twitter Card meta tags
- **Browsers**: Redirected to the original Reddit URL
- Detection logic in [src/util.ts](src/util.ts):`isBot()`

#### Reddit API Interaction
- Uses Reddit's public JSON API (append `.json` to any Reddit URL)
- Handles various URL patterns: subreddit posts, user posts, short links, share links, comments
- Request timeout: 2000ms for posts, 5000ms for videos
- See `get_post()` in [src/endpoints/post.ts](src/endpoints/post.ts)

#### Post Type Handling
The `post_hint` field determines embed behavior:
- `image`: Single image posts
- `hosted:video`: Reddit-hosted videos (attempts to find version with audio)
- `link`: External links, may have domain-specific handlers

Domain-specific handlers in [src/reddit/compile.ts](src/reddit/compile.ts):`getDomainHandler()`:
- YouTube: Converts to embed iframe URL
- Twitch: Handles clips specifically
- Twitter/X: Custom embed handling
- Imgur: Image embed handling

#### Video Processing
Reddit videos often lack audio in the primary stream. The service:
1. Fetches the post's HTML page from reddit.com
2. Extracts `packaged-media-json` attribute containing video variants
3. Selects the highest quality variant (last in array)
4. Provides a `/v/...` proxy endpoint that redirects to current video URL

See `get_packaged_video()` in [src/util.ts](src/util.ts) and [src/endpoints/video.ts](src/endpoints/video.ts).

#### Gallery Handling
- Galleries combine `media_metadata` and `gallery_data.items` from Reddit API
- Discord limitation: Maximum 4 images shown in embed
- Gallery posts include "🖼️ Gallery: N Images" indicator
- Images processed in order specified by `gallery_data.items`

#### Error Handling Strategy
- **403 Forbidden**: Silently handled (likely NSFW content)
- **429 Rate Limit**: Logged and returns rate limit response
- **5xx Server Errors**: Passed through from Reddit
- **TimeoutError**: Returns 502 Gateway Timeout
- **Other Errors**: 10% chance of showing error embed (to avoid caching errors), 90% returns 500

See error handling in [src/worker.ts](src/worker.ts) lines 72-127.

### HTML Meta Tag Extensions

Custom prototype extensions in [src/html.ts](src/html.ts) add helper methods to `HTMLElement`:
- `.meta(property, content)`: Add Open Graph/Twitter meta tag
- `.image(url, width, height, type)`: Add image meta tags
- `.video(url, width, height, type)`: Add video meta tags

These methods handle both Open Graph (`og:*`) and Twitter Card (`twitter:*`) tags simultaneously.

## File Structure

```
src/
├── worker.ts              # Entry point, router, error handling
├── constants.ts           # Configuration (URLs, user agents, headers)
├── types.d.ts            # Global types
├── util.ts               # Utilities (bot detection, URL conversion, video fetching)
├── html.ts               # HTMLElement prototype extensions
├── cache.ts              # Cloudflare cache configuration
├── response_error.ts     # Custom error class
├── endpoints/
│   ├── post.ts           # Main post handling logic
│   ├── share.ts          # Handle /r/.../s/... share links
│   └── video.ts          # Video proxy endpoint
├── reddit/
│   ├── types.d.ts        # Reddit API response types
│   ├── parse.ts          # Transform API responses to RedditPost
│   ├── compile.ts        # Generate HTML from RedditPost
│   └── oembed.ts         # OEmbed endpoint
└── embeds/
    ├── youtube.ts        # YouTube embed handler
    ├── twitch.ts         # Twitch clip embed handler
    ├── twitter.ts        # Twitter/X embed handler
    └── image_host.ts     # External image host handler
```

## Important Implementation Notes

### Cloudflare Workers Environment
- This is a Cloudflare Worker, not a Node.js application
- Uses Web APIs (fetch, AbortSignal, etc.) rather than Node.js APIs
- No filesystem access
- Limited to 50ms CPU time per request
- Type definitions: `@cloudflare/workers-types`

### TypeScript Configuration
- Target: ES2021
- Module: ES2022
- Strict mode enabled
- `noEmit: true` (Wrangler handles bundling)
- Module resolution: Bundler

### Dependencies
- `itty-router`: Lightweight router for Cloudflare Workers
- `node-html-parser`: HTML parsing/generation
- `remeda`: Utility functions (type-safe alternatives to lodash)
- `@borderless/worker-sentry`: Sentry error reporting

### Code Style
- 4-space indentation
- Single quotes
- Semicolons required
- See [.eslintrc.yml](.eslintrc.yml)

### Constants and Configuration
All URLs and headers defined in [src/constants.ts](src/constants.ts):
- `CUSTOM_DOMAIN`: rxddit.com
- `REDDIT_BASE_URL`: https://www.reddit.com
- Response cache: 24 hours (86400s)

### Sentry Integration
The `SENTRY_ENDPOINT` variable must be provided at deployment time (not in version control). Error reporting captures:
- Request URL, method, headers
- User IP (from cf-connecting-ip header)
- Error tags and context

## Common Pitfalls

### Spoiler URLs
Reddit URLs can end with `||` for spoiler content. Always use `cleanSpoiler()` from [src/util.ts](src/util.ts) when processing URL parameters.

### Comment Handling
Comments are embedded in the same JSON response as the post. The `findComment()` function recursively searches the comment tree to locate specific comment IDs. Comments are attached to posts as `post.comment` in the `RedditPost` structure.

### Poll Data
Polls may have `null` options if data is broken. Always check `isNonNullish(options)` before processing. See [src/reddit/compile.ts](src/reddit/compile.ts):`compilePollData()`.

### Video URLs
Reddit video URLs expire. The `/v/...` proxy endpoint exists to provide stable URLs that redirect to current video URLs. Never use video URLs directly in embeds; always use the proxy path.

### Crosspost Handling
Crossposts inherit media from the parent post. The parser in [src/reddit/parse.ts](src/reddit/parse.ts) recursively parses `crosspost_parent_list[0]` and falls back to parent data when the crosspost lacks media.
