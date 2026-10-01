import { IRequest } from 'itty-router';
import { get_untyped_post } from './post';
import { postToHtml } from '../reddit/compile';
import { getMediaSlot } from '../reddit/component_embed';
import { redirectPage } from '../util';
import ResponseError from '../response_error';

const SLOT_REGEX = /^(a|qa|\d)\.(jpg|mp4)$/;

/** Redirects the short media URLs of a component embed (/m/<post>/<slot>.jpg|mp4) to the real media */
export async function handleMedia(request: IRequest) {
    const { id, file } = request.params;
    const slot = SLOT_REGEX.exec(file)?.[1];
    if (!slot || !/^[a-z0-9]+$/i.test(id)) {
        return new Response('Not Found', { status: 404 });
    }

    let url = getMediaSlot(id, slot);
    if (!url) {
        // Discord fetches media later, possibly from another isolate: rendering the post again fills the store
        try {
            const post = await get_untyped_post(id);
            await postToHtml(post, new URL(request.url).origin);
            url = getMediaSlot(id, slot);
        } catch (err) {
            if ((err as ResponseError).status !== 404) {
                throw err;
            }
        }
    }

    if (!url) {
        return new Response('Not Found', { status: 404 });
    }

    return new Response(redirectPage(url).toString(), {
        status: 302,
        headers: { 'Location': url, 'Content-Type': 'text/html', 'Cache-Control': 'public, max-age=3600' },
    });
}
