import { REDDIT_BASE_URL, USER_AGENT } from '../constants';

// Since May 2026, Reddit rejects unauthenticated .json requests with 403,
// and it no longer hands out anonymous "loid" cookies to logged-out clients.
// Requests are authenticated with the session cookie of a logged-in account,
// provided as the REDDIT_COOKIE secret (e.g. "reddit_session=...").
let redditCookie: string | undefined;

export function setRedditCookie(cookie: string | undefined) {
    redditCookie = cookie;
}

export function getRedditCookie(): string | undefined {
    return redditCookie;
}

// /api/me.json answers 200 for a logged-in session and 403 otherwise.
// Other statuses (5xx, timeouts) are Reddit outages and don't say anything about the cookie.
export async function checkRedditCookie(cookie: string | undefined, webhookUrl: string) {
    let problem: string | undefined;
    if (!cookie) {
        problem = 'REDDIT_COOKIE is not set';
    } else {
        const response = await fetch(`${REDDIT_BASE_URL}/api/me.json`, {
            signal: AbortSignal.timeout(5000),
            headers: { 'User-Agent': USER_AGENT, 'Cookie': cookie },
        });
        await response.body?.cancel();
        if (response.status === 403) {
            problem = 'Reddit rejected REDDIT_COOKIE (403), the session has expired or been revoked';
        }
    }

    if (problem) {
        console.log(`Reddit cookie check failed: ${problem}`);
        await fetch(webhookUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                content: `⚠️ **fxreddit**: ${problem}. Post embeds fail with 403 until it is replaced with \`wrangler secret put REDDIT_COOKIE\`.`,
            }),
        });
    }
}
