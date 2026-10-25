"""Turns Reddit's JSON for a post or comment into a RedditPost."""

import re
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class Resolution:
    width: int
    height: int


@dataclass
class Image:
    url: str
    width: int
    height: int
    caption: str | None = None


@dataclass
class MediaItem:
    kind: Literal['image', 'video']
    url: str
    caption: str | None = None


@dataclass
class RedditPost:
    subreddit: str
    title: str
    author: str
    post_hint: str  # 'image' | 'hosted:video' | 'link' | ...
    url: str
    permalink: str
    description: str
    is_media_only: bool = False
    preview_image_url: str | None = None
    domain: str | None = None
    resolution: Resolution | None = None
    video_url: str | None = None
    video_has_audio: bool = True
    oembed: dict[str, Any] | None = None
    media_metadata: list[Image] = field(default_factory=list)
    poll_data: dict[str, Any] | None = None
    comment: RedditPost | None = None
    # Used by the component embed
    id: str | None = None
    created_utc: float | None = None
    edited: bool = False
    score: int | None = None
    upvote_ratio: float | None = None
    num_comments: int | None = None
    nsfw: bool = False
    spoiler: bool = False
    locked: bool = False
    stickied: bool = False
    flair: str | None = None
    is_original_content: bool = False
    distinguished: str | None = None
    is_submitter: bool = False
    removed: bool = False
    subreddit_icon: str | None = None
    media: list[MediaItem] = field(default_factory=list)  # ordered images and videos, URLs unescaped
    crosspost: RedditPost | None = None


def parse_reddit_post(metadata: dict[str, Any]) -> RedditPost:
    parents = metadata.get('crosspost_parent_list')
    crosspost = parse_reddit_post(parents[0]) if parents else None

    resolution: Resolution | None = None
    post_hint = metadata.get('post_hint') or 'unknown'
    video_url = ((metadata.get('secure_media') or {}).get('reddit_video') or {}).get('fallback_url')
    has_audio = True

    reddit_video = (metadata.get('media') or {}).get('reddit_video')
    preview_images = (metadata.get('preview') or {}).get('images') or []
    if reddit_video is not None:
        resolution = Resolution(reddit_video['width'], reddit_video['height'])
        video_url = reddit_video['fallback_url']
        has_audio = reddit_video['has_audio']
        post_hint = 'hosted:video'
    elif crosspost:
        video_url = crosspost.video_url
        resolution = crosspost.resolution
        post_hint = crosspost.post_hint
        has_audio = crosspost.video_has_audio is True
    elif preview_images:
        source = preview_images[0].get('source')
        resolutions = preview_images[0].get('resolutions') or []
        if source is None and resolutions:
            source = resolutions[-1]
        if source is not None:
            resolution = Resolution(source['width'], source['height'])
    elif metadata.get('thumbnail_width') and metadata.get('thumbnail_height'):
        resolution = Resolution(metadata['thumbnail_width'], metadata['thumbnail_height'])

    media_metadata: list[Image] = []
    gallery_items = (metadata.get('gallery_data') or {}).get('items')
    if metadata.get('media_metadata') is not None and gallery_items is not None:
        for item in gallery_items:
            source = (metadata['media_metadata'].get(item['media_id']) or {}).get('s')
            # Animated images have no 'u', only 'gif' and 'mp4'
            if not source or not (url := source.get('u') or source.get('gif')):
                continue
            media_metadata.append(Image(url, source['x'], source['y'], item.get('caption')))
    elif metadata.get('media_metadata') is not None:
        for value in metadata['media_metadata'].values():
            source = (value or {}).get('s')
            if not source or not (url := source.get('u') or source.get('gif')):
                continue
            media_metadata.append(Image(url, source['x'], source['y']))
    elif crosspost:
        media_metadata.extend(crosspost.media_metadata)

    preview_source = (preview_images[0].get('source') or {}) if preview_images else {}
    # Without a thumbnail, Reddit puts a placeholder like 'self', 'default' or 'nsfw' there
    thumbnail = metadata.get('thumbnail') if (metadata.get('thumbnail') or '').startswith('http') else None
    preview_image_url = first_not_empty(preview_source.get('url'), thumbnail, crosspost and crosspost.preview_image_url)
    sr_detail = metadata.get('sr_detail') or {}

    return RedditPost(
        subreddit=metadata['subreddit'],
        title=metadata.get('title', ''),
        post_hint=post_hint,
        url=metadata.get('url', ''),
        permalink=metadata['permalink'],
        description=get_description(metadata),
        is_media_only=metadata.get('media_only') is True,
        preview_image_url=preview_image_url,
        resolution=resolution,
        video_url=video_url,
        video_has_audio=has_audio,
        oembed=(metadata.get('secure_media') or {}).get('oembed') or (metadata.get('media') or {}).get('oembed'),
        domain=metadata.get('domain'),
        media_metadata=media_metadata,
        author=metadata['author'],
        poll_data=metadata.get('poll_data'),
        id=metadata.get('id'),
        created_utc=metadata.get('created_utc'),
        edited=bool(metadata.get('edited')),
        score=metadata.get('score'),
        upvote_ratio=metadata.get('upvote_ratio'),
        num_comments=metadata.get('num_comments'),
        nsfw=metadata.get('over_18') is True,
        spoiler=metadata.get('spoiler') is True,
        locked=metadata.get('locked') is True,
        stickied=metadata.get('stickied') is True,
        # Drops Reddit emoji shortcodes
        flair=re.sub(r':[A-Za-z0-9_-]+:', '', unescape_html(metadata.get('link_flair_text') or '')).strip() or None,
        is_original_content=metadata.get('is_original_content') is True,
        distinguished=metadata.get('distinguished'),
        is_submitter=metadata.get('is_submitter') is True,
        removed=metadata.get('removed_by_category') is not None,
        subreddit_icon=unescape_html(sr_detail.get('community_icon') or sr_detail.get('icon_img') or '') or None,
        media=get_media(metadata, crosspost),
        crosspost=crosspost,
    )


def unescape_html(text: str) -> str:
    """Reddit escapes &, < and > in JSON strings"""
    text = text.replace('&lt;', '<').replace('&gt;', '>')
    return re.sub('&#x200B;', '', text, flags=re.IGNORECASE).replace('&amp;', '&')


def get_media(metadata: dict[str, Any], crosspost: RedditPost | None) -> list[MediaItem]:
    """All media of the post in display order, images and videos mixed"""
    items: list[MediaItem] = []
    gallery_items = (metadata.get('gallery_data') or {}).get('items')
    reddit_video = (metadata.get('media') or {}).get('reddit_video')
    preview_images = (metadata.get('preview') or {}).get('images') or []
    if metadata.get('media_metadata') is not None and gallery_items is not None:
        for item in gallery_items:
            source = (metadata['media_metadata'].get(item['media_id']) or {}).get('s') or {}
            image = source.get('u') or source.get('gif')
            if source.get('mp4') and not source.get('u'):
                items.append(MediaItem('video', unescape_html(source['mp4']), item.get('caption')))
            elif image:
                items.append(MediaItem('image', unescape_html(image), item.get('caption')))
    elif reddit_video is not None:
        # No audio, compile.py swaps in the muxed video
        items.append(MediaItem('video', reddit_video['fallback_url']))
    elif metadata.get('post_hint') == 'image' and metadata.get('url'):
        items.append(MediaItem('image', unescape_html(metadata['url'])))
    elif preview_images and (preview_images[0].get('source') or {}).get('url'):
        items.append(MediaItem('image', unescape_html(preview_images[0]['source']['url'])))

    return items or (crosspost.media if crosspost else [])


def get_description(metadata: dict[str, Any]) -> str:
    text = metadata.get('selftext') if metadata.get('selftext') is not None else metadata.get('body')
    if text is None:
        return ''
    if metadata.get('poll_data') is not None:
        text = re.sub(r'^\s*\[View Poll\]\([^)]+\)', '', text, count=1, flags=re.IGNORECASE)
    return re.sub(r'^&amp;#x200B;', '', text, count=1).strip()


def first_not_empty(*strings: str | None) -> str | None:
    return next((s for s in strings if s is not None and s.strip()), None)
