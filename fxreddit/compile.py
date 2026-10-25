"""Generates the embed page of a post with Open Graph and Twitter Card tags."""

from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlsplit

from .component_embed import compile_component_embed
from .embeds import (
    external_image_embed,
    twitch_clip_embed,
    twitter_link_embed,
    youtube_embed,
)
from .markup import Head
from .oembed import encode_oembed
from .parse import MediaItem, RedditPost
from .video import muxed_video_url

IMAGE_EXTENSIONS = ['png', 'jpg', 'jpeg', 'gif']

Handler = Callable[[RedditPost, str, Head], Awaitable[None]]


def get_domain_handler(domain: str | None, url: str | None) -> tuple[Handler, str] | None:
    """The handler for links to this domain, and the og:type it produces"""
    match domain:
        case 'youtu.be' | 'www.youtube.com' | 'youtube.com':
            return youtube_embed, 'video.other'
        case 'twitch.tv' | 'www.twitch.tv' | 'clips.twitch.tv':
            return (twitch_clip_embed, 'video.other') if url and 'clip' in url else None
        case 'twitter.com' | 'x.com':
            return twitter_link_embed, 'summary'
        case 'imgur.com' | 'i.imgur.com':
            return external_image_embed, 'article'
        case _:
            return None


async def post_to_html(post: RedditPost, origin: str) -> str:
    head = Head()
    original_url = f'https://www.reddit.com{post.permalink}'
    author_name = f'u/{post.author} on r/{post.subreddit}'
    width, height = (post.resolution.width, post.resolution.height) if post.resolution else (None, None)

    head.meta('og:title', author_name)
    head.meta('twitter:title', author_name)
    head.meta('twitter:creator', post.title)

    head.append('link', {
        'rel': 'alternate',
        'type': 'application/json+oembed',
        'title': author_name,
        'href': encode_oembed({
            'type': 'link',
            'author_name': post.title,
            'author_url': original_url,
            'provider_name': 'rxddit.com',
            'version': '1.0',
        }),
    })

    head.append('link', {'rel': 'canonical', 'href': original_url})
    head.meta('og:url', original_url)

    head.meta('og:site_name', 'rxddit.com')
    head.meta('twitter:site', 'rxddit.com')
    head.meta('theme-color', '#ff4500')

    description_text = post.description
    description_status = []

    type = 'object'
    embed_media = post.media
    embed_supported = True

    match post.post_hint:
        case 'image':
            type = 'photo'
            head.image(post.url, width, height, 'large')
        case 'hosted:video':
            type = 'video.other'

            # Reddit's own video file has no sound, so prefer the muxed one when there is audio to add
            video_url = (muxed_video_url(origin, post.video_url) if post.video_has_audio else None) or post.video_url or post.url
            head.video(video_url, width, height)
            embed_media = [MediaItem('video', video_url)]
        case _:
            domain_handler = get_domain_handler(post.domain, post.url)
            if domain_handler:
                handler, type = domain_handler
                await handler(post, post.url, head)
                handler_media = get_handler_media(head)
                if handler_media is None:
                    # An iframe player can't go in a component embed, keep the playable OG card instead
                    embed_supported = False
                elif handler_media:
                    embed_media = handler_media
            elif post.media_metadata:
                head.meta('twitter:card', 'summary_large_image')
                amount = len(post.media_metadata)

                if amount > 1:
                    description_status.append(f'🖼️ Gallery: {amount} Images')

                index = 1
                for image in post.media_metadata:
                    head.image(image.url, image.width, image.height)
                    if image.caption:
                        head.meta('twitter:image:alt', image.caption)
                        head.meta('og:image:alt', image.caption)
                    elif amount > 1:
                        head.meta('twitter:image:alt', f'Image {index} of {amount}')
                        head.meta('og:image:alt', f'Image {index} of {amount}')
                        index += 1
            elif post.oembed:
                head.image(post.oembed.get('thumbnail_url', ''), None, None, 'large' if post.is_media_only else 'thumbnail')
                description_text += post.oembed.get('title', '')
            elif post.preview_image_url:
                head.image(post.preview_image_url, width, height, 'large' if post.is_media_only else 'thumbnail')
            elif post.url.startswith('https://'):
                path = urlsplit(post.url).path
                if any(path.endswith(f'.{extension}') for extension in IMAGE_EXTENSIONS):
                    head.image(post.url, width, height, 'large')
                elif path.endswith('.mp4'):
                    head.video(post.url)

    head.meta('og:type', type)

    # Discord renders this instead of the OG tags, which remain the fallback
    component_embed = compile_component_embed(post, embed_media) if embed_supported else None
    if component_embed:
        head.append('script', {'id': 'discord:component-embed', 'type': 'application/json'}, component_embed)

    if post.comment and post.comment.author:
        author, comment = post.comment.author, post.comment.description
        comment_text = f'Comment by u/{author}' + (f':\n{comment}' if comment else '')
        if len(comment_text) < 1000:
            description_text = f'{comment_text}\n\n---- Original Post ----\n\n{description_text}'
        else:
            description_text = comment_text

    poll_description = compile_poll_data(post.poll_data) if post.poll_data is not None else ''

    # Set the description based on the post content and status
    description = '\n\n'.join([' '.join(description_status), description_text, poll_description]).strip()
    if description:
        head.meta('og:description', description)
        head.meta('twitter:description', description)

    return f'<html>{head}</html>'


def get_handler_media(head: Head) -> list[MediaItem] | None:
    """The media a domain handler put into the OG tags, or None if it is a player that only works as an iframe"""
    video = head.content('og:video')
    if video:
        return [MediaItem('video', video)] if head.content('og:video:type') == 'video/mp4' else None
    image = head.content('og:image')
    return [MediaItem('image', image)] if image else []


def compile_poll_data(poll: dict[str, Any]) -> str:
    options = poll.get('options')
    if options is None:
        return ''

    total = poll['total_vote_count']
    max_votes = max((o['vote_count'] for o in options if o.get('vote_count') is not None), default=0)
    answers = []
    for option in options:
        votes = option.get('vote_count')
        decoration = ' 🥇' if votes == max_votes else ''
        if votes is not None:
            answers.append(f'{option["text"]} ({votes} votes)\n{poll_answer_bar(votes, total)}{decoration}')
        else:
            answers.append(f'- {option["text"]}')

    return f'📊 Poll:\n\n{"\n".join(answers)}\n\nTotal Votes: {total}'


def poll_answer_bar(votes: int, total_votes: int) -> str:
    if not total_votes:
        return ''
    percentage = min(votes / total_votes, 1.0)
    return '\u2587' * int(20 * percentage)
