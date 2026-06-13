"""노션 상태 저장소 클라이언트 - 콘텐츠 파이프라인 DB 읽기/쓰기

콘텐츠 카드 하나 = 노션 페이지 하나.
속성(stage/status 등)은 자동화 라우팅에 쓰고,
산출물(리서치/키워드/브리프/초안/대화록)은 페이지 본문에 토글 블록으로 누적한다.
"""
import time
from datetime import datetime, timezone

import requests

from orchestrator.config import (
    NOTION_API_KEY, NOTION_PIPELINE_DB_ID, NOTION_VERSION,
)

BASE = "https://api.notion.com/v1"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _request(method: str, path: str, body: dict | None = None, retries: int = 3) -> dict:
    """노션 API 호출. 429/5xx는 지수 백오프로 재시도한다."""
    for attempt in range(retries + 1):
        resp = requests.request(
            method, f"{BASE}{path}", headers=_headers(), json=body, timeout=60,
        )
        if resp.status_code in (429, 500, 502, 503, 504) and attempt < retries:
            time.sleep(2 ** attempt * 2)
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError("notion request failed")


# ---------- 속성 파싱/생성 헬퍼 ----------

def _plain(prop: dict) -> str:
    """노션 속성 객체에서 평문을 추출한다."""
    t = prop.get("type")
    if t == "title":
        return "".join(x["plain_text"] for x in prop["title"])
    if t == "rich_text":
        return "".join(x["plain_text"] for x in prop["rich_text"])
    if t == "select":
        return (prop["select"] or {}).get("name", "")
    if t == "multi_select":
        return ",".join(x["name"] for x in prop["multi_select"])
    if t == "url":
        return prop.get("url") or ""
    return ""


def _rt(text: str) -> dict:
    return {"rich_text": [{"text": {"content": text[:1900]}}]} if text else {"rich_text": []}


def _sel(name: str) -> dict:
    return {"select": {"name": name}}


def card_from_page(page: dict) -> dict:
    """노션 페이지 객체를 다루기 쉬운 카드 dict로 변환한다."""
    props = page["properties"]
    get = lambda name: _plain(props[name]) if name in props else ""
    return {
        "page_id": page["id"],
        "created_time": page.get("created_time", ""),
        "last_edited_time": page.get("last_edited_time", ""),
        "topic": get("이름"),
        "content_id": get("content_id"),
        "stage": get("stage"),
        "status": get("status"),
        "audience": get("audience"),
        "format": get("format"),
        "priority": get("priority"),
        "approval_status": get("approval_status"),
        "review_status": get("review_status"),
        "approved_keyword": get("approved_keyword"),
        "manus_task_ids": get("manus_task_ids"),
        "idempotency_key": get("idempotency_key"),
    }


# ---------- 조회 ----------

def age_minutes(card: dict) -> float:
    """카드 생성 후 경과 분을 반환한다 (research 정체 판단용). 파싱 실패 시 큰 값."""
    ts = card.get("last_edited_time") or card.get("created_time")
    if not ts:
        return 9999.0
    try:
        created = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - created).total_seconds() / 60
    except ValueError:
        return 9999.0


def query_cards(stage: str | None = None, status: str | None = None,
                approval_status: str | None = None, page_size: int = 20) -> list[dict]:
    """stage/status 조합으로 카드를 조회한다."""
    conditions = []
    if stage:
        conditions.append({"property": "stage", "select": {"equals": stage}})
    if status:
        conditions.append({"property": "status", "select": {"equals": status}})
    if approval_status:
        conditions.append(
            {"property": "approval_status", "select": {"equals": approval_status}}
        )
    body: dict = {"page_size": page_size}
    if conditions:
        body["filter"] = {"and": conditions} if len(conditions) > 1 else conditions[0]
    data = _request("POST", f"/databases/{NOTION_PIPELINE_DB_ID}/query", body)
    return [card_from_page(p) for p in data.get("results", [])]


# ---------- 갱신 ----------

def update_card(page_id: str, **fields) -> None:
    """카드 속성을 갱신한다.

    예: update_card(pid, stage="research", status="running",
                    manus_task_ids="a,b,c", last_error="")
    """
    select_fields = {"stage", "status", "priority", "approval_status", "review_status"}
    text_fields = {
        "content_id", "audience", "approved_keyword",
        "manus_task_ids", "idempotency_key", "last_error",
    }
    props: dict = {}
    for key, value in fields.items():
        if key in select_fields:
            props[key] = _sel(value)
        elif key in text_fields:
            props[key] = _rt(value)
        elif key == "published_url":
            props[key] = {"url": value or None}
        else:
            raise ValueError(f"알 수 없는 필드: {key}")
    _request("PATCH", f"/pages/{page_id}", {"properties": props})


def next_content_id() -> str:
    """DG-{연도}-{순번} 형식의 content_id를 발급한다."""
    data = _request("POST", f"/databases/{NOTION_PIPELINE_DB_ID}/query", {
        "page_size": 100,
        "filter": {"property": "content_id", "rich_text": {"is_not_empty": True}},
    })
    year = datetime.now(timezone.utc).year
    prefix = f"DG-{year}-"
    max_n = 0
    for page in data.get("results", []):
        cid = _plain(page["properties"].get("content_id", {}))
        if cid.startswith(prefix):
            try:
                max_n = max(max_n, int(cid.removeprefix(prefix)))
            except ValueError:
                continue
    return f"{prefix}{max_n + 1:04d}"


# ---------- 페이지 본문 기록 ----------

def _chunks(text: str, size: int = 1900) -> list[str]:
    return [text[i:i + size] for i in range(0, len(text), size)] or [""]


def append_section(page_id: str, heading: str, body: str) -> None:
    """카드 본문에 '단계 산출물' 토글 섹션을 추가한다.

    예: append_section(pid, "🔍 리서치 요약", summary_text)
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    children = [
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": [{"text": {"content": chunk}}]},
        }
        for chunk in _chunks(body)[:90]  # 블록 100개 제한 보호
    ]
    block = {
        "object": "block",
        "type": "toggle",
        "toggle": {
            "rich_text": [{"text": {"content": f"{heading} ({timestamp})"}}],
            "children": children,
        },
    }
    _request("PATCH", f"/blocks/{page_id}/children", {"children": [block]})


def read_sections(page_id: str) -> str:
    """카드 본문(토글 + 문단)을 평문으로 읽는다. 다음 단계 에이전트의 입력으로 사용."""
    lines: list[str] = []
    cursor = None
    while True:
        path = f"/blocks/{page_id}/children?page_size=100"
        if cursor:
            path += f"&start_cursor={cursor}"
        data = _request("GET", path)
        for block in data.get("results", []):
            btype = block["type"]
            rich = block.get(btype, {}).get("rich_text", [])
            text = "".join(x["plain_text"] for x in rich)
            if text:
                lines.append(text)
            if block.get("has_children"):
                lines.append(read_sections(block["id"]))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return "\n".join(lines)


def read_latest_section(page_id: str, heading_prefix: str) -> str:
    """카드 본문에서 heading_prefix로 시작하는 가장 최근 토글의 내용을 읽는다.

    예: read_latest_section(pid, "✍️ 초안") → 발행할 초안 텍스트
    """
    matches: list[str] = []
    cursor = None
    while True:
        path = f"/blocks/{page_id}/children?page_size=100"
        if cursor:
            path += f"&start_cursor={cursor}"
        data = _request("GET", path)
        for block in data.get("results", []):
            if block["type"] != "toggle":
                continue
            heading = "".join(
                x["plain_text"] for x in block["toggle"].get("rich_text", [])
            )
            if heading.startswith(heading_prefix):
                matches.append(block["id"])
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    if not matches:
        return ""
    return read_sections(matches[-1])


def create_card(topic: str, *, stage: str = "intake", status: str = "queued",
                audience: str = "", body: str = "") -> str:
    """새 콘텐츠 카드(또는 큐시트)를 생성하고 page_id를 반환한다."""
    props = {
        "이름": {"title": [{"text": {"content": topic[:200]}}]},
        "stage": _sel(stage),
        "status": _sel(status),
        "content_id": _rt(next_content_id()),
    }
    if audience:
        props["audience"] = _rt(audience)
    page = _request("POST", "/pages", {
        "parent": {"database_id": NOTION_PIPELINE_DB_ID},
        "properties": props,
    })
    if body:
        append_section(page["id"], "📋 상세", body)
    return page["id"]
