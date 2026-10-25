"""HTTP clients shared by all requests, opened and closed with the app (see main.py)."""

import httpx
from curl_cffi.requests import AsyncSession

# Reddit rejects clients that don't look like a browser, even with a logged-in session cookie,
# so its requests copy Chrome's TLS and HTTP/2 fingerprint
reddit: AsyncSession
# Everything else: v.redd.it, fxtwitter, koutube, YouTube
web: httpx.AsyncClient
