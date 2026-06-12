"""Threads 발행 서비스 - 레거시 threads_publisher.py 포팅 (httpx + DB 기반)

API 흐름 (글마다): POST /{user_id}/threads (컨테이너 생성, 답글은 reply_to_id)
              → POST /{user_id}/threads_publish (creation_id로 발행)
포스트 간 2초 대기 (레이트 리밋). 토큰 미설정/PUBLISH_DRY_RUN 시 dry-run.
"""
import time
from datetime import datetime

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import THREADS_HARD_LIMIT, ContentStatus, ContentType
from app.db.models import Content, PublishLog
from app.services.splitter import split_posts


class PublishError(Exception):
    pass


def _publish_posts_to_threads(posts: list[str], settings) -> list[dict]:
    """Threads API로 글 목록을 순차 발행. 부분 실패 시 PublishError(발행된 ID 포함)."""
    published: list[dict] = []
    parent_id = None

    with httpx.Client(timeout=30) as client:
        for i, post_text in enumerate(posts):
            params = {
                "media_type": "TEXT",
                "text": post_text,
                "access_token": settings.threads_access_token,
            }
            if parent_id:
                params["reply_to_id"] = parent_id

            resp = client.post(
                f"{settings.threads_api_base}/{settings.threads_user_id}/threads",
                params=params,
            )
            if resp.status_code != 200:
                raise PublishError(
                    f"{i + 1}번 글 컨테이너 생성 실패 ({resp.status_code}): "
                    f"{resp.text[:200]} | 발행된 글: {[p['id'] for p in published]}"
                )
            container_id = resp.json().get("id")

            pub_resp = client.post(
                f"{settings.threads_api_base}/{settings.threads_user_id}/threads_publish",
                params={
                    "creation_id": container_id,
                    "access_token": settings.threads_access_token,
                },
            )
            if pub_resp.status_code != 200:
                raise PublishError(
                    f"{i + 1}번 글 발행 실패 ({pub_resp.status_code}): "
                    f"{pub_resp.text[:200]} | 발행된 글: {[p['id'] for p in published]}"
                )

            media_id = pub_resp.json().get("id")
            published.append({"id": media_id})

            if i == 0:
                parent_id = media_id
            if i < len(posts) - 1:
                time.sleep(2)

    return published


def publish_content(db: Session, content: Content) -> PublishLog:
    """콘텐츠를 발행하고 상태/로그를 갱신한다. 호출 측에서 상태 검증 완료 가정."""
    settings = get_settings()
    log = PublishLog(content_id=content.id)

    try:
        if content.type == ContentType.thread.value:
            posts = split_posts(content.body)
            if not posts:
                raise PublishError("발행할 내용이 없습니다 (본문이 비어 있음)")
            over = [(i + 1, len(p)) for i, p in enumerate(posts) if len(p) > THREADS_HARD_LIMIT]
            if over:
                detail = ", ".join(f"{n}번 글 {ln}자" for n, ln in over)
                raise PublishError(f"Threads {THREADS_HARD_LIMIT}자 제한 초과: {detail}")
            log.posts_count = len(posts)

            if settings.effective_dry_run:
                results = [{"id": f"dry-run-{i}"} for i in range(len(posts))]
                log.dry_run = True
            else:
                results = _publish_posts_to_threads(posts, settings)

            content.external_ids = results
            content.external_id = results[0]["id"] if results else None
        else:
            # 릴스/뉴스레터는 외부 발행 API 없음 - 상태 변경만
            log.posts_count = 1
            log.dry_run = True

        content.status = ContentStatus.published.value
        content.published_at = datetime.now()
        log.success = True
    except PublishError as e:
        content.status = ContentStatus.failed.value
        log.success = False
        log.error = str(e)
    except httpx.HTTPError as e:
        content.status = ContentStatus.failed.value
        log.success = False
        log.error = f"네트워크 오류: {e}"

    db.add(log)
    db.commit()
    db.refresh(log)
    return log
