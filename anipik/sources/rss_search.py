"""Search a site's RSS with keywords: search_prefix + keyword_sep.join(keywords) + search_suffix.

Works for dmhy / MioBT / acg.rip / acgnx / nyaa style feeds.
"""
import html
import re

from bs4 import BeautifulSoup

from ..matcher import info_hash_from_magnet
from .base import Release, SourceError, SourceKind

_HEX40 = re.compile(r"^[0-9a-fA-F]{40}$")


def parse_feed(content: bytes) -> list[Release]:
    if not re.match(rb"^\s*(?:\xef\xbb\xbf)?<", content):
        raise SourceError("response is not XML")
    soup = BeautifulSoup(content, features="xml")
    releases = []
    for item in soup.find_all("item"):
        # Some feeds (acgnx, MioBT) escape titles twice: "&amp;amp;" arrives as "&amp;".
        title = html.unescape(item.title.text).strip() if item.title else ""
        link = item.link.text.strip() if item.link else None
        enclosure = item.find("enclosure")
        url = enclosure.get("url") if enclosure is not None and enclosure.get("url") else link
        # nyaa: <nyaa:infoHash>; other feeds put a magnet in the enclosure.
        tag = item.find(lambda t: t.name and t.name.lower().endswith("infohash"))
        info_hash = tag.text.strip().lower() if tag is not None and _HEX40.match(tag.text.strip()) else None
        info_hash = info_hash or info_hash_from_magnet(url)
        if title and url:
            releases.append(Release(title=title, url=url, info_hash=info_hash, page_link=link,
                                    published=item.pubDate.text.strip() if item.pubDate else None))
    return releases


class RssSearchSource(SourceKind):
    kind = "rss_search"
    fields = ("search_prefix", "keyword_sep", "search_suffix")

    def search_url(self, params):
        keywords = [k.strip() for k in params.get("keywords") or [] if k and k.strip()]
        if not keywords:
            raise SourceError("binding has no keywords")
        c = self.config
        return c.get("search_prefix", "") + c.get("keyword_sep", "+").join(keywords) + c.get("search_suffix", "")

    def search(self, params):
        return parse_feed(self.http.get(self.search_url(params)))
