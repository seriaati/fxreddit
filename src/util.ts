import { IRequest, html as HtmlResponse } from 'itty-router';
import { CUSTOM_DOMAIN } from './constants';
import { HTMLElement } from 'node-html-parser';
import { httpEquiv } from './html';

export function cleanSpoiler(string: string): string {
    return string.endsWith('||') ? string.substring(0, string.length - 2) : string;
}

export function getOriginalUrl(url: string, short: boolean) {
    const location = new URL(url);

    const targetDomain = short ? 'redd.it' : 'reddit.com';

    if (location.hostname.endsWith(CUSTOM_DOMAIN)) {
        const originalDomain = short ? location.hostname : CUSTOM_DOMAIN;
        location.hostname = location.hostname.replace(originalDomain, targetDomain);
    } else {
        location.hostname = targetDomain;
    }

    location.protocol = 'https:';
    location.port = '';

    return location.toString();
}

export function isBot({ headers }: IRequest): boolean {
    const userAgent = headers.get('User-Agent')?.toLowerCase() ?? '';
    return userAgent.includes('bot') || userAgent.includes('SteamChatURLLookup'.toLowerCase());
}


export function redirectPage(url: string) {
    const html = new HTMLElement('html', {});
    html.appendChild(new HTMLElement('head', {}).appendChild(httpEquiv(url)));
    return html;
}

export function fallbackRedirect(req: IRequest) {
    const url = getOriginalUrl(req.url, false);
    const html = redirectPage(url);

    return HtmlResponse(html.toString(), {
        headers: { Location: url }, status: 302
    });
}
