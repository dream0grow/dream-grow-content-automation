"""Threads 자동 발행 - publish_ready 카드를 클라우드에서 발행 (로드맵 2단계)

threads_publisher.py의 API 흐름을 노션 카드 기반으로 이식했다.
발행 게이트: review_status=approved AND approval_status=approved 카드만 발행한다.
THREADS_ACCESS_TOKEN 미설정 시 카드를 needs_human으로 두고 수동 발행을 안내한다.
"""
import os
import re
import time
from datetime import datetime, timezone

import requests

from orchestrator import state as notion_state

THREADS_API_BASE = "https://graph.threads.net/v1.0"
THREADS_ACCESS_TOKEN = os.getenv("THREADS_ACCESS_TOKEN", "")
THREADS_USER_ID = os.getenv("THREADS_USER_ID", "")

POST_CHAR_LIMIT = 500


def available() -> bool:
    return bool(THREADS_ACCESS_TOKEN and THREADS_USER_ID)


def split_posts(draft: str) -> list[str]:
    """초안을 스레드 체인 글 목록으로 나눈다.

    '---' 구분자가 있으면 그 기준으로, 없으면 문단 단위로 500자 미만씩 묶는다.
    """
    draft = draft.strip()
    if re.search(r"\n-{3,}\n", draft):
        parts = re.split(r"\n-{3,}\n", draft)
        posts = []
        for part in parts:
            text = re.sub(r"^\[?\d+/\d+\]?\s*", "", part.strip())
            if text:
                posts.append(text[:POST_CHAR_LIMIT])
        return posts

    if len(draft) <= POST_CHAR_LIMIT:
        return [draft]

    posts, current = [], ""
    for para in draft.split("\n\n"):
        candidate = f"{current}\n\n{para}".strip() if current else para
        if len(candidate) <= POST_CHAR_LIMIT - 20:
            current = candidate
            continue
        if current:
            posts.append(current)
        # 한 문단이 글자 수 제한을 넘으면 문장 단위로 이월한다 (내용 유실 금지)
        current = ""
        for sentence in re.split(r"(?<=[.!?…])\s+|\n", para):
            if not sentence.strip():
                continue
            cand = f"{current} {sentence}".strip() if current else sentence.strip()
            if len(cand) <= POST_CHAR_LIMIT - 20:
                current = cand
            else:
                if current:
                    posts.append(current)
                # 문장 하나가 제한을 넘는 극단적 경우만 하드 컷
                current = sentence.strip()[:POST_CHAR_LIMIT - 20]
    if current:
        posts.append(current)
    return posts


def publish_chain(posts: list[str]) -> tuple[list[str], str]:
    """글 목록을 Threads 체인으로 발행한다.

    Returns: (발행된 media_id 목록, 첫 글 permalink)
    """
    media_ids: list[str] = []
    parent_id = None
    for i, text in enumerate(posts):
        params = {
            "media_type": "TEXT",
            "text": text[:POST_CHAR_LIMIT],
            "access_token": THREADS_ACCESS_TOKEN,
        }
        if parent_id:
            params["reply_to_id"] = parent_id
        resp = requests.post(
            f"{THREADS_API_BASE}/{THREADS_USER_ID}/threads",
            params=params, timeout=60,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"컨테이너 생성 실패 [{i + 1}]: {resp.text[:300]}")
        container_id = resp.json().get("id")

        pub = requests.post(
            f"{THREADS_API_BASE}/{THREADS_USER_ID}/threads_publish",
            params={"creation_id": container_id, "access_token": THREADS_ACCESS_TOKEN},
            timeout=60,
        )
        if pub.status_code != 200:
            raise RuntimeError(f"발행 실패 [{i + 1}]: {pub.text[:300]}")
        media_id = pub.json().get("id")
        media_ids.append(media_id)
        if i == 0:
            parent_id = media_id
        if i < len(posts) - 1:
            time.sleep(2)  # rate limit 준수

    permalink = ""
    if media_ids:
        try:
            info = requests.get(
                f"{THREADS_API_BASE}/{media_ids[0]}",
                params={"fields": "permalink", "access_token": THREADS_ACCESS_TOKEN},
                timeout=30,
            )
            permalink = info.json().get("permalink", "") if info.status_code == 200 else ""
        except requests.RequestException:
            permalink = ""
    return media_ids, permalink


def _publish_newsletter(page_id: str) -> bool:
    """뉴스레터를 스티비로 발행한다. 실제 발송에 성공하면 True를 반환한다.

    Secret 미설정·초안 없음·발송 실패·예외는 모두 False (카드에 기록 후 수동 안내 폴백).
    AUTO_SEND가 꺼져 초안만 생성된 경우도 sent=False라 False를 반환한다.
    """
    from orchestrator import stibee
    draft = notion_state.read_latest_section(page_id, "✍️ 초안 (newsletter)")
    if not draft.strip():
        return False
    if not stibee.available():
        notion_state.append_section(
            page_id, "📧 뉴스레터 발행 안내",
            "STIBEE_API_KEY/STIBEE_LIST_ID Secret이 없어 자동 발송을 건너뜁니다. "
            "'✍️ 초안 (newsletter)' 최종본을 스티비 에디터에 붙여넣어 발행하세요.",
        )
        return False
    try:
        result = stibee.create_and_send(draft)
        notion_state.append_section(
            page_id, "📧 뉴스레터 발행 기록 (스티비)",
            f"{result['detail']}\n제목: {stibee.extract_subject(draft)}",
        )
        return bool(result.get("sent"))
    except Exception as e:
        notion_state.append_section(
            page_id, "📧 뉴스레터 발행 실패 (스티비)",
            f"{e}\n\n'✍️ 초안 (newsletter)'를 스티비 에디터에 수동 붙여넣기 해주세요. "
            "오류 내용이 API payload 문제라면 orchestrator/stibee.py 조정이 필요합니다.",
        )
        return False


def handle_publish(card: dict):
    """publish_ready/queued 카드를 발행한다. run.py DISPATCH에서 호출."""
    page_id = card["page_id"]

    # 발행 게이트 재확인 (방어적 이중 체크)
    if card["review_status"] != "approved" or card["approval_status"] != "approved":
        notion_state.update_card(page_id, status="needs_human",
                                 last_error="발행 게이트 미충족 (review/approval)")
        return

    formats = [f.strip() for f in card["format"].split(",") if f.strip()]

    # 발행 전 문체 학습: 사람이 '✍️ 초안'을 수정했다면 AI 원본과 비교해 패턴 추출
    from orchestrator import style_learn
    for fmt in [f for f in formats if f in ("thread", "newsletter")]:
        try:
            style_learn.learn_from_edits(page_id, fmt)
        except Exception as e:
            print(f"문체 학습 실패 ({fmt}, 발행은 계속): {e}")

    # 뉴스레터: 스티비 API로 자동 발행 (미설정/실패 시 수동 붙여넣기 안내)
    newsletter_sent = False
    if "newsletter" in formats:
        newsletter_sent = _publish_newsletter(page_id)

    if "thread" not in formats:
        # newsletter 단독 카드: 실발송 성공이면 발행 완료 처리, 아니면 사람 확인 대기
        if newsletter_sent:
            notion_state.update_card(page_id, stage="published", status="done")
            notion_state.notify(
                page_id, f"🚀 [{card.get('content_id') or ''}] 뉴스레터 발송 완료.")
        else:
            notion_state.update_card(page_id, status="needs_human")
            notion_state.notify(
                page_id,
                f"⚠️ [{card.get('content_id') or ''}] 뉴스레터 자동 발송이 안 됐습니다. "
                "카드의 발행 안내 섹션을 확인해주세요 (Secret 미설정/AUTO_SEND 꺼짐/오류).",
            )
        return

    if not available():
        notion_state.append_section(
            page_id, "📤 발행 안내",
            "THREADS_ACCESS_TOKEN/THREADS_USER_ID Secret이 없어 자동 발행을 건너뜁니다. "
            "수동 발행 후 stage를 published로 바꾸거나, Secret 등록 후 status를 queued로 되돌리세요.",
        )
        notion_state.update_card(page_id, status="needs_human")
        notion_state.notify(
            page_id,
            f"⚠️ [{card.get('content_id') or ''}] Threads Secret이 없어 자동 발행을 "
            "건너뛰었습니다. 수동 발행하거나 Secret을 등록해주세요.",
        )
        return

    draft = (
        notion_state.read_latest_section(page_id, "✍️ 초안 (thread)")
        or notion_state.read_latest_section(page_id, "✍️ 초안")
    )
    if not draft.strip():
        raise RuntimeError("카드에서 '✍️ 초안' 섹션을 찾지 못했습니다")

    posts = split_posts(draft)
    media_ids, permalink = publish_chain(posts)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    notion_state.append_section(
        page_id, "📤 발행 기록",
        f"발행 시각: {timestamp}\n글 수: {len(media_ids)}개\n"
        f"media_ids: {', '.join(media_ids)}\npermalink: {permalink or '(조회 실패)'}",
    )
    fields = {"stage": "published", "status": "done"}
    if permalink:
        fields["published_url"] = permalink
    notion_state.update_card(page_id, **fields)
    # 성공도 폰에서 사이클이 닫히게 통지한다 (링크 포함)
    notion_state.notify(
        page_id,
        f"🚀 [{card.get('content_id') or ''}] Threads 발행 완료 "
        f"({len(media_ids)}개 체인) {permalink or ''}".strip(),
    )
