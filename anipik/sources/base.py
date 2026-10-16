from dataclasses import dataclass
from typing import Optional


class SourceError(Exception):
    pass


@dataclass
class Release:
    title: str
    url: str                          # magnet, or a link to a .torrent
    info_hash: Optional[str] = None   # lowercase hex, when the feed provides it
    page_link: Optional[str] = None
    published: Optional[str] = None


class SourceKind:
    """A kind of source. Instances come from Source.config; search() gets SourceBinding.params."""
    kind = ""

    def __init__(self, config: dict, http):
        self.config = config or {}
        self.http = http

    def search(self, params: dict) -> list[Release]:
        raise NotImplementedError
