"""Entry point: routes, bot detection and error handling."""

import asyncio
import logging
import os
import random
import re
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from html import escape
from urllib.parse import parse_qs, urlsplit, urlunsplit

import httpx
from cachetools import TTLCache
from curl_cffi.requests import AsyncSession
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response

from . import clients, reddit
from .compile import post_to_html
from .constants import CUSTOM_DOMAIN, GITHUB_LINK, RESPONSE_HEADERS
from .markup import Head, http_equiv, redirect_page
from .oembed import decode_oembed, oembed_response
from .parse import RedditPost
from .reddit import ResponseError, clean_spoiler
from .video import JOB_TIMEOUT, evict_expired, get_video

DISCORD_WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL')

log = logging.getLogger('uvicorn.error')
# Successful embeds and share links, like the worker cached Reddit's responses at the edge for a day.
# Cloudflare can't cache the pages since bots and browsers get different responses on the same URL.
cache = TTLCache[str, str](maxsize=10_000, ttl=24 * 60 * 60)


@asynccontextmanager
async def lifespan(_: FastAPI):
    clients.reddit = AsyncSession(impersonate='chrome', headers={'Cookie': reddit.REDDIT_COOKIE or ''})
    clients.web = httpx.AsyncClient(timeout=JOB_TIMEOUT, follow_redirects=True)
    tasks = [asyncio.create_task(evict_expired())]
    if DISCORD_WEBHOOK_URL:
        tasks.append(asyncio.create_task(reddit.check_cookie_forever(DISCORD_WEBHOOK_URL)))
    yield
    for task in tasks:
        task.cancel()
    await clients.reddit.close()
    await clients.web.aclose()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


def get_original_url(url: str, short: bool) -> str:
    location = urlsplit(url)
    target_domain = 'redd.it' if short else 'reddit.com'
    hostname = location.hostname or ''

    if hostname.endswith(CUSTOM_DOMAIN):
        hostname = hostname.replace(hostname if short else CUSTOM_DOMAIN, target_domain, 1)
    else:
        hostname = target_domain

    return urlunsplit(location._replace(scheme='https', netloc=hostname, path=location.path or '/'))


def is_bot(request: Request) -> bool:
    user_agent = request.headers.get('User-Agent', '').lower()
    return 'bot' in user_agent or 'steamchaturllookup' in user_agent


def request_url(request: Request) -> str:
    """The URL as the client sent it, path still percent-encoded like Reddit's links"""
    query = request.scope['query_string'].decode()
    return f'{request.url.scheme}://{request.url.netloc}{request.scope["raw_path"].decode()}' + (f'?{query}' if query else '')


def redirect(url: str, headers: dict[str, str] | None = None) -> HTMLResponse:
    return HTMLResponse(redirect_page(url), status_code=302, headers={**(headers or {}), 'Location': url})


def fallback_redirect(request: Request, _: dict[str, str]) -> Response:
    return redirect(get_original_url(request_url(request), False))


Resolver = Callable[..., Awaitable[RedditPost]]


async def handle_post(request: Request, params: dict[str, str], short: bool, resolver: Resolver) -> Response:
    url = clean_spoiler(request_url(request))
    original_link = get_original_url(url, short)

    headers = dict(RESPONSE_HEADERS)
    if url.startswith('https:'):
        headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'

    if not is_bot(request):  # forcing redirect for browsers
        return redirect(original_link, headers)

    html = cache.get(url)
    if html is None:
        try:
            post = await resolver(params['id'], params.get('name'), params.get('slug'), params.get('ref'))
        except ResponseError as e:
            if e.status == 404:
                return Response('Post not found', status_code=404, headers=headers)
            raise
        html = cache[url] = await post_to_html(post, f'{request.url.scheme}://{request.url.netloc}')

    return Response(html, headers=headers)


async def handle_share(request: Request, _: dict[str, str]) -> Response:
    """Determines the original link by using the Location header"""
    url = clean_spoiler(request_url(request))
    location = cache.get(url)
    if location is None:
        split = urlsplit(url)
        location = await reddit.resolve_share_link(urlunsplit(('', '', split.path, split.query, '')))
        if not location:
            return Response('Post not found', status_code=404)
        cache[url] = location

    # Same post on this server
    target = urlsplit(location)
    port = f':{target.port}' if target.port else ''
    return redirect(urlunsplit(target._replace(netloc=f'{request.url.hostname}{port}')), RESPONSE_HEADERS)


def handle_oembed(request: Request, _: dict[str, str]) -> Response:
    data = parse_qs(request.url.query).get('embed', [None])[-1]
    embed = decode_oembed(data) if data else None
    if embed is None:
        return Response(status_code=404)
    return JSONResponse(oembed_response(embed))


def post_route(short: bool, resolver: Resolver):
    return lambda request, params: handle_post(request, params, short, resolver)


def text(content: str):
    return lambda *_: PlainTextResponse(content)


def compile_route(route: str) -> re.Pattern[str]:
    """Same syntax as the worker's router: :param, :param? for optional, * for anything"""
    pattern = re.sub(r'(/?):(\w+)', r'(\1(?P<\2>[^/]+?))', route).replace('.', r'\.')
    return re.compile(f'^{re.sub(r"(/?)\*", r"(\1.*)?", pattern)}/*$')


Handler = Callable[[Request, dict[str, str]], Response | Awaitable[Response]]


def not_found(*_) -> Response:
    return PlainTextResponse('Not Found', status_code=404)


def handle_head(*_) -> Response:
    # Steam makes a HEAD request to check the content type first
    return HTMLResponse(None)


async def video(request: Request, params: dict[str, str]) -> Response:
    return await get_video(request.method, params['id'], params['file'])


ROUTES: list[tuple[str, str, Handler]] = [
    ('GET', '/', lambda *_: redirect(GITHUB_LINK)),
    # Block all robots / crawlers
    ('GET', '/robots.txt', text('User-agent: *\nDisallow: /')),
    ('GET', '/security.txt', text(f'Contact: {GITHUB_LINK}/issues/new')),
    ('GET', '/blog', fallback_redirect),
    ('GET', '/new', fallback_redirect),
    # Some static files we don't support
    *(('GET', f'/*.{extension}', not_found) for extension in ['ico', 'png', 'jpg', 'jpeg', 'txt', 'xml']),
    # OEmbed encoding endpoint
    ('GET', '/oembed', handle_oembed),
    # Links to posts
    ('GET', '/r/:name/comments/:id/:slug?', post_route(False, reddit.get_subreddit_post)),
    ('GET', '/:id', post_route(True, reddit.get_short_url_post)),
    ('GET', '/gallery/:id', post_route(False, reddit.get_short_url_post)),
    ('GET', '/user/:name/comments/:id/:slug?', post_route(False, reddit.get_profile_post)),
    ('GET', '/u/:name/comments/:id/:slug?', post_route(False, reddit.get_profile_post)),
    # Direct links to comments
    ('GET', '/r/:name/comments/:id/:slug/:ref', post_route(False, reddit.get_subreddit_post)),
    ('GET', '/user/:name/comments/:id/:slug/:ref', post_route(False, reddit.get_profile_post)),
    ('GET', '/u/:name/comments/:id/:slug/:ref', post_route(False, reddit.get_profile_post)),
    # Share links
    ('GET', '/r/:name/s/:id', handle_share),
    ('GET', '/u/:name/s/:id', handle_share),
    ('GET', '/user/:name/s/:id', handle_share),
    # Videos with sound
    ('GET', '/v/:id/:file', video),
    ('HEAD', '/v/:id/:file', video),
    # Untyped links
    ('GET', '/comments/:id/comment/:ref', post_route(False, reddit.get_untyped_post)),
    ('GET', '/comments/:id/:slug/:ref', post_route(False, reddit.get_untyped_post)),
    ('GET', '/comments/:id/:slug?', post_route(False, reddit.get_untyped_post)),
    ('HEAD', '*', handle_head),
    # On missing routes we simply redirect
    ('ALL', '*', fallback_redirect),
]
COMPILED_ROUTES = [(method, compile_route(route), handler) for method, route, handler in ROUTES]


@app.api_route('/{_:path}', methods=['GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'])
async def route(request: Request) -> Response:
    path = request.scope['raw_path'].decode()
    for method, pattern, handler in COMPILED_ROUTES:
        match = pattern.match(path)
        if (method == request.method or method == 'ALL') and match:
            params = {key: value for key, value in match.groupdict().items() if value is not None}
            try:
                response = handler(request, params)
                return await response if isinstance(response, Awaitable) else response
            except Exception as e:  # noqa: BLE001 - every error gets a response, like the worker's catch-all
                return handle_error(request, e)
    return not_found()


def handle_error(request: Request, error: Exception) -> Response:
    if isinstance(error, ResponseError):
        if error.status == 403:
            log.info('Ignoring 403 error from reddit, likely NSFW post.')
            return PlainTextResponse('Forbidden.', status_code=403)
        if error.status == 429:
            log.info('Ignoring rate-limit error.')
            return PlainTextResponse('Rate Limited.', status_code=429)
        if error.status >= 500:
            log.info('Reddit server-side error. Ignoring. Receive status: %s', error)
            return PlainTextResponse('Reddit server side error.', status_code=error.status)
    elif reddit.is_timeout(error):
        return PlainTextResponse('Reddit Timeout.', status_code=502)

    log.exception('Failed to handle %s', request.url, exc_info=error)

    head = Head()
    head.elements.append(http_equiv(get_original_url(request_url(request), False)))
    # If a post consistently fails to embed, we show an error embed (10% chance of happening, to avoid caching errors)
    show_embed = random.random() < 0.1
    if show_embed:
        head.meta('og:description', f'Failed to parse reddit post, please report bug!\n\n{GITHUB_LINK}/issues/new')
        head.meta('theme-color', '#e3242b')
    body = f'<body><h1>Internal Server Error</h1><p>{escape(str(error))}</p></body>'
    return HTMLResponse(f'<html>{head}{body}</html>', status_code=200 if show_embed else 500)
