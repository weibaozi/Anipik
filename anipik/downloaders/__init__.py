from .base import Downloader, JobSpec, NeedsAttention, Status, TransientError
from .pikpak_client import PikPakClientDownloader

DOWNLOADERS = {cls.name: cls for cls in (PikPakClientDownloader,)}


def build_downloader(name, config) -> Downloader:
    try:
        return DOWNLOADERS[name](config)
    except KeyError:
        raise ValueError(f"unknown downloader {name!r}; available: {', '.join(DOWNLOADERS)}") from None
