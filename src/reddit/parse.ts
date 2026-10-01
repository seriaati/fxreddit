import { isDefined, isNonNullish } from 'remeda';
import { Image, MediaItem, RedditListingData, RedditPost } from './types';

export function parseRedditPost(metadata: RedditListingData): RedditPost {
    const crosspost = metadata.crosspost_parent_list?.length ? parseRedditPost(metadata.crosspost_parent_list[0]) : undefined;

    let resolution: undefined | { width: number, height: number } = undefined;

    let post_hint = metadata.post_hint ?? 'unknown';
    let video_url = metadata.secure_media?.reddit_video?.fallback_url;
    let has_audio = true;

    if (metadata?.media?.reddit_video) {
        resolution = { width: metadata.media.reddit_video.width, height: metadata.media.reddit_video.height };
        video_url = metadata.media.reddit_video.fallback_url;
        has_audio = metadata.media.reddit_video.has_audio;
        post_hint = 'hosted:video';
    } else if (crosspost) {
        video_url = crosspost.video_url;
        resolution = crosspost.resolution;
        post_hint = crosspost.post_hint;
        has_audio = crosspost.video_has_audio === true;
    } else if (metadata?.preview?.images?.length) {
        if (metadata.preview.images[0].source) {
            resolution = metadata.preview.images[0].source;
        } else {
            const resolutions = metadata.preview?.images?.[0].resolutions;
            resolution = resolutions?.[resolutions?.length - 1];
        }
    } else if (metadata?.thumbnail_width && metadata?.thumbnail_height) {
        resolution = { width: metadata.thumbnail_width, height: metadata.thumbnail_height };
    }

    const media_metadata: Image[] = [];
    if (metadata.media_metadata && metadata.gallery_data?.items) {
        for (const { media_id, caption } of metadata.gallery_data.items) {
            const value = metadata.media_metadata[media_id];
            // Animated images have no 'u', only 'gif' and 'mp4'
            const url = value?.s?.u ?? value?.s?.gif;
            if (!value?.s || !url) continue;
            media_metadata.push({
                width: value.s.x,
                height: value.s.y,
                url,
                caption: caption,
            });
        }
    } else if (metadata.media_metadata) {
        for (const values of Object.values(metadata.media_metadata)) {
            const url = values?.s?.u ?? values?.s?.gif;
            if (!values?.s || !url) continue;
            media_metadata.push({
                width: values.s.x,
                height: values.s.y,
                url,
            });
        }
    } else if (isDefined(crosspost?.media_metadata)) {
        media_metadata.push(...crosspost.media_metadata);
    }

    const preview_image_url = firstNotEmpty(metadata.preview?.images?.[0].source?.url, metadata.thumbnail, crosspost?.preview_image_url);

    return {
        subreddit: metadata.subreddit,
        title: metadata.title,
        post_hint: post_hint,
        url: metadata.url,
        permalink: metadata.permalink,
        description: getDescription(metadata),
        is_reddit_media: metadata.is_reddit_media_domain,
        is_media_only: metadata.media_only === true,
        preview_image_url,
        resolution: resolution ? { width: resolution.width, height: resolution.height } : undefined,
        video_url: video_url,
        video_has_audio: has_audio,
        oembed: metadata.secure_media?.oembed ?? metadata.media?.oembed,
        domain: metadata.domain,
        secure_media_embed: metadata.secure_media_embed,
        media_metadata,
        author: metadata.author,
        poll_data: metadata.poll_data,
        id: metadata.id,
        created_utc: metadata.created_utc,
        edited: !!metadata.edited,
        score: metadata.score,
        upvote_ratio: metadata.upvote_ratio,
        num_comments: metadata.num_comments,
        nsfw: metadata.over_18 === true,
        spoiler: metadata.spoiler === true,
        locked: metadata.locked === true,
        stickied: metadata.stickied === true,
        flair: unescapeHtml(metadata.link_flair_text ?? '').replace(/:[\w-]+:/g, '').trim() || undefined, // drop Reddit emoji shortcodes
        is_original_content: metadata.is_original_content === true,
        distinguished: metadata.distinguished ?? undefined,
        is_submitter: metadata.is_submitter === true,
        removed: isNonNullish(metadata.removed_by_category),
        subreddit_icon: unescapeHtml(metadata.sr_detail?.community_icon || metadata.sr_detail?.icon_img || '') || undefined,
        media: getMedia(metadata, crosspost),
        crosspost,
    };
}

/** Reddit escapes &, < and > in JSON strings */
export function unescapeHtml(text: string): string {
    return text.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&#x200B;/gi, '').replace(/&amp;/g, '&');
}

/** All media of the post in display order, images and videos mixed */
function getMedia(metadata: RedditListingData, crosspost?: RedditPost): MediaItem[] {
    const items: MediaItem[] = [];
    if (metadata.media_metadata && metadata.gallery_data?.items) {
        for (const { media_id, caption } of metadata.gallery_data.items) {
            const s = metadata.media_metadata[media_id]?.s;
            const image = s?.u ?? s?.gif;
            if (s?.mp4 && !s.u) {
                items.push({ kind: 'video', url: unescapeHtml(s.mp4), caption });
            } else if (image) {
                items.push({ kind: 'image', url: unescapeHtml(image), caption });
            }
        }
    } else if (metadata.media?.reddit_video) {
        // Same proxy the og:video tag uses, the fallback_url has no audio
        items.push({ kind: 'video', url: `/v${metadata.permalink}` });
    } else if (metadata.post_hint === 'image' && metadata.url) {
        items.push({ kind: 'image', url: unescapeHtml(metadata.url) });
    } else if (metadata.preview?.images?.[0]?.source?.url) {
        items.push({ kind: 'image', url: unescapeHtml(metadata.preview.images[0].source.url) });
    }

    return items.length ? items : crosspost?.media ?? [];
}

function getDescription(metadata: RedditListingData): string {
    let text = metadata.selftext ?? metadata.body;
    if (isNonNullish(metadata.poll_data)) {
        text = text?.replace(/^\s*\[View Poll\]\([^)]+\)/gi, '');
    }
    return text?.replace(/^&amp;#x200B;/, '')?.trim() ?? '';
}

function firstNotEmpty(...strings: (string | undefined)[]) {
    for (const s of strings) {
        if (isNonNullish(s) && s.trim().length > 0) {
            return s;
        }
    }

    return undefined;
}