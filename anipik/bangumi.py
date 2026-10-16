"""bgm.tv metadata: search titles, fetch subject details (cover, air date, episode count)."""
from urllib.parse import quote

import requests

API = "https://api.bgm.tv"
HEADERS = {"User-Agent": "weibaozi/anipik (https://github.com/weibaozi/Anipik)"}


def _https(url):
    return url.replace("http://", "https://", 1) if url else url


def search(keyword, limit=10):
    response = requests.get(f"{API}/search/subject/{quote(keyword)}",
                            params={"type": 2, "responseGroup": "medium", "max_results": limit},
                            headers=HEADERS, timeout=15)
    if response.status_code == 404:
        return []
    response.raise_for_status()
    data = response.json() if response.content else {}
    return [{
        "id": item["id"],
        "name": item.get("name") or "",
        "name_cn": item.get("name_cn") or "",
        "cover_url": _https((item.get("images") or {}).get("common")),
        "air_date": item.get("air_date") or None,
        "total_episodes": item.get("eps_count") or item.get("eps") or None,
    } for item in data.get("list") or []]


def subject(subject_id):
    response = requests.get(f"{API}/v0/subjects/{int(subject_id)}", headers=HEADERS, timeout=15)
    response.raise_for_status()
    item = response.json()
    return {
        "id": item["id"],
        "name": item.get("name") or "",
        "name_cn": item.get("name_cn") or "",
        "cover_url": _https((item.get("images") or {}).get("common")),
        "air_date": item.get("date") or None,
        "total_episodes": item.get("eps") or item.get("total_episodes") or None,
        "summary": item.get("summary") or None,
    }
