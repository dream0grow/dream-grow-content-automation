"""콘텐츠 CRUD + 상태 전이 + 검수 라우터"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.constants import (
    ALLOWED_TRANSITIONS,
    THREADS_HARD_LIMIT,
    THREADS_STYLE_LIMIT,
    ContentStatus,
    ContentType,
)
from app.db.base import get_db
from app.db.models import Content
from app.schemas.content import (
    ContentCreate,
    ContentDetail,
    ContentListOut,
    ContentOut,
    ContentSummary,
    ContentUpdate,
    PostPreview,
    ReviewFixOut,
    ReviewResultOut,
    ScheduleAssign,
    StatusUpdate,
)
from app.services import reviewer
from app.services.splitter import split_posts

router = APIRouter(prefix="/contents", tags=["contents"])

EDITABLE_STATUSES = {ContentStatus.review_wait.value, ContentStatus.review_done.value}


def get_content_or_404(db: Session, content_id: int) -> Content:
    content = db.get(Content, content_id)
    if not content:
        raise HTTPException(404, "콘텐츠를 찾을 수 없습니다")
    return content


def _post_previews(content: Content) -> list[PostPreview]:
    if content.type != ContentType.thread.value:
        return []
    return [
        PostPreview(
            text=p, length=len(p),
            over_limit=len(p) > THREADS_HARD_LIMIT,
            over_style=len(p) > THREADS_STYLE_LIMIT,
        )
        for p in split_posts(content.body)
    ]


@router.get("", response_model=ContentListOut)
def list_contents(
    db: Session = Depends(get_db),
    status: str | None = None,
    type: str | None = None,
    category: str | None = None,
    q: str | None = None,
    limit: int = Query(100, le=500),
    offset: int = 0,
):
    stmt = select(Content)
    if status:
        stmt = stmt.where(Content.status == status)
    if type:
        stmt = stmt.where(Content.type == type)
    if category:
        stmt = stmt.where(Content.category == category)
    if q:
        stmt = stmt.where(or_(Content.title.contains(q), Content.body.contains(q)))

    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    items = db.scalars(
        stmt.order_by(Content.updated_at.desc()).limit(limit).offset(offset)
    ).all()
    return ContentListOut(
        items=[ContentSummary.model_validate(c) for c in items], total=total or 0
    )


@router.post("", response_model=ContentOut, status_code=201)
def create_content(payload: ContentCreate, db: Session = Depends(get_db)):
    content = Content(
        type=payload.type.value,
        title=payload.title,
        body=payload.body,
        category=payload.category,
        tone=payload.tone,
        status=ContentStatus.review_wait.value,
    )
    db.add(content)
    db.commit()
    db.refresh(content)
    return content


@router.get("/{content_id}", response_model=ContentDetail)
def get_content(content_id: int, db: Session = Depends(get_db)):
    content = get_content_or_404(db, content_id)
    children = db.scalars(
        select(Content).where(Content.parent_content_id == content_id)
    ).all()
    detail = ContentDetail.model_validate(content)
    detail.posts = _post_previews(content)
    detail.children = [ContentSummary.model_validate(c) for c in children]
    return detail


@router.put("/{content_id}", response_model=ContentOut)
def update_content(content_id: int, payload: ContentUpdate, db: Session = Depends(get_db)):
    content = get_content_or_404(db, content_id)
    if content.status not in EDITABLE_STATUSES:
        raise HTTPException(409, f"'{content.status}' 상태에서는 수정할 수 없습니다")
    for field in ("title", "body", "category", "tone"):
        value = getattr(payload, field)
        if value is not None:
            setattr(content, field, value)
    db.commit()
    db.refresh(content)
    return content


@router.delete("/{content_id}", status_code=204)
def delete_content(content_id: int, db: Session = Depends(get_db)):
    content = get_content_or_404(db, content_id)
    if content.status == ContentStatus.published.value:
        raise HTTPException(409, "발행완료된 콘텐츠는 삭제할 수 없습니다")
    db.delete(content)
    db.commit()


@router.post("/{content_id}/status", response_model=ContentOut)
def update_status(content_id: int, payload: StatusUpdate, db: Session = Depends(get_db)):
    content = get_content_or_404(db, content_id)
    new_status = payload.status.value

    allowed = ALLOWED_TRANSITIONS.get(content.status, set())
    if new_status not in allowed:
        raise HTTPException(409, f"'{content.status}' → '{new_status}' 전이는 허용되지 않습니다")

    # 리뷰완료 처리 시 ERROR 이슈가 있으면 force 필요
    if new_status == ContentStatus.review_done.value and not payload.force:
        result = reviewer.review(content.body, content.type)
        content.review_result = result
        if not result["passed"]:
            db.commit()
            raise HTTPException(409, "검수 ERROR 이슈가 있습니다. 수정 후 다시 시도하거나 force를 사용하세요")

    # 리뷰대기/리뷰완료로 되돌리면 예약 해제
    if new_status in (ContentStatus.review_wait.value, ContentStatus.review_done.value):
        content.scheduled_at = None

    content.status = new_status
    db.commit()
    db.refresh(content)
    return content


@router.post("/{content_id}/review", response_model=ReviewResultOut)
def run_review(content_id: int, db: Session = Depends(get_db)):
    content = get_content_or_404(db, content_id)
    result = reviewer.review(content.body, content.type)
    content.review_result = result
    db.commit()
    return result


@router.post("/{content_id}/review/fix", response_model=ReviewFixOut)
def run_review_fix(content_id: int, db: Session = Depends(get_db)):
    content = get_content_or_404(db, content_id)
    if content.status not in EDITABLE_STATUSES:
        raise HTTPException(409, f"'{content.status}' 상태에서는 수정할 수 없습니다")
    fixed_body, fixes = reviewer.apply_fixes(content.body)
    content.body = fixed_body
    result = reviewer.review(fixed_body, content.type)
    content.review_result = result
    db.commit()
    return ReviewFixOut(body=fixed_body, fixes=fixes, review=result)


@router.post("/{content_id}/schedule", response_model=ContentOut)
def schedule_content(content_id: int, payload: ScheduleAssign, db: Session = Depends(get_db)):
    content = get_content_or_404(db, content_id)

    if payload.scheduled_at is None:
        # 예약 해제
        if content.status != ContentStatus.publish_wait.value:
            raise HTTPException(409, "발행대기 상태가 아니라 예약을 해제할 수 없습니다")
        content.scheduled_at = None
        content.status = ContentStatus.review_done.value
    else:
        if content.status not in (
            ContentStatus.review_done.value, ContentStatus.publish_wait.value,
        ):
            raise HTTPException(409, "리뷰완료 또는 발행대기 상태만 예약할 수 있습니다")
        # 동일 슬롯 점유 검사
        occupied = db.scalar(
            select(func.count()).select_from(Content).where(
                Content.scheduled_at == payload.scheduled_at.replace(tzinfo=None),
                Content.id != content_id,
                Content.status.in_([
                    ContentStatus.publish_wait.value, ContentStatus.published.value,
                ]),
            )
        )
        if occupied:
            raise HTTPException(409, "해당 시간에 이미 예약된 콘텐츠가 있습니다")
        content.scheduled_at = payload.scheduled_at.replace(tzinfo=None)
        content.status = ContentStatus.publish_wait.value

    db.commit()
    db.refresh(content)
    return content
