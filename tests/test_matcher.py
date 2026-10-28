import bencodepy
import hashlib
from urllib.parse import parse_qs

import pytest

from anipik.matcher import (info_hash_from_magnet, info_hash_from_torrent, magnet_from_torrent, matches_filters,
                            normalize_magnet, parse_episode, with_display_name)
from anipik.sources.rss_search import RssSearchSource, parse_feed


@pytest.mark.parametrize("title, expected", [
    ("[ANi] 戰士久留美 - 03 [1080P][Baha][WEB-DL][AAC AVC][CHT][MP4]", 3),
    ("[LoliHouse] Kusuriya no Hitorigoto - 47 [WebRip 1080p HEVC-10bit AAC][简繁内封字幕]", 47),
    ("【幻月字幕组】【23年日剧】【呛人姐与心机妹】【07】【1080P】【中日双语】", 7),
    ("[Nekomoe kissaten][Kusuriya no Hitorigoto][47][1080p][JPSC].mp4", 47),
    ("[DKB] Sentai Daishikkaku S02 - 12 [1080p][HEVC x265 10bit][Multi-Subs]", 12),
    ("[ToonsHub] Super Cube S01E264 1080p iQ WEB-DL AAC2.0 H.264", 264),
    ("[ANi] 86 - 不存在的戰區 - 03v2 [1080P]", 3),
    ("[北宇治字幕组] 药屋少女的呢喃 第二季 第47话 [WebRip 1080p]", 47),
    ("[Erai-raws] Title 2nd Season - 05 [1080p][Multiple Subtitle][ABCD1234]", 5),
    ("[SubsPlease] One Piece - 1100 (1080p) [ABCDEF12].mkv", 1100),
    ("[Group] Title (2025) - 08 [1080p]", 8),
    ("【喵萌奶茶屋】★10月新番★[某番][12][1080P][简体][MP4]", 12),
    ("[Group] Title EP05 [1080p]", 5),
    # batches and ambiguous titles are skipped rather than guessed
    ("[DKB] Sentai Daishikkaku S02 [01-12][1080p][Batch]", None),
    ("[Group] Title 第01-12话 合集", None),
    ("[Group] Title Vol.2 BDRip 1080p", None),
])
def test_parse_episode(title, expected):
    assert parse_episode(title) == expected


def test_magnet_normalization():
    base32 = "magnet:?xt=urn:btih:5KRX7IPMOWOC44JSDA5W3MUIEAADSQ6R"
    assert info_hash_from_magnet(base32) == "eaa37fa1ec759c2e7132183b6db28820003943d1"
    hex_upper = "magnet:?xt=urn:btih:EAA37FA1EC759C2E7132183B6DB28820003943D1&tr=http://t/announce"
    assert info_hash_from_magnet(hex_upper) == info_hash_from_magnet(base32)
    assert normalize_magnet(hex_upper).startswith("magnet:?xt=urn:btih:eaa37fa1ec759c2e7132183b6db28820003943d1&tr=")
    assert info_hash_from_magnet("https://example.com/a.torrent") is None


def test_torrent_hash():
    info = {b"name": b"x", b"length": 1, b"piece length": 16384, b"pieces": b"0" * 20}
    data = bencodepy.encode({b"info": info, b"announce": b"http://t"})
    assert info_hash_from_torrent(data) == hashlib.sha1(bencodepy.encode(info)).hexdigest()


def test_magnets_carry_the_release_title():
    info = {b"name": b"x.mp4", b"length": 1, b"piece length": 16384, b"pieces": b"0" * 20}
    data = bencodepy.encode({b"info": info, b"announce": b"http://t/announce\r",
                             b"announce-list": [[b"http://t/announce"], [b"udp://u:80"]]})
    title = "[黒ネズミたち] 乱世千金 - 04 [1080p]"
    magnet = magnet_from_torrent(data, title)
    params = parse_qs(magnet[len("magnet:?"):])
    assert params["dn"] == [title] and params["tr"] == ["http://t/announce", "udp://u:80"]
    assert info_hash_from_magnet(magnet) == hashlib.sha1(bencodepy.encode(info)).hexdigest()
    assert parse_qs(magnet_from_torrent(data)[len("magnet:?"):])["dn"] == ["x.mp4"]
    bare = "magnet:?xt=urn:btih:eaa37fa1ec759c2e7132183b6db28820003943d1"
    assert parse_qs(with_display_name(bare, title)[len("magnet:?"):])["dn"] == [title]
    assert with_display_name(bare + "&dn=keep", title) == bare + "&dn=keep"


def test_filters():
    assert matches_filters("[ANi] X - 01 [1080P]", include=["1080"], exclude=["720"])
    assert not matches_filters("[ANi] X - 01 [720P]", include=["1080"])
    assert not matches_filters("[ANi] X - 01 [1080P][繁]", exclude=["繁"])


FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:nyaa="https://nyaa.si/xmlns/nyaa" version="2.0"><channel>
<item><title>[A] Show - 02 [1080p]</title><link>https://nyaa.si/download/2.torrent</link>
  <pubDate>Thu, 16 Oct 2026 00:00:00 -0000</pubDate>
  <nyaa:infoHash>EAA37FA1EC759C2E7132183B6DB28820003943D1</nyaa:infoHash></item>
<item><title>[B] Show - 01 [1080p]</title><link>https://site/view/1</link>
  <enclosure url="magnet:?xt=urn:btih:5KRX7IPMOWOC44JSDA5W3MUIEAADSQ6R" type="application/x-bittorrent"/></item>
<item><title>[C&amp;amp;D] Show - 03</title><link>https://site/view/3</link>
  <enclosure url="https://site/3.torrent" type="application/x-bittorrent"/></item>
</channel></rss>"""


def test_parse_feed():
    a, b, c = parse_feed(FEED)
    assert (a.url, a.info_hash) == ("https://nyaa.si/download/2.torrent", "eaa37fa1ec759c2e7132183b6db28820003943d1")
    assert b.info_hash == "eaa37fa1ec759c2e7132183b6db28820003943d1" and b.url.startswith("magnet:")
    assert (c.url, c.info_hash) == ("https://site/3.torrent", None)
    assert c.title == "[C&D] Show - 03"  # double-escaped entity decoded


def test_search_url_matches_legacy_format():
    source = RssSearchSource({"search_prefix": "https://www.miobt.com/rss-", "keyword_sep": "+",
                              "search_suffix": ".xml"}, http=None)
    assert source.search_url({"keywords": [" ani 战士久留美 ", "1080"]}) == \
        "https://www.miobt.com/rss-ani 战士久留美+1080.xml"
