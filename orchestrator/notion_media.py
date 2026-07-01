"""카드뉴스 산출물을 노션 카드에 저장하고 앱 푸시 알림을 보낸다.

- 카피(슬라이드 텍스트) → 카드 본문 섹션
- 완성 카드 PNG(로컬) → 노션 파일 업로드 API로 이미지 블록 첨부
- 영상(힉스필드 URL 등) → 비디오 블록(외부 URL) 또는 파일 업로드
- 저장 후 notify()로 멘션 댓글 → 노션 모바일 앱 푸시 알림

파이프라인(Actions)은 NOTION_API_KEY로 REST 호출하므로 이 모듈이 그대로 동작한다.
"""
import mimetypes
from pathlib import Path

import requests

from orchestrator import notion_state
from orchestrator.config import NOTION_API_KEY, NOTION_VERSION

API = "https://api.notion.com/v1"


def _headers(extra: dict | None = None) -> dict:
    h = {"Authorization": f"Bearer {NOTION_API_KEY}", "Notion-Version": NOTION_VERSION}
    if extra:
        h.update(extra)
    return h


def upload_file(path: str) -> str:
    """로컬 파일을 노션에 업로드하고 file_upload id를 반환한다 (Notion File Upload API)."""
    p = Path(path)
    ct = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
    r = requests.post(f"{API}/file_uploads",
                      headers=_headers({"Content-Type": "application/json"}),
                      json={"filename": p.name, "content_type": ct}, timeout=60)
    r.raise_for_status()
    up = r.json()
    with open(p, "rb") as f:
        r2 = requests.post(up["upload_url"], headers=_headers(),
                           files={"file": (p.name, f, ct)}, timeout=180)
    r2.raise_for_status()
    return up["id"]


def _append(page_id: str, children: list[dict]) -> None:
    if children:
        notion_state._request("PATCH", f"/blocks/{page_id}/children", {"children": children})


def append_images(page_id: str, paths=None, urls=None) -> int:
    children = []
    for u in (urls or []):
        children.append({"type": "image", "image": {"type": "external", "external": {"url": u}}})
    for p in (paths or []):
        try:
            uid = upload_file(p)
            children.append({"type": "image", "image": {"type": "file_upload", "file_upload": {"id": uid}}})
        except Exception as e:
            print(f"[notion_media] 이미지 첨부 실패 {p}: {e}", flush=True)
    _append(page_id, children)
    return len(children)


def append_video(page_id: str, url: str = "", path: str = "") -> None:
    try:
        if path:
            uid = upload_file(path)
            _append(page_id, [{"type": "video", "video": {"type": "file_upload", "file_upload": {"id": uid}}}])
        elif url:
            _append(page_id, [{"type": "video", "video": {"type": "external", "external": {"url": url}}}])
    except Exception as e:
        print(f"[notion_media] 영상 블록 실패({e}) → 링크로 대체", flush=True)
        if url:
            _append(page_id, [{"type": "bookmark", "bookmark": {"url": url}}])


def save_cardnews(page_id: str, plan: dict, image_paths=None, image_urls=None,
                  video_url: str = "", video_path: str = "", notify: bool = True) -> None:
    """카드뉴스 계획+에셋을 노션 카드에 저장하고 앱 푸시를 보낸다."""
    slides = plan.get("slides", [])
    lines = [f"**표지 미디어**: {plan.get('cover_media', '?')} — {plan.get('cover_reason', '')}", ""]
    for i, s in enumerate(slides, 1):
        lines.append(f"**{i}. {s.get('title', '')}**")
        lines.append(s.get("body", ""))
        lines.append("")
    notion_state.append_formatted_section(page_id, "🖼️ 카드뉴스 카피", "\n".join(lines))

    if plan.get("cover_media") == "video" and (video_url or video_path):
        append_video(page_id, url=video_url, path=video_path)
    n = append_images(page_id, paths=image_paths, urls=image_urls)

    if notify:
        extra = " + 영상" if (video_url or video_path) else ""
        notion_state.notify(
            page_id,
            f"🖼️ 카드뉴스가 노션에 저장됐어요 — 카드 {n}장{extra}. 확인해 주세요!")
