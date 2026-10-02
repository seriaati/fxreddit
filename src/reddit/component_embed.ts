import { MediaItem, PollData, RedditPost } from './types';
import { unescapeHtml } from './parse';
import { REDDIT_BASE_URL } from '../constants';

// Discord component embed: https://discord.com/developers/docs/link-previews/component-embeds
// The serialized payload must stay within 3000 bytes, otherwise Discord silently falls back to the OG tags.
const MAX_BYTES = 3000;
const GALLERY_LIMITS = [10, 4, 1]; // 10 is the maximum across the whole embed, fewer when the media URLs don't fit
const MIN_BODY = 200; // below this, the context is crowding out the main text
export const ACCENT_COLOR = 0xff4500;

const LIMITS = [
    { reply: 150, quote: 300 },
    { reply: 100, quote: 150 },
    { reply: 50, quote: 80 },
];

type Limits = typeof LIMITS[number];
type Component = Record<string, unknown>;

const userUrl = (user: string) => `${REDDIT_BASE_URL}/user/${user}`;
const subredditUrl = (subreddit: string) => `${REDDIT_BASE_URL}/r/${subreddit}`;
const shortUrl = (id?: string) => `https://redd.it/${id}`;
const formatCount = (n?: number) => (n ?? 0).toLocaleString('en-US');
const timestamp = (seconds: number | undefined, style: string) => `<t:${Math.floor(seconds ?? 0)}:${style}>`;

function escapeMarkdown(text: string) {
    return text.replace(/([\\*_~`|[\]])/g, '\\$1').replace(/^([>#-])/gm, '\\$1');
}

/** Cuts to n code points, never leaving half a [text](url) link behind */
function cut(text: string, n: number) {
    const chars = [...text];
    if (chars.length <= n) {
        return text;
    }
    return chars.slice(0, n).join('').replace(/\[[^\]]*(\]\([^)]*)?$/, '').trimEnd() + '…';
}

/** Reddit bodies are already Markdown: keep it, convert Reddit-only syntax and link u/ and r/ */
function redditMarkdown(text: string) {
    const parts = unescapeHtml(text).split(/(\[[^\]]*\]\([^)]*\)|https?:\/\/\S+)/); // odd indices are links, left untouched
    return parts.map((part, i) => i % 2 ? part : part
        .replace(/>!(.+?)!</g, '||$1||')
        .replace(/^#{1,6}\s+(.+)$/gm, '**$1**')
        .replace(/(^|[^\w/])\/?(u|r)\/([A-Za-z0-9_-]{2,21})/g, (_, pre, type, name) =>
            `${pre}[${type}/${name}](${type === 'u' ? userUrl(name) : subredditUrl(name)})`))
        .join('')
        .replace(/\n{3,}/g, '\n\n');
}

function quote(text: string) {
    return text.split('\n').map(line => `> ${line.replace(/^>\s?/, '')}`).join('\n');
}

function badges(post: RedditPost) {
    const result = [];
    if (post.is_submitter) result.push('🎤 OP');
    if (post.distinguished === 'moderator') result.push('🛡️ Mod');
    if (post.is_original_content) result.push('OC');
    if (post.flair) result.push(`🏷️ ${escapeMarkdown(cut(post.flair, 40))}`);
    return result;
}

function pollText({ options, total_vote_count, voting_end_timestamp }: PollData) {
    if (!options) {
        return null;
    }
    const lines = options.map(({ text, vote_count }) => vote_count != null
        ? `- ${escapeMarkdown(text)} — **${formatCount(vote_count)}** (${Math.round(100 * vote_count / Math.max(total_vote_count, 1))}%)`
        : `- ${escapeMarkdown(text)}`);
    const state = voting_end_timestamp < Date.now() ? 'ended' : 'ends';
    return `📊 **Poll** · ${formatCount(total_vote_count)} votes · ${state} ${timestamp(voting_end_timestamp / 1000, 'R')}\n${lines.join('\n')}`;
}

const separator = (divider: boolean, spacing = 2) => ({ type: 14, divider, spacing });
const text = (content: string) => ({ type: 10, content });

function block(texts: string[], thumbnail?: string): Component[] {
    if (!thumbnail) {
        return texts.map(text);
    }
    return [{ type: 9, components: texts.map(text), accessory: { type: 11, media: { url: thumbnail } } }];
}

class Composer {
    constructor(private readonly post: RedditPost, private readonly media: MediaItem[], private readonly maxGallery: number) { }

    compose(limits: Limits, bodyLength: number) {
        const { post, media, maxGallery } = this;
        const comment = post.comment;
        const main = comment ?? post;
        const components: Component[] = [];

        // Community icon, community and author, reply context, title and body
        const author = [`[u/${escapeMarkdown(main.author)}](${userUrl(main.author)})`, ...badges(main)].join(' · ');
        const texts = [`## [r/${post.subreddit}](${subredditUrl(post.subreddit)})\n-# ${author}`];
        if (comment) {
            const title = `### ${escapeMarkdown(cut(unescapeHtml(post.title), limits.reply))}`;
            texts.push(`-# ↩️ Replying to **[u/${escapeMarkdown(post.author)}](${shortUrl(post.id)})**\n${quote(title)}`);
            texts.push(cut(redditMarkdown(comment.description), bodyLength) || '\u200b');
        } else {
            const body = cut(redditMarkdown(post.description), bodyLength);
            const title = `### ${escapeMarkdown(unescapeHtml(post.title))}`;
            texts.push(body ? `${title}\n${body}` : title);
        }
        components.push(...block(texts, post.subreddit_icon));

        const poll = !comment && post.poll_data ? pollText(post.poll_data) : null;
        if (poll) {
            components.push(separator(false), text(poll));
        }

        // Media gallery, comment links show the post's media as well
        if (media.length) {
            const spoiler = post.nsfw || post.spoiler;
            components.push(separator(false), {
                type: 12,
                items: media.slice(0, maxGallery).map(item => ({
                    media: { url: item.url },
                    ...(item.caption ? { description: cut(item.caption, 200) } : {}),
                    ...(spoiler ? { spoiler: true } : {}),
                })),
            });
        }

        // Crosspost as the quoted post, its media is already in the gallery since crossposts inherit it
        const crosspost = post.crosspost;
        if (crosspost && !comment) {
            components.push(separator(true));
            if (crosspost.removed || crosspost.author === '[deleted]') {
                components.push(text('-# 🔀 Original post is unavailable'));
            } else {
                const by = `**[r/${crosspost.subreddit}](${shortUrl(crosspost.id)})** · [u/${escapeMarkdown(crosspost.author)}](${userUrl(crosspost.author)}) · ${timestamp(crosspost.created_utc, 'd')}`;
                const body = crosspost.description ? `\n${cut(redditMarkdown(crosspost.description), limits.quote)}` : '';
                const quoted = `${quote(`**${escapeMarkdown(cut(unescapeHtml(crosspost.title), 150))}**${body}`)}\n> -# ⬆️ ${formatCount(crosspost.score)} · 💬 ${formatCount(crosspost.num_comments)}`;
                components.push(...block([`-# 🔀 Crossposted from\n${by}`, quoted], crosspost.subreddit_icon));
            }
        }

        // Footer and buttons
        const ratio = !comment && post.upvote_ratio != null ? ` (${Math.round(post.upvote_ratio * 100)}%)` : '';
        const footer = [`⬆️ **${formatCount(main.score)}**${ratio}`];
        if (!comment) footer.push(`💬 **${formatCount(post.num_comments)}**`);
        footer.push(timestamp(main.created_utc, 'f'));
        if (main.edited) footer.push('✏️ Edited');
        if (post.nsfw) footer.push('🔞 NSFW');
        if (post.spoiler) footer.push('⚠️ Spoiler');
        if (post.locked) footer.push('🔒 Locked');
        if (post.stickied) footer.push('📌 Pinned');
        if (media.length > maxGallery) footer.push(`🖼️ ${maxGallery} of ${media.length}`);

        // Slug-free links, a CJK slug costs 9 bytes per character once percent-encoded
        const link = comment
            ? `${REDDIT_BASE_URL}/r/${post.subreddit}/comments/${post.id}/comment/${comment.id}/`
            : `${REDDIT_BASE_URL}/r/${post.subreddit}/comments/${post.id}/`;
        components.push(separator(true), text(footer.join(' · ')), separator(false, 1), {
            type: 1,
            components: [
                { type: 2, style: 5, label: comment ? 'Open comment' : 'Open post', url: link },
                { type: 2, style: 5, label: cut(`u/${main.author}`, 80), url: userUrl(main.author) },
            ],
        });

        const container = { type: 17, accent_color: ACCENT_COLOR, ...(post.nsfw ? { spoiler: true } : {}), components };
        // Escaped so the JSON can never close the surrounding <script> tag
        return JSON.stringify({ component: container }).replace(/</g, '\\u003c');
    }
}

const encoder = new TextEncoder();

/**
 * Builds the serialized component embed for a post (or the comment it links to).
 * Returns null when the post has no id or the payload cannot fit, the page then only carries OG tags.
 * @param media overrides the post's media, e.g. with what a domain handler resolved
 */
export function compileComponentEmbed(post: RedditPost, media = post.media ?? []): string | null {
    if (!post.id) {
        return null;
    }

    const body = [...redditMarkdown((post.comment ?? post).description)];
    const wanted = Math.min(body.length, MIN_BODY);
    let best: string | null = null;

    for (const maxGallery of GALLERY_LIMITS) {
        for (const limits of LIMITS) {
            const composer = new Composer(post, media, maxGallery);
            const fits = (n: number) => encoder.encode(composer.compose(limits, n)).length <= MAX_BYTES;
            if (!fits(0)) {
                continue;
            }

            // Longest body that fits
            let low = 0, high = body.length;
            while (low < high) {
                const mid = Math.ceil((low + high) / 2);
                if (fits(mid)) {
                    low = mid;
                } else {
                    high = mid - 1;
                }
            }

            best = composer.compose(limits, low);
            if (low >= wanted) {
                break;
            }
        }

        // Only drop media when nothing fits at all
        if (best) {
            break;
        }
    }

    return best;
}
