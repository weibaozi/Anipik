import logging
import time

import requests

from .base import Release, SourceError, SourceKind
from .rss_search import RssSearchSource

log = logging.getLogger(__name__)

SOURCE_KINDS = {cls.kind: cls for cls in (RssSearchSource,)}


class Http:
    """Small GET helper with retries, shared by sources and torrent resolution."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                             "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"}

    def __init__(self, retries=3, timeout=30):
        self.retries, self.timeout = retries, timeout
        self.session = requests.Session()

    def get(self, url) -> bytes:
        error = None
        for attempt in range(self.retries):
            try:
                response = self.session.get(url, headers=self.headers, timeout=self.timeout)
                if response.status_code == 200:
                    return response.content
                error = f"HTTP {response.status_code}"
            except requests.RequestException as exc:
                error = str(exc)
            if attempt + 1 < self.retries:
                time.sleep(2 * (attempt + 1))
        raise SourceError(f"GET {url} failed: {error}")


def build_source(kind, config, http) -> SourceKind:
    try:
        cls = SOURCE_KINDS[kind]
    except KeyError:
        raise SourceError(f"unknown source kind {kind!r}") from None
    return cls(config, http)
