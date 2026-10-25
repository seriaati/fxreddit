"""Builds the <head> of the embed pages and reads meta tags from other pages."""

import html
import json
from html.parser import HTMLParser


def quote_attribute(value: str) -> str:
    """Quotes an attribute value like node-html-parser did in the worker version.

    Reddit already escapes &, < and > in its JSON, so only quotes are escaped here.
    Backslashes are dropped, which removes Reddit's markdown escapes (\\_, \\*) from descriptions.
    """
    return (
        json.dumps(value.replace('"', '&quot;'), ensure_ascii=False)
        .replace('\\t', '\t')
        .replace('\\n', '\n')
        .replace('\\r', '\r')
        .replace('\\', '')
    )


def element(tag: str, attributes: dict[str, str]) -> str:
    rendered = ''.join(f' {name}={quote_attribute(value)}' if value else f' {name}' for name, value in attributes.items())
    return f'<{tag}{rendered}>'


def http_equiv(url: str) -> str:
    return element('meta', {'http-equiv': 'Refresh', 'content': f'0; URL={url}'})


def redirect_page(url: str) -> str:
    return f'<html><head>{http_equiv(url)}</head></html>'


class Head:
    """The elements of a page's <head>, in order"""

    def __init__(self):
        self.elements: list[str] = []
        self.metas: list[tuple[str, str]] = []

    def append(self, tag: str, attributes: dict[str, str], text: str | None = None):
        self.elements.append(element(tag, attributes) + (f'{text}</{tag}>' if text is not None else ''))

    def meta(self, property: str, content: str | None = None):
        self.append('meta', {'property': property, 'content': content or ''})
        self.metas.append((property, content or ''))

    def content(self, property: str) -> str | None:
        """Content of the first meta tag with this property, entities decoded like a parser reading the page would"""
        return next((html.unescape(content) for name, content in self.metas if name == property), None)

    def image(self, url: str, width: int | None = None, height: int | None = None, type: str | None = None):
        self.meta('twitter:image:src', url)
        self.meta('og:image', url)
        if width and height:
            self.meta('og:image:width', str(width))
            self.meta('og:image:height', str(height))
        if type == 'large':
            self.meta('twitter:card', 'summary_large_image')

    def video(self, url: str, width: int | None = None, height: int | None = None, type: str = 'video/mp4'):
        self.meta('twitter:player', url)
        self.meta('og:video', url)
        self.meta('og:video:secure_url', url)
        self.meta('og:video:type', type)
        if width and height:
            self.meta('og:video:width', str(width))
            self.meta('og:video:height', str(height))
            self.meta('twitter:player:width', str(width))
            self.meta('twitter:player:height', str(height))

    def __str__(self) -> str:
        return f'<head>{"".join(self.elements)}</head>'


class _MetaParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.metas: list[dict[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        if tag == 'meta':
            self.metas.append(dict(attrs))


class Metas:
    """The meta tags of an HTML page"""

    def __init__(self, html: str):
        parser = _MetaParser()
        parser.feed(html)
        self.metas = parser.metas

    def get(self, key: str, value: str) -> str | None:
        """Content of the first meta tag whose attribute `key` is `value`"""
        return next((meta.get('content') for meta in self.metas if meta.get(key) == value), None)
