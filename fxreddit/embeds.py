"""Embeds for posts linking to other sites."""

import re
from urllib.parse import parse_qs, urlencode, urlsplit

from . import clients
from .markup import Head, Metas
from .parse import RedditPost


async def external_image_embed(post: RedditPost, _link: str, head: Head):
    if post.preview_image_url is not None:
        width, height = (post.resolution.width, post.resolution.height) if post.resolution else (None, None)
        head.image(post.preview_image_url, width, height, 'large')


def player_size(post: RedditPost) -> tuple[int, int]:
    oembed = post.oembed or {}
    width = oembed['width'] if (oembed.get('width') or 0) > 500 else 1280
    height = oembed['height'] if (oembed.get('height') or 0) > 500 else 720
    return width, height


TWITCH_ANCESTORS = [
    'twitter.com',
    'x.com',  # 🤡
    'cards-frame.twitter.com',
    'tweetdeck.twitter.com',
    'discordapp.com',
    'discord.com',
    'ptb.discordapp.com',
    'ptb.discord.com',
    'canary.discordapp.com',
    'canary.discord.com',
    'embedly.com',
    'cdn.embedly.com',
    'facebook.com',
    'www.facebook.com',
    'meta.com',  # 🤡
    'www.meta.com',
    'vk.com',
]


def twitch_clip_slug(hostname: str | None, path: str) -> str | None:
    # https://www.twitch.tv/username/clip/abcd1234
    if hostname == 'www.twitch.tv':
        # The slug is always the part after 'clip/' in the path
        parts = path.split('/')
        if 'clip' in parts and parts.index('clip') + 1 < len(parts):
            return parts[parts.index('clip') + 1]
        return path[1:]
    # https://clips.twitch.tv/abcd1234
    if hostname == 'clips.twitch.tv':
        return path[1:]
    return None


async def twitch_clip_embed(post: RedditPost, link: str, head: Head):
    """Converts the twitch clip link to a video embed url"""
    url = urlsplit(link)
    slug = twitch_clip_slug(url.hostname, url.path)
    if slug is None:
        return

    # The parents are required so the csp allows us to embed the video
    # idk what twitch was thinking on this one my dudes
    params = [('clip', slug), *(('parent', parent) for parent in TWITCH_ANCESTORS)]
    embedding_url = f'https://clips.twitch.tv/embed?{urlencode(params)}'
    width, height = player_size(post)

    head.meta('twitter:card', 'player')
    head.video(embedding_url, width, height, 'text/html')

    oembed = post.oembed or {}
    if oembed.get('thumbnail_url'):
        head.image(oembed['thumbnail_url'], oembed.get('thumbnail_width') or width, oembed.get('thumbnail_height') or height)
    elif post.preview_image_url:
        head.image(post.preview_image_url, width, height)


TWEET_LINK = re.compile(r'^https?://(?:www\.)?(?:twitter|x)\.com/(?:#!/)?([^/]+)/status(?:es)?/([^/]+)$', re.IGNORECASE)


def to_num(value: str | None) -> int | None:
    match = re.match(r'\s*[+-]?\d+', value or '')
    return int(match[0]) if match else None


async def twitter_link_embed(post: RedditPost, link: str, head: Head):
    match = TWEET_LINK.match(link)
    if not match:
        return

    username, id = match.groups()
    response = await clients.web.get(f'https://fxtwitter.com/{username}/status/{id}', headers={'User-Agent': 'Discordbot 2.0'})
    page = Metas(response.text)

    def content(property: str) -> str | None:
        return page.get('property', property)

    description = content('og:description')
    image = content('og:image')
    video = content('og:video')
    title = content('og:title')
    card = content('twitter:card')

    if card:
        head.meta('twitter:card', card)

    if description:
        rich_text = f'{description}\n- {title} on Twitter'
        head.meta('og:description', rich_text)
        head.meta('twitter:description', rich_text)
    else:
        head.meta('og:description', f'{title} on Twitter')
        head.meta('twitter:description', f'{title} on Twitter')

    if image:
        head.image(image, to_num(content('og:image:width')), to_num(content('og:image:height')))

    if video:
        type = content('og:video:type') or 'video/mp4'
        head.video(video, to_num(content('og:video:width')), to_num(content('og:video:height')), type)


def youtube_id(hostname: str | None, path: str, query: str) -> str | None:
    if hostname == 'youtu.be':  # https://youtu.be/abc123
        return path[1:]
    if hostname in ('www.youtube.com', 'youtube.com'):  # https://www.youtube.com/watch?v=abc123
        return parse_qs(query).get('v', [None])[0]
    return None


async def youtube_embed(post: RedditPost, link: str, head: Head):
    """Converts the youtube link to a video embed url"""
    url = urlsplit(link.replace('&amp;', '&', 1))

    # Clip links need another request to extract a proper url for embedding
    if url.path.startswith('/clip/'):
        page = Metas((await clients.web.get(link)).text)
        clip_embed = page.get('name', 'twitter:player')
        thumbnail = page.get('name', 'twitter:image')
        width, height = player_size(post)

        if thumbnail:
            head.image(thumbnail, width, height)
        if clip_embed:
            head.meta('twitter:card', 'player')
            head.video(clip_embed, width, height, 'text/html')
        return

    id = youtube_id(url.hostname, url.path, url.query)
    if not id:
        return

    # Discord doesn't support iframe embeds - use koutube.com API to get direct video stream
    try:
        data = (await clients.web.get(f'https://koutube.com/api/watch?v={id}')).json()
        if data.get('error'):
            raise RuntimeError(data['error'])

        video_url = data.get('playerStreamUrl')
        width = int(data.get('videoWidth') or '1280')
        height = int(data.get('videoHeight') or '720')
        thumbnail_url = data.get('image')

        if video_url:
            head.meta('twitter:card', 'player')
            head.meta('og:video', video_url)
            head.meta('og:video:secure_url', video_url)
            head.meta('og:video:type', 'video/mp4')
            head.meta('og:video:width', str(width))
            head.meta('og:video:height', str(height))
            head.meta('twitter:player', video_url)
            head.meta('twitter:player:width', str(width))
            head.meta('twitter:player:height', str(height))

        head.image(thumbnail_url or f'https://img.youtube.com/vi/{id}/maxresdefault.jpg', width, height)
    except Exception:  # noqa: BLE001
        # Fallback to simple image embed if koutube API fails
        head.meta('twitter:card', 'summary_large_image')
        head.image(f'https://img.youtube.com/vi/{id}/maxresdefault.jpg', 1280, 720)
