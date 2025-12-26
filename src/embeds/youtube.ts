import { RedditPost } from '../reddit/types';
import { HTMLElement, parse as parseHTML } from 'node-html-parser';
import { CACHE_CONFIG } from '../cache';
import '../html';

/** Converts the youtube link to a video embed url */
export async function youtubeEmbed(post: RedditPost, link: string, head: HTMLElement) {
    const url: URL = new URL(link);

    // Clip links need another request to extract a proper url for embedding
    if (url.pathname.startsWith('/clip/')) {
        const html = await fetch(link, { ...CACHE_CONFIG }).then(r => r.text()).then(parseHTML);
        const clipEmbed = html.querySelector('meta[name="twitter:player"]')?.getAttribute('content');
        const thumbnail = html.querySelector('meta[name="twitter:image"]')?.getAttribute('content');

        const width = (post.oembed?.width && post.oembed.width > 500) ? post.oembed.width : 1280;
        const height = (post.oembed?.height && post.oembed.height > 500) ? post.oembed.height : 720;

        if (thumbnail) {
            head.image(thumbnail, width, height);
        }
        if (clipEmbed) {
            head.meta('twitter:card', 'player');
            head.video(clipEmbed, width, height, 'text/html');
        }

        return;
    }

    const YOUTUBE_EXTRACTOR: Record<string, (url: URL) => string | null> = {
        'youtu.be': (url: URL) => url.pathname.substring(1), // https://youtu.be/abc123
        'www.youtube.com': (url: URL) => url.searchParams.get('v'), // https://www.youtube.com/watch?v=abc123
        'youtube.com': (url: URL) => url.searchParams.get('v'), // https://youtube.com/watch?v=abc123
    };

    const id = YOUTUBE_EXTRACTOR[url.hostname]?.(url) ?? null;

    if (id) {
        // Discord doesn't support iframe embeds - use koutube.com API to get direct video stream
        const koutubeApiUrl = `https://koutube.com/api/watch?v=${id}`;

        try {
            const koutubeData = await fetch(koutubeApiUrl, { ...CACHE_CONFIG }).then(r => r.json()) as {
                playerStreamUrl?: string;
                videoWidth?: string;
                videoHeight?: string;
                image?: string;
                error?: string;
            };

            if (koutubeData.error) {
                throw new Error(koutubeData.error);
            }

            const videoUrl = koutubeData.playerStreamUrl;
            const width = parseInt(koutubeData.videoWidth || '1280');
            const height = parseInt(koutubeData.videoHeight || '720');
            const thumbnailUrl = koutubeData.image;

            if (videoUrl) {
                head.meta('twitter:card', 'player');
                head.meta('og:video', videoUrl);
                head.meta('og:video:secure_url', videoUrl);
                head.meta('og:video:type', 'video/mp4');
                head.meta('og:video:width', width.toString());
                head.meta('og:video:height', height.toString());
                head.meta('twitter:player', videoUrl);
                head.meta('twitter:player:width', width.toString());
                head.meta('twitter:player:height', height.toString());
            }

            if (thumbnailUrl) {
                head.image(thumbnailUrl, width, height);
            } else {
                head.image(`https://img.youtube.com/vi/${id}/maxresdefault.jpg`, width, height);
            }
        } catch (error) {
            // Fallback to simple image embed if koutube API fails
            head.meta('twitter:card', 'summary_large_image');
            head.image(`https://img.youtube.com/vi/${id}/maxresdefault.jpg`, 1280, 720);
        }
    }
}
