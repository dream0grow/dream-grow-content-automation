"""실물 스톡 사진 검색 - 저작권 안전한 상업용 라이선스 사진을 가져온다.

프로바이더(있는 키로 자동 선택):
  - Pexels   : PEXELS_API_KEY          (무료, 상업적 사용 허용, 출처표기 불필요)
  - Unsplash : UNSPLASH_ACCESS_KEY     (무료, 상업적 사용 허용)
DG_STOCK_PROVIDER=pexels|unsplash 로 강제 지정 가능.

fetch(query, cache_dir)는 이미지를 내려받아 로컬 PNG/JPG 경로를 반환(없으면 None).
쿼리 해시로 캐시해 재실행 비용을 줄인다. 키 없으면 available()=False.
"""
import hashlib
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

PEXELS_KEY = os.getenv("PEXELS_API_KEY", "").strip()
UNSPLASH_KEY = os.getenv("UNSPLASH_ACCESS_KEY", "").strip()


def provider() -> str:
    forced = os.getenv("DG_STOCK_PROVIDER", "").strip().lower()
    if forced:
        return forced
    if PEXELS_KEY:
        return "pexels"
    if UNSPLASH_KEY:
        return "unsplash"
    return ""


def available() -> bool:
    p = provider()
    return (p == "pexels" and bool(PEXELS_KEY)) or (p == "unsplash" and bool(UNSPLASH_KEY))


def _pexels_url(query: str) -> str:
    url = ("https://api.pexels.com/v1/search?per_page=1&orientation=square&query="
           + urllib.parse.quote(query))
    req = urllib.request.Request(url, headers={"Authorization": PEXELS_KEY})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    photos = data.get("photos", [])
    if not photos:
        return ""
    src = photos[0].get("src", {})
    return src.get("large2x") or src.get("large") or src.get("original") or ""


def _unsplash_url(query: str) -> str:
    url = ("https://api.unsplash.com/search/photos?per_page=1&orientation=squarish&query="
           + urllib.parse.quote(query))
    req = urllib.request.Request(url, headers={"Authorization": f"Client-ID {UNSPLASH_KEY}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    results = data.get("results", [])
    if not results:
        return ""
    return results[0].get("urls", {}).get("regular", "")


def fetch(query: str, cache_dir: str) -> str | None:
    """query로 스톡 사진 1장을 내려받아 로컬 경로를 반환. 실패/키없음이면 None."""
    if not available() or not query.strip():
        return None
    p = provider()
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(f"{p}:{query}".encode()).hexdigest()[:16]
    fp = cache / f"stock_{key}.jpg"
    if fp.exists() and fp.stat().st_size > 0:
        return str(fp)
    try:
        img_url = _pexels_url(query) if p == "pexels" else _unsplash_url(query)
        if not img_url:
            return None
        req = urllib.request.Request(img_url, headers={"User-Agent": "dreamgrow-cardnews"})
        with urllib.request.urlopen(req, timeout=60) as r:
            fp.write_bytes(r.read())
        return str(fp)
    except Exception as e:
        print(f"[stock] 조회 실패({p}, {query}): {type(e).__name__}: {e}", flush=True)
        return None
