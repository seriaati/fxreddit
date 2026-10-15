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
