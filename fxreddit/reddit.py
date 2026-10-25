"""Fetches posts from Reddit's JSON API."""

import asyncio
import logging
import os
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from . import clients
from .constants import REDDIT_BASE_URL, REDDIT_SHORT_URL
from .parse import RedditPost, parse_reddit_post

# Since May 2026, Reddit rejects unauthenticated .json requests with 403.
# Requests are authenticated with the session cookie of a logged-in account ("reddit_session=..."),
# and only pass when they come from a client that looks like a browser (see clients.py).
REDDIT_COOKIE = os.environ.get('REDDIT_COOKIE')
COOKIE_CHECK_INTERVAL = 6 * 60 * 60

log = logging.getLogger('uvicorn.error')


class ResponseError(Exception):
    def __init__(self, status: int, error: str):
        super().__init__(f'{status}: {error}')
        self.status = status


def clean_spoiler(text: str) -> str:
    """Discord spoilers wrap links in ||, which can end up at the end of the path"""
    return text.removesuffix('||')


def find_comment(children: list[dict[str, Any]], id: str) -> dict[str, Any] | None:
    for child in children:
        data = child['data']
        if not id or data.get('id') == id:
            return data

        replies = data.get('replies')
        comment = find_comment(replies['data']['children'], id) if replies else None
        if comment:
            return comment

    return None


async def get_post(url: str, comment_ref: str | None = None) -> RedditPost:
    split = urlsplit(url)
    # sr_detail adds the subreddit icon used by the component embed.
    # limit skips the comment tree, a linked comment is still returned as the first child.
    query = '&'.join(filter(None, [split.query, 'sr_detail=1', 'limit=1']))
    response = await clients.reddit.get(urlunsplit(split._replace(query=query)), timeout=2)
    if not response.ok:
        raise ResponseError(response.status_code, response.reason)

    listings = response.json()
    data = listings[0]['data']['children'][0]['data'] if isinstance(listings, list) and listings and listings[0]['data']['children'] else None
    if data is None:
        raise ResponseError(404, 'Not Found')

    post = parse_reddit_post(data)
    if comment_ref:
        for listing in listings:
            comment = find_comment(listing['data']['children'], comment_ref)
            if comment:
                post.comment = parse_reddit_post(comment)
                break

    return post


def get_post_url(type: str | None, id: str, subreddit: str | None = None, slug: str | None = None, comment_ref: str | None = None) -> str:
    url = REDDIT_BASE_URL
    if type:
        url += f'/{type}'
        if subreddit:
            url += f'/{subreddit}'

    if slug and comment_ref:
        return f'{url}/comments/{id}/{slug}/{clean_spoiler(comment_ref)}.json'
    if slug:
        return f'{url}/comments/{id}/{clean_spoiler(slug)}.json'
    if comment_ref:
        return f'{url}/comments/{id}/comment/{clean_spoiler(comment_ref)}.json'
    # Without a slug, /r/<sub>/<id>.json redirects to a URL with the raw title (breaks on non-ASCII titles and drops the query),
    # the ids are global so this needs no subreddit or user
    return f'{REDDIT_BASE_URL}/comments/{clean_spoiler(id)}.json'


async def get_subreddit_post(id: str, subreddit: str | None = None, slug: str | None = None, ref: str | None = None) -> RedditPost:
    return await get_post(get_post_url('r', id, subreddit, slug, ref), ref)


async def get_profile_post(id: str, user: str | None = None, slug: str | None = None, ref: str | None = None) -> RedditPost:
    return await get_post(get_post_url('user', id, user, slug, ref), ref)


async def get_short_url_post(id: str, *_: str | None) -> RedditPost:
    response = await clients.reddit.get(f'{REDDIT_SHORT_URL}/{id}')
    return await get_post(f'{response.url}.json')


async def get_untyped_post(id: str, subreddit: str | None = None, slug: str | None = None, ref: str | None = None) -> RedditPost:
    return await get_post(get_post_url(None, id, subreddit, slug, ref), ref)


async def resolve_share_link(path: str) -> str | None:
    """The post a share link (/r/<sub>/s/<id>) points to, from Reddit's redirect"""
    response = await clients.reddit.get(f'{REDDIT_BASE_URL}{clean_spoiler(path)}', allow_redirects=False)
    return response.headers.get('Location')


async def check_cookie_forever(webhook_url: str):
    """Alerts on Discord when the Reddit cookie stops working"""
    while True:
        try:
            await check_cookie(webhook_url)
        except Exception:
            log.exception('Reddit cookie check failed')
        await asyncio.sleep(COOKIE_CHECK_INTERVAL)


async def check_cookie(webhook_url: str):
    # /api/me.json answers 200 for a logged-in session and 403 otherwise.
    # Other statuses (5xx, timeouts) are Reddit outages and don't say anything about the cookie.
    problem = None
    if not REDDIT_COOKIE:
        problem = 'REDDIT_COOKIE is not set'
    else:
        response = await clients.reddit.get(f'{REDDIT_BASE_URL}/api/me.json', timeout=5)
        if response.status_code == 403:
            problem = 'Reddit rejected REDDIT_COOKIE (403), the session has expired or been revoked'

    if problem:
        log.warning('Reddit cookie check failed: %s', problem)
        await clients.web.post(webhook_url, json={
            'content': f'⚠️ **fxreddit**: {problem}. Post embeds fail with 403 until it is replaced and the server restarted.',
        })


def is_timeout(error: Exception) -> bool:
    from curl_cffi.requests.exceptions import Timeout
    return isinstance(error, (Timeout, httpx.TimeoutException, TimeoutError))
