"""AI 이미지 생성 - 카드뉴스 배경용 '한국인 중심' 실사 이미지를 생성한다.

프로바이더는 환경변수로 선택(있는 키에 맞춰 자동):
  - OpenAI  : OPENAI_API_KEY  (gpt-image-1)
  - Google  : GOOGLE_API_KEY 또는 GEMINI_API_KEY (imagen-3.0-generate-002)
DG_IMAGE_PROVIDER=openai|google 로 강제 지정 가능. DG_IMAGE_MODEL로 모델 override.

키가 없으면 available()=False → 카드뉴스는 그라데이션 폴백으로 진행(파이프라인 안 멈춤).
생성 결과는 prompt 해시로 캐시(cache_dir)해 재실행 시 재생성 비용을 아낀다.

주의: 외부 이미지 API는 GitHub Actions(인터넷 개방)에서 동작. 일부 샌드박스는 egress 차단.
"""
import base64
import hashlib
import json
import os
import urllib.request
from pathlib import Path

OPENAI_KEY = os.getenv("OPENAI_API_KEY", "").strip()
GOOGLE_KEY = (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip()


def provider() -> str:
    forced = os.getenv("DG_IMAGE_PROVIDER", "").strip().lower()
    if forced:
        return forced
    if OPENAI_KEY:
        return "openai"
    if GOOGLE_KEY:
        return "google"
    return ""


def available() -> bool:
    p = provider()
    return (p == "openai" and bool(OPENAI_KEY)) or (p == "google" and bool(GOOGLE_KEY))


def _openai(prompt: str, size: str) -> bytes:
    model = os.getenv("DG_IMAGE_MODEL", "gpt-image-1")
    body = json.dumps({
        "model": model, "prompt": prompt, "n": 1,
        "size": size if size in ("1024x1024", "1536x1024", "1024x1536") else "1024x1024",
    }).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/images/generations", data=body,
        headers={"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read())
    return base64.b64decode(data["data"][0]["b64_json"])


def _google(prompt: str, size: str) -> bytes:
    """Google 이미지 생성.

    기본: gemini-2.5-flash-image(:generateContent) — 무료 AI Studio 키에서도 동작.
    DG_IMAGE_MODEL을 imagen-* 으로 지정하면 Imagen(:predict, 유료 빌링 필요) 사용.
    """
    model = os.getenv("DG_IMAGE_MODEL", "gemini-2.5-flash-image")
    base = "https://generativelanguage.googleapis.com/v1beta/models"

    if model.startswith("imagen"):
        body = json.dumps({
            "instances": [{"prompt": prompt}],
            "parameters": {"sampleCount": 1, "aspectRatio": "1:1"},
        }).encode()
        req = urllib.request.Request(
            f"{base}/{model}:predict?key={GOOGLE_KEY}",
            data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read())
        preds = data.get("predictions", [])
        if not preds:
            raise RuntimeError(f"Imagen 응답에 이미지 없음: {str(data)[:200]}")
        b64 = preds[0].get("bytesBase64Encoded") or preds[0].get("image", {}).get("imageBytes")
        return base64.b64decode(b64)

    # Gemini 이미지 생성 (nano banana): generateContent 응답의 inlineData에서 이미지 추출
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["IMAGE"]},
    }).encode()
    req = urllib.request.Request(
        f"{base}/{model}:generateContent?key={GOOGLE_KEY}",
        data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read())
    for cand in data.get("candidates", []):
        for part in (cand.get("content") or {}).get("parts", []):
            inline = part.get("inlineData") or part.get("inline_data") or {}
            if inline.get("data"):
                return base64.b64decode(inline["data"])
    raise RuntimeError(f"Gemini 이미지 응답에 inlineData 없음: {str(data)[:200]}")


def generate(prompt: str, cache_dir: str, size: str = "1024x1024") -> str | None:
    """prompt로 이미지를 생성해 PNG 경로를 반환. 실패/키없음이면 None."""
    if not available():
        return None
    p = provider()
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(f"{p}:{prompt}:{size}".encode()).hexdigest()[:16]
    fp = cache / f"gen_{key}.png"
    if fp.exists() and fp.stat().st_size > 0:
        return str(fp)
    try:
        raw = _openai(prompt, size) if p == "openai" else _google(prompt, size)
        fp.write_bytes(raw)
        return str(fp)
    except Exception as e:
        print(f"[image_gen] 생성 실패({p}): {type(e).__name__}: {e}", flush=True)
        return None
