import { IRequest } from 'itty-router';
import { CACHE_CONFIG } from '../cache';

// Reddit serves video and audio as separate streams, the video server (see server/) muxes them into one file with sound
let videoServer: { url: string, secret: string } | undefined;

export function setVideoServer(url: string | undefined, secret: string | undefined) {
    videoServer = url && secret ? { url, secret } : undefined;
}

const REDDIT_VIDEO = /^https:\/\/v\.redd\.it\/([a-z0-9]+)\/((?:DASH|CMAF)_\d+\.mp4)/;
const VIDEO_ID = /^[a-z0-9]+$/;
const VIDEO_FILE = /^(?:DASH|CMAF)_\d+\.mp4$/;

/** URL of the reddit video with sound, if a video server is configured */
export function muxedVideoUrl(origin: string, videoUrl?: string) {
    const match = videoServer && videoUrl?.match(REDDIT_VIDEO);
    return match ? `${origin}/v/${match[1]}/${match[2]}` : undefined;
}

export async function getVideo(request: IRequest) {
    const { id, file } = request.params;
    if (!VIDEO_ID.test(id) || !VIDEO_FILE.test(file)) {
        return new Response(undefined, { status: 404 });
    }

    if (videoServer) {
        // Only limits the wait for the mux, aborting later would cut off the video while it streams
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 8000);
        try {
            const response = await fetch(`${videoServer.url}/${id}.mp4`, {
                method: request.method,
                headers: { Authorization: `Bearer ${videoServer.secret}` },
                signal: controller.signal,
                ...CACHE_CONFIG,
            });
            if (response.ok) {
                return response;
            }
        } catch {
            // Falls back to the silent video below
        } finally {
            clearTimeout(timeout);
        }
    }

    // Discord doesn't play videos behind a redirect, so the silent video is proxied as well
    return fetch(`https://v.redd.it/${id}/${file}`, { method: request.method });
}
