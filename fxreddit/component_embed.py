"""Discord component embed: https://discord.com/developers/docs/link-previews/component-embeds"""

import json
import math
import re
import time
from dataclasses import dataclass
from typing import Any

from .constants import REDDIT_BASE_URL
from .parse import MediaItem, RedditPost, unescape_html

# The serialized payload must stay within 3000 bytes, otherwise Discord silently falls back to the OG tags.
MAX_BYTES = 3000
GALLERY_LIMITS = [10, 4, 1]  # 10 is the maximum across the whole embed, fewer when the media URLs don't fit
MIN_BODY = 200  # below this, the context is crowding out the main text
ACCENT_COLOR = 0xFF4500


@dataclass
class Limits:
    reply: int
    quote: int


LIMITS = [Limits(150, 300), Limits(100, 150), Limits(50, 80)]

Component = dict[str, Any]


def user_url(user: str) -> str:
    return f'{REDDIT_BASE_URL}/user/{user}'


def subreddit_url(subreddit: str) -> str:
    return f'{REDDIT_BASE_URL}/r/{subreddit}'


def short_url(id: str | None) -> str:
    return f'https://redd.it/{id}'


def format_count(n: int | None) -> str:
    return f'{n or 0:,}'


def timestamp(seconds: float | None, style: str) -> str:
    return f'<t:{math.floor(seconds or 0)}:{style}>'


def js_round(x: float) -> int:
    """Rounds halves up like JavaScript's Math.round, Python's round() rounds them to even"""
    return math.floor(x + 0.5)


def escape_markdown(text: str) -> str:
    text = re.sub(r'([\\*_~`|\[\]])', r'\\\1', text)
    return re.sub(r'^([>#-])', r'\\\1', text, flags=re.MULTILINE)


def cut(text: str, n: int) -> str:
    """Cuts to n code points, never leaving half a [text](url) link behind"""
    if len(text) <= n:
        return text
    return re.sub(r'\[[^\]]*(\]\([^)]*)?\Z', '', text[:n]).rstrip() + '…'


def link_names(text: str) -> str:
    """Links u/ and r/ mentions"""
    return re.sub(
        r'(^|[^A-Za-z0-9_/])/?(u|r)/([A-Za-z0-9_-]{2,21})',
        lambda m: f'{m[1]}[{m[2]}/{m[3]}]({user_url(m[3]) if m[2] == "u" else subreddit_url(m[3])})',
        text,
    )


def reddit_markdown(text: str) -> str:
    """Reddit bodies are already Markdown: keep it, convert Reddit-only syntax and link u/ and r/"""
    parts = re.split(r'(\[[^\]]*\]\([^)]*\)|https?://\S+)', unescape_html(text))  # odd indices are links, left untouched
    for i in range(0, len(parts), 2):
        part = re.sub(r'>!(.+?)!<', r'||\1||', parts[i])
        part = re.sub(r'^#{1,6}\s+(.+)$', r'**\1**', part, flags=re.MULTILINE)
        parts[i] = link_names(part)
    return re.sub(r'\n{3,}', '\n\n', ''.join(parts))


def quote(text: str) -> str:
    return '\n'.join(f'> {re.sub(r"^>\s?", "", line)}' for line in text.split('\n'))


def badges(post: RedditPost) -> list[str]:
    result = []
    if post.is_submitter:
        result.append('🎤 OP')
    if post.distinguished == 'moderator':
        result.append('🛡️ Mod')
    if post.is_original_content:
        result.append('OC')
    if post.flair:
        result.append(f'🏷️ {escape_markdown(cut(post.flair, 40))}')
    return result


def poll_text(poll: dict[str, Any]) -> str | None:
    options = poll.get('options')
    if options is None:
        return None
    total = poll['total_vote_count']
    lines = [
        f'- {escape_markdown(o["text"])} — **{format_count(o["vote_count"])}** ({js_round(100 * o["vote_count"] / max(total, 1))}%)'
        if o.get('vote_count') is not None
        else f'- {escape_markdown(o["text"])}'
        for o in options
    ]
    end = poll['voting_end_timestamp']
    state = 'ended' if end < time.time() * 1000 else 'ends'
    return f'📊 **Poll** · {format_count(total)} votes · {state} {timestamp(end / 1000, "R")}\n' + '\n'.join(lines)


def separator(divider: bool, spacing: int = 2) -> Component:
    return {'type': 14, 'divider': divider, 'spacing': spacing}


def text(content: str) -> Component:
    return {'type': 10, 'content': content}


def block(texts: list[str], thumbnail: str | None = None) -> list[Component]:
    if not thumbnail:
        return [text(t) for t in texts]
    return [{'type': 9, 'components': [text(t) for t in texts], 'accessory': {'type': 11, 'media': {'url': thumbnail}}}]


def compose(post: RedditPost, media: list[MediaItem], max_gallery: int, limits: Limits, body_length: int) -> str:
    comment = post.comment
    main = comment or post
    components: list[Component] = []

    # Community icon, community and author, reply context, title and body
    author = ' · '.join([f'[u/{escape_markdown(main.author)}]({user_url(main.author)})', *badges(main)])
    texts = [f'## [r/{post.subreddit}]({subreddit_url(post.subreddit)})\n-# {author}']
    if comment:
        title = f'### {escape_markdown(cut(unescape_html(post.title), limits.reply))}'
        texts.append(f'-# ↩️ Replying to **[u/{escape_markdown(post.author)}]({short_url(post.id)})**\n{quote(title)}')
        texts.append(cut(reddit_markdown(comment.description), body_length) or '\u200b')
    else:
        body = cut(reddit_markdown(post.description), body_length)
        title = f'### {escape_markdown(unescape_html(post.title))}'
        texts.append(f'{title}\n{body}' if body else title)
    components.extend(block(texts, post.subreddit_icon))

    poll = poll_text(post.poll_data) if not comment and post.poll_data else None
    if poll:
        components.extend([separator(False), text(poll)])

    # Media gallery, comment links show the post's media as well
    if media:
        spoiler = post.nsfw or post.spoiler
        items = []
        for item in media[:max_gallery]:
            entry: Component = {'media': {'url': item.url}}
            if item.caption:
                entry['description'] = cut(item.caption, 200)
            if spoiler:
                entry['spoiler'] = True
            items.append(entry)
        components.extend([separator(False), {'type': 12, 'items': items}])

    # Crosspost as the quoted post, its media is already in the gallery since crossposts inherit it
    crosspost = post.crosspost
    if crosspost and not comment:
        components.append(separator(True))
        if crosspost.removed or crosspost.author == '[deleted]':
            components.append(text('-# 🔀 Original post is unavailable'))
        else:
            by = (
                f'**[r/{crosspost.subreddit}]({short_url(crosspost.id)})** · '
                f'[u/{escape_markdown(crosspost.author)}]({user_url(crosspost.author)}) · {timestamp(crosspost.created_utc, "d")}'
            )
            body = f'\n{cut(reddit_markdown(crosspost.description), limits.quote)}' if crosspost.description else ''
            quoted = (
                f'{quote(f"**{escape_markdown(cut(unescape_html(crosspost.title), 150))}**{body}")}\n'
                f'> -# ⬆️ {format_count(crosspost.score)} · 💬 {format_count(crosspost.num_comments)}'
            )
            components.extend(block([f'-# 🔀 Crossposted from\n{by}', quoted], crosspost.subreddit_icon))

    # Footer and buttons
    ratio = f' ({js_round(post.upvote_ratio * 100)}%)' if not comment and post.upvote_ratio is not None else ''
    footer = [f'⬆️ **{format_count(main.score)}**{ratio}']
    if not comment:
        footer.append(f'💬 **{format_count(post.num_comments)}**')
    footer.append(timestamp(main.created_utc, 'f'))
    if main.edited:
        footer.append('✏️ Edited')
    if post.nsfw:
        footer.append('🔞 NSFW')
    if post.spoiler:
        footer.append('⚠️ Spoiler')
    if post.locked:
        footer.append('🔒 Locked')
    if post.stickied:
        footer.append('📌 Pinned')
    if len(media) > max_gallery:
        footer.append(f'🖼️ {max_gallery} of {len(media)}')

    # Slug-free links, a CJK slug costs 9 bytes per character once percent-encoded
    link = (
        f'{REDDIT_BASE_URL}/r/{post.subreddit}/comments/{post.id}/comment/{comment.id}/'
        if comment
        else f'{REDDIT_BASE_URL}/r/{post.subreddit}/comments/{post.id}/'
    )
    components.extend([
        separator(True),
        text(' · '.join(footer)),
        separator(False, 1),
        {
            'type': 1,
            'components': [
                {'type': 2, 'style': 5, 'label': 'Open comment' if comment else 'Open post', 'url': link},
                {'type': 2, 'style': 5, 'label': cut(f'u/{main.author}', 80), 'url': user_url(main.author)},
            ],
        },
    ])

    container: Component = {'type': 17, 'accent_color': ACCENT_COLOR}
    if post.nsfw:
        container['spoiler'] = True
    container['components'] = components
    # Escaped so the JSON can never close the surrounding <script> tag
    return json.dumps({'component': container}, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')


def compile_component_embed(post: RedditPost, media: list[MediaItem] | None = None) -> str | None:
    """Builds the serialized component embed for a post (or the comment it links to).

    Returns None when the post has no id or the payload cannot fit, the page then only carries OG tags.
    `media` overrides the post's media, e.g. with what a domain handler resolved.
    """
    if not post.id:
        return None
    if media is None:
        media = post.media

    body = reddit_markdown((post.comment or post).description)
    wanted = min(len(body), MIN_BODY)
    best: str | None = None

    for max_gallery in GALLERY_LIMITS:
        for limits in LIMITS:
            def fits(n: int, max_gallery: int = max_gallery, limits: Limits = limits) -> bool:
                return len(compose(post, media, max_gallery, limits, n).encode()) <= MAX_BYTES

            if not fits(0):
                continue

            # Longest body that fits
            low, high = 0, len(body)
            while low < high:
                mid = math.ceil((low + high) / 2)
                if fits(mid):
                    low = mid
                else:
                    high = mid - 1

            best = compose(post, media, max_gallery, limits, low)
            if low >= wanted:
                break

        # Only drop media when nothing fits at all
        if best:
            break

    return best
