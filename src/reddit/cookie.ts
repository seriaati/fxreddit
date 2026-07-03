import { USER_AGENT } from '../constants';

// Since May 2026, Reddit rejects unauthenticated .json requests with 403.
// An anonymous session cookie ("loid"), which Reddit sets on any plain HTML
// page response, is enough to authenticate them.
const MINT_URL = 'https://old.reddit.com/';
const CACHE_KEY = 'https://rxddit.com/__internal/loid';
const CACHE_TTL = 604800; // 7 days, the cookie itself is valid for 2 years

let memoryLoid: string | null = null;

async function mintLoid(): Promise<string | null> {
    const response = await fetch(MINT_URL, {
        signal: AbortSignal.timeout(5000),
        headers: { 'User-Agent': USER_AGENT },
    });
    await response.body?.cancel();

    const match = /loid=([A-Za-z0-9._-]+)/.exec(response.headers.get('set-cookie') ?? '');
    return match ? `loid=${match[1]}` : null;
}

export async function getLoidCookie(): Promise<string | null> {
    if (memoryLoid) {
        return memoryLoid;
    }

    const cached = await caches.default.match(CACHE_KEY);
    if (cached) {
        memoryLoid = await cached.text();
        return memoryLoid;
    }

    const loid = await mintLoid();
    if (loid) {
        memoryLoid = loid;
        await caches.default.put(CACHE_KEY, new Response(loid, {
            headers: { 'Cache-Control': `max-age=${CACHE_TTL}` },
        }));
    }
    return loid;
}

export async function invalidateLoidCookie(): Promise<void> {
    memoryLoid = null;
    await caches.default.delete(CACHE_KEY);
}
