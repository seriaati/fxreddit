import base64
import binascii
import json
from typing import Any

from .constants import CUSTOM_DOMAIN


def encode_oembed(embed: dict[str, str]) -> str:
    data = base64.urlsafe_b64encode(json.dumps(embed, ensure_ascii=False, separators=(',', ':')).encode()).rstrip(b'=')
    return f'https://{CUSTOM_DOMAIN}/oembed?embed={data.decode()}'


def decode_oembed(data: str) -> dict[str, Any] | None:
    try:
        decoded = json.loads(base64.urlsafe_b64decode(data + '=' * (-len(data) % 4)))
    except (binascii.Error, ValueError):
        return None
    return decoded if isinstance(decoded, dict) else None


def oembed_response(embed: dict[str, Any]) -> dict[str, str]:
    def string(key: str) -> str | None:
        value = embed.get(key)
        return value if isinstance(value, str) else None

    author_url = string('author_url')
    response = {
        'type': string('type'),
        'author_name': string('author_name'),
        'author_url': author_url if author_url and author_url.startswith('https://www.reddit.com/') else None,
        'provider_name': string('provider_name'),
        'version': string('version'),
    }
    return {key: value for key, value in response.items() if value is not None}
