"""오케스트레이터 메인 - 노션 stage 상태 머신 (24시간 가동, 결정 #4)

GitHub Actions cron(30분)이 실행한다. 노션 DB에서 처리할 카드를 찾아
stage별 핸들러를 호출하고, 산출물을 카드 본문에 기록한 뒤 상태를 전환한다.

승인 게이트 (사람이 노션 모바일에서 처리):
  keyword_approval: approved_keyword 입력 + approval_status=approved
  approval:         approval_status=approved

실행:
  python3 -m orchestrator.run            # 전체 stage 1회 처리
  python3 -m orchestrator.run --stage intake  # 특정 stage만
"""
import json
import os
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator import (
    agent_dialogue, llm, manus_research, naver_keywords, prompts,
)
from orchestrator import state as notion_state
from orchestrator.config import (
    AUTO_APPROVE_KEYWORD, MAX_CARDS_PER_RUN, RUBRIC_SKIP_QUALITY,
    STALE_RUNNING_MINUTES,
)

# 사람이 재초안을 원할 때 수정 지시를 적어두는 섹션. handle_revision_requested가
# 이 섹션을 읽어 작가에게 되먹인다(없으면 일반 재작성).
REVISION_SECTION = "📝 수정 요청"

# 다음 실행에서 1회 자동 재시도를 표시하는 last_error 접두사(A3).
_RETRY_MARK = "[자동재시도]"

# 실패해도 status를 되돌려 다음 실행에 재시도해도 안전한 stage → 재큐 status.
# publish_ready는 부분 발행 후 재시도하면 중복 게시 위험이 있어 제외(즉시 사람 호출).
_REQUEUE_STATUS = {"intake": "queued", "research": "running", "keyword": "queued"}


def log(msg: str):
    print(f"[orchestrator] {msg}", flush=True)


def _fmt_json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _bullets(items) -> str:
    return "\n".join(f"- {x}" for x in (items or []) if str(x).strip())


def _fmt_research(r: dict) -> str:
    """리서치 결과 dict를 읽기 좋은 마크다운으로."""
    conf = {"low": "낮음", "medium": "보통", "high": "높음"}.get(r.get("confidence", ""), r.get("confidence", ""))
    return (
        f"## 핵심 발견\n{_bullets(r.get('key_findings'))}\n\n"
        f"## 부모의 실제 언어\n{_bullets(r.get('parent_language'))}\n\n"
        f"## 콘텐츠 기회\n{_bullets(r.get('content_opportunities'))}\n\n"
        f"## 주의할 표현\n{_bullets(r.get('risk_notes'))}\n\n"
        f"## 근거 출처\n{_bullets(r.get('source_links'))}\n\n"
        f"> 신뢰도: {conf}"
    )


def _fmt_brief(b: dict) -> str:
    """브리프 dict를 읽기 좋은 마크다운으로."""
    parts = [
        f"## {b.get('brief_title', '브리프')}",
        f"**대상 독자**: {b.get('target_reader', '')}",
        f"**부모의 고민**: {b.get('pain_sentence', '')}",
        f"**핵심 메시지**: {b.get('core_message', '')}",
        f"**반전 관점**: {b.get('contrarian_angle', '')}",
    ]
    if b.get("reaction_type"):
        parts.append(f"**부모 반응 유형**: {b.get('reaction_type')}")
    if b.get("parent_reactions"):
        parts.append(f"## 부모 반응(원문 느낌)\n{_bullets(b.get('parent_reactions'))}")
    parts.append(f"## 콘텐츠 구조\n{_bullets(b.get('outline'))}")
    parts.append(f"## 근거 앵커\n{_bullets(b.get('evidence_anchors'))}")
    parts.append(f"**CTA**: {b.get('cta', '')}")
    parts.append(f"## 금지 표현\n{_bullets(b.get('avoid_phrases'))}")
    return "\n\n".join(parts)


def _fmt_review(rv: dict) -> str:
    """교육윤리 검수 결과를 읽기 좋은 마크다운으로."""
    status = {"approved": "✅ 승인", "revise": "✏️ 수정 필요",
              "hold": "⛔ 보류", "risk": "🚨 위험"}.get(rv.get("review_status", ""), rv.get("review_status", ""))
    risk = {"low": "낮음", "medium": "보통", "high": "높음"}.get(rv.get("risk_level", ""), rv.get("risk_level", ""))
    return (
        f"## 검수 결과: {status}  (리스크: {risk})\n\n"
        f"## 발견된 문제\n{_bullets(rv.get('issues'))}\n\n"
        f"## 수정 제안\n{_bullets(rv.get('revision_suggestions'))}\n\n"
        f"> {rv.get('final_recommendation', '')}"
    )


def _fmt_score(s: dict) -> str:
    """글 평가 점수를 읽기 좋은 마크다운으로."""
    rows = [("훅", "hook"), ("가독성", "readability"), ("실천성", "actionability"),
            ("브랜드핏", "brand_fit"), ("공감", "empathy")]
    lines = [f"- {label}: {s.get(key, '?')}/10" for label, key in rows]
    return (
        f"## 총점 {s.get('total', '?')}/50\n"
        + "\n".join(lines)
        + f"\n\n**총평**: {s.get('one_line_review', '')}\n\n"
        f"**가장 약한 부분**: {s.get('weakest_part', '')}"
    )


# ---------- stage 핸들러 ----------

def handle_intake(card: dict):
    """intake/queued → 리서치 시작. Manus 우선, 없으면 Claude 폴백."""
    page_id = card["page_id"]
    content_id = card["content_id"] or notion_state.next_content_id()
    idem = f"{content_id}:research"
    if card["idempotency_key"] == idem:
        log(f"{content_id} 중복 실행 차단 (idempotency)")
        return
    notion_state.update_card(
        page_id, content_id=content_id, idempotency_key=idem,
        stage="research", status="running", last_error="",
    )
    if manus_research.available():
        task_ids = manus_research.create_research_tasks(
            content_id, card["topic"], card["audience"],
        )
        notion_state.update_card(page_id, manus_task_ids=",".join(task_ids))
        log(f"{content_id} Manus 리서치 {len(task_ids)}개 병렬 생성")
    else:
        results = manus_research.claude_research_fallback(
            card["topic"], card["audience"],
        )
        _save_research(page_id, results)
        notion_state.update_card(page_id, stage="keyword", status="queued")
        log(f"{content_id} Claude 폴백 리서치 {len(results)}건 완료 → keyword")


# research가 이 분(minute)을 넘겨도 안 끝나면 Manus가 막힌 것으로 보고 Claude로 우회
RESEARCH_STALL_MINUTES = int(os.getenv("DG_RESEARCH_STALL_MINUTES", "25"))


def handle_research(card: dict):
    """research/running → Manus 완료 폴링 → 키워드 단계로.

    Manus가 RESEARCH_STALL_MINUTES를 넘겨도 결과를 안 주면(느림/응답형식 불일치)
    Claude 폴백 리서치로 우회해 카드가 영구히 막히지 않게 한다.
    """
    page_id = card["page_id"]
    task_ids = [t for t in card["manus_task_ids"].split(",") if t.strip()]

    results, debug = [], ""
    if task_ids:
        try:
            all_done, results, debug = manus_research.poll_results(task_ids)
        except Exception as e:
            all_done, debug = False, f"poll 예외: {type(e).__name__}: {e}"
            log(f"{card['content_id']} Manus 폴링 실패: {e}")
        if all_done and results:
            _save_research(page_id, results)
            notion_state.update_card(page_id, stage="keyword", status="queued")
            log(f"{card['content_id']} 리서치 완료 → keyword")
            return

    age_min = notion_state.age_minutes(card)
    if age_min < RESEARCH_STALL_MINUTES:
        log(f"{card['content_id']} 리서치 진행 중 "
            f"({len(results)}/{len(task_ids)}, {age_min:.0f}분 경과)")
        return

    # 임계 시간 초과 → Claude 폴백 리서치로 우회 (Manus 부분 결과가 있으면 함께 저장)
    log(f"{card['content_id']} Manus {RESEARCH_STALL_MINUTES}분 초과 → Claude 폴백 우회")
    notion_state.append_section(
        page_id, "⚠️ Manus 리서치 우회",
        f"Manus 결과를 {RESEARCH_STALL_MINUTES}분 내에 받지 못해 Claude 리서치로 대체합니다.\n"
        f"마지막 폴링 디버그: {debug[:500]}",
    )
    if results:
        _save_research(page_id, results)
    fallback = manus_research.claude_research_fallback(card["topic"], card["audience"])
    _save_research(page_id, fallback)
    notion_state.update_card(page_id, stage="keyword", status="queued")
    log(f"{card['content_id']} Claude 폴백 리서치 {len(fallback)}건 → keyword")


def _save_research(page_id: str, results: list[dict]):
    for r in results:
        notion_state.append_formatted_section(
            page_id, f"🔍 리서치: {r.get('research_focus', '')[:40]}", _fmt_research(r),
        )


def handle_keyword(card: dict):
    """keyword/queued → Claude 점수화 → 사람 승인 대기."""
    # 키워드 점수화엔 리서치 산출물만 필요하다(누적 초안·검수 제외로 토큰 절감, B3).
    research = notion_state.read_sections_by_prefix(
        card["page_id"], "🔍 리서치", "📋 상세", "⚠️ Manus",
    )
    scored = llm.call_json(
        prompts.KEYWORD_SCORE.format(
            topic=card["topic"], audience=card["audience"], research=research[:20000],
        ),
        system=prompts.get_system(),
    )
    keywords = sorted(
        scored.get("keywords", []),
        key=lambda k: k.get("total_score", 0), reverse=True,
    )
    # 네이버 검색광고 API로 실측 검색량/경쟁도 보강 (키 미설정/실패 시 점수만 표시)
    volumes: dict = {}
    if naver_keywords.available():
        try:
            volumes = naver_keywords.fetch_volumes(
                [k.get("keyword", "") for k in keywords]
            )
        except Exception as e:
            log(f"네이버 키워드도구 조회 실패 (점수만 표시): {e}")
    lines = []
    for k in keywords:
        line = (
            f"- **{k.get('keyword')}** ({k.get('keyword_id')}, 총 {k.get('total_score')}점) "
            f"— {k.get('core_message', '')}"
        )
        if volumes:
            line += f"\n  ↳ {naver_keywords.format_volume(volumes.get(k.get('keyword', '')))}"
        lines.append(line)
    table = "\n".join(lines)
    notion_state.append_formatted_section(
        card["page_id"], "🏷️ 키워드 후보 (승인 필요)",
        f"## 키워드 후보 (점수순)\n{table}\n\n"
        f"> 승인 방법: 위 키워드 중 하나를 골라 approved_keyword 속성에 입력하고 "
        f"approval_status를 approved로 바꾸세요.",
    )
    # 자동 승인 모드: 최고점 키워드를 사람 승인 없이 채택 → 바로 브리프/초안으로 진행
    if AUTO_APPROVE_KEYWORD and keywords:
        top_kw = keywords[0].get("keyword", "")
        notion_state.update_card(
            card["page_id"], approved_keyword=top_kw,
            stage="keyword_approval", status="running", approval_status="approved",
        )
        log(f"{card['content_id']} 키워드 자동 승인: {top_kw}")
        return
    notion_state.update_card(
        card["page_id"], stage="keyword_approval", status="needs_human",
        approval_status="requested",
    )
    notion_state.notify(
        card["page_id"],
        f"🏷️ [{card['content_id']}] 키워드 승인이 필요합니다. "
        f"'{card['topic']}' — 키워드 표를 확인하고 approved_keyword 입력 후 "
        "approval_status를 approved로 바꿔주세요.",
    )
    log(f"{card['content_id']} 키워드 {len(keywords)}개 → 승인 대기 ⏸️")


def handle_keyword_approved(card: dict):
    """keyword_approval + approved → 브리프 → 토론 초안 → 검수까지 일괄 진행."""
    page_id = card["page_id"]
    keyword = card["approved_keyword"].strip()
    if not keyword:
        log(f"{card['content_id']} approved_keyword가 비어 있어 대기")
        return
    notion_state.update_card(
        page_id, stage="brief", status="running", approval_status="not_requested",
    )
    # 재초안 경로(handle_revision_requested)가 남긴 사람의 수정 지시가 있으면 반영한다.
    revision_note = notion_state.read_latest_section(page_id, REVISION_SECTION).strip()
    if revision_note:
        log(f"{card['content_id']} 수정 지시 반영해 재초안")
    # 브리프엔 리서치+키워드만 필요하다. 재초안 시 누적된 옛 초안/검수/평가를
    # 통째로 다시 싣지 않도록 관련 섹션만 고른다(B3, A1 재초안 경로와 시너지).
    context = notion_state.read_sections_by_prefix(
        page_id, "🔍 리서치", "📋 상세", "🏷️ 키워드", "📝 수정 요청",
    )
    brief = llm.call_json(
        prompts.BRIEF.format(
            keyword=keyword, topic=card["topic"],
            audience=card["audience"], context=context[:20000],
        ),
        system=prompts.get_system(),
    )
    notion_state.append_formatted_section(page_id, "📝 브리프", _fmt_brief(brief))

    formats = [f.strip() for f in card["format"].split(",") if f.strip()]
    supported = [f for f in formats if f in ("thread", "newsletter")] or ["thread"]
    notion_state.update_card(page_id, stage="draft", status="running")

    rank = {"approved": 0, "revise": 1, "hold": 2, "risk": 3}
    worst_review = "approved"
    for fmt in supported:
        result = agent_dialogue.run_draft_dialogue(
            brief, fmt, style_context=agent_dialogue.get_style_context(fmt),
            hook_examples=agent_dialogue.load_hooks(),
            benchmark=agent_dialogue.load_benchmark(fmt),
            extra_directive=revision_note,
        )
        notion_state.append_section(
            page_id, f"💬 에이전트 토론 ({fmt}, {result['rounds']}라운드)",
            result["transcript"],
        )
        # AI 원본은 문체 diff 학습용으로 보존, 사람은 '✍️ 초안'만 수정한다
        notion_state.append_section(
            page_id, f"🗄️ AI 원본 ({fmt}) - 수정 금지", result["draft"],
        )
        notion_state.append_section(page_id, f"✍️ 초안 ({fmt})", result["draft"])

        review = result["review"]
        notion_state.append_formatted_section(
            page_id, f"✅ 교육윤리 검수 ({fmt})", _fmt_review(review),
        )
        if rank.get(review.get("review_status", "revise"), 1) > rank[worst_review]:
            worst_review = review.get("review_status", "revise")

        # 자동 글 평가 - 사람 검수자가 승인 판단에 참고
        quality_total = None
        try:
            score = llm.call_json(
                prompts.QUALITY_SCORE.format(format=fmt, draft=result["draft"]),
                system=prompts.get_system(),
            )
            quality_total = score.get("total")
            notion_state.append_formatted_section(
                page_id,
                f"📊 글 평가 ({fmt}) - 총 {score.get('total', '?')}/50점",
                _fmt_score(score),
            )
        except Exception as e:
            log(f"{card['content_id']} 글 평가 실패 ({fmt}): {e}")

        # 평가표(사용자 글 기준) AI 검토 + 2차안(줄바꿈 교정) 토글 추가.
        # 글 평가 총점이 충분히 높으면 비싼 전문 재작성(2차안)을 생략해 토큰을 아낀다(B2).
        try:
            if (isinstance(quality_total, (int, float))
                    and quality_total >= RUBRIC_SKIP_QUALITY):
                log(f"{card['content_id']} 글 평가 {quality_total}점 → 2차안 생략 ({fmt})")
            else:
                from orchestrator import rubric_review
                if rubric_review.run_for_card(page_id, fmt, skip_if_exists=True):
                    log(f"{card['content_id']} 2차안 추가 ({fmt})")
        except Exception as e:
            log(f"{card['content_id']} 평가표 검토/2차안 실패 ({fmt}): {e}")

    notion_state.append_section(
        page_id, "⏸️ 발행 승인 요청",
        "확인 순서: 📊 글 평가 점수 → ✅ 검수 결과 → ✍️ 초안 본문.\n"
        "초안을 직접 수정해도 됩니다 ('✍️ 초안' 토글 안에서만, AI 원본은 그대로 두세요). "
        "수정분은 발행 시 자동으로 문체 학습에 반영됩니다.\n"
        "approval_status를 approved로 바꾸면 thread는 Threads에, "
        "newsletter는 스티비로 자동 발행됩니다 (STIBEE_AUTO_SEND가 꺼져 있으면 "
        "스티비에 초안만 생성되니 대시보드에서 확인 후 발송하세요). "
        f"수정을 원하면 '{REVISION_SECTION}' 토글(섹션)에 고칠 점을 적고 "
        "approval_status=revision_requested로 바꾸세요 → 지시를 반영해 재초안합니다.",
    )
    notion_state.update_card(
        page_id, stage="approval", status="needs_human",
        review_status=worst_review,
        approval_status="requested",
    )
    notion_state.notify(
        page_id,
        f"✍️ [{card['content_id']}] 초안 완성, 발행 승인이 필요합니다. "
        f"'{card['topic']}' — 글 평가/검수와 초안을 확인하고 approval_status를 "
        "approved로 바꾸면 자동 발행됩니다.",
    )
    log(f"{card['content_id']} 초안 {len(supported)}종 + 검수/평가 완료 → 발행 승인 대기 ⏸️")


def handle_final_approved(card: dict):
    """approval + approved → 검수 통과면 publish_ready, 아니면 사유를 사람에게 통지.

    검수가 approved가 아닌데 사람이 발행 승인을 누른 경우, 예전엔 로그만 남기고
    조용히 막혀 카드가 영구 정체됐다(A2). 이제는 needs_human으로 디큐하고 이유와
    다음 행동(초안 수정 후 재승인 / 재초안 요청)을 통지해 침묵을 없앤다.
    """
    page_id = card["page_id"]
    if card["review_status"] != "approved":
        rv = card["review_status"] or "미검수"
        notion_state.update_card(
            page_id, status="needs_human", approval_status="blocked",
        )
        notion_state.notify(
            page_id,
            f"⛔ [{card['content_id']}] 발행 승인을 눌렀지만 교육윤리 검수가 "
            f"'{rv}' 상태라 자동 발행을 멈췄습니다. 초안을 고친 뒤 review_status를 "
            f"approved로 바꿔 다시 approval_status=approved 하거나, "
            f"'{REVISION_SECTION}'에 지시를 적고 approval_status=revision_requested로 "
            "재초안을 요청하세요.",
        )
        log(f"{card['content_id']} 검수 {rv} → 발행 차단, 사람 통지 ⏸️")
        return
    notion_state.update_card(page_id, stage="publish_ready", status="queued")
    log(f"{card['content_id']} publish_ready → 발행 대기열")


def handle_revision_requested(card: dict):
    """approval + revision_requested → 재초안 경로로 되돌린다(A1).

    예전엔 이 상태를 처리하는 핸들러가 없어 '수정 요청'이 영구 방치됐다. 이제는
    keyword_approval/approved로 되돌려 handle_keyword_approved가 '{REVISION_SECTION}'의
    사람 지시를 반영해 브리프→초안을 다시 만들고 발행 승인 대기로 재진입시킨다.
    """
    page_id = card["page_id"]
    if not card["approved_keyword"].strip():
        # 키워드가 없으면 재생성이 불가하므로 키워드 승인 대기로 되돌린다.
        notion_state.update_card(
            page_id, stage="keyword_approval", status="needs_human",
            approval_status="requested",
        )
        notion_state.notify(
            page_id,
            f"↩️ [{card['content_id']}] 수정 요청을 받았지만 approved_keyword가 비어 "
            "키워드부터 다시 골라야 합니다.",
        )
        return
    note = notion_state.read_latest_section(page_id, REVISION_SECTION).strip()
    notion_state.update_card(
        page_id, stage="keyword_approval", status="running", approval_status="approved",
    )
    log(f"{card['content_id']} 수정 요청 → 재초안 큐 (지시 {'있음' if note else '없음'}) 🔁")


def handle_publish(card: dict):
    """publish_ready/queued → Threads 자동 발행 (로드맵 2단계)."""
    from orchestrator import publish
    publish.handle_publish(card)
    log(f"{card['content_id']} 발행 처리 완료")


def handle_rubric_backfill():
    """기존 모든 카드(초안 보유)에 평가표 검토 + 2차안 토글을 소급 적용한다.

    초안 단계 이후의 카드는 자동으로 다시 흐르지 않으므로, workflow_dispatch로 1회 실행한다:
      python3 -m orchestrator.run --stage rubric_backfill
    이미 '✍️ 2차안'이 있는 카드/포맷은 건너뛴다(idempotent).
    """
    from orchestrator import rubric_review
    seen, count = set(), 0
    for stage in ("draft", "approval", "publish_ready", "published"):
        for card in notion_state.query_cards(stage=stage, page_size=50):
            page_id = card["page_id"]
            if page_id in seen:
                continue
            seen.add(page_id)
            formats = [f.strip() for f in card["format"].split(",") if f.strip()] or ["thread"]
            for fmt in formats:
                if fmt not in ("thread", "newsletter"):
                    continue
                try:
                    if rubric_review.run_for_card(page_id, fmt, skip_if_exists=True):
                        count += 1
                        log(f"{card.get('content_id')} 2차안 추가 ({fmt})")
                except Exception as e:
                    log(f"{card.get('content_id')} 2차안 실패 ({fmt}): {e}")
    log(f"평가표 백필 완료: {len(seen)}개 카드 점검, 2차안 {count}건 추가")


# ---------- 디스패처 ----------

DISPATCH = [
    # (stage, status, approval_status, handler)
    ("intake", "queued", None, handle_intake),
    ("research", "running", None, handle_research),
    ("keyword", "queued", None, handle_keyword),
    ("keyword_approval", None, "approved", handle_keyword_approved),
    ("approval", None, "approved", handle_final_approved),
    ("approval", None, "revision_requested", handle_revision_requested),
    ("publish_ready", "queued", None, handle_publish),
]

# 쿼리가 status를 안 보는(status=None) stage. 실패 시 approval_status로 디큐해야 한다.
_STATUS_AGNOSTIC = {"keyword_approval", "approval"}


def _handle_failure(card: dict, stage: str, exc: Exception):
    """핸들러 예외를 처리한다: 안전한 stage는 1회 자동 재시도, 이후 실패는 사람 통지(A3).

    - intake/research/keyword: status를 되돌려 다음 실행에 1회 재시도.
    - keyword_approval/approval: 쿼리가 status 무시라 그대로 두면 다음 실행에 재시도됨.
    - 재시도 표식(last_error 접두사)이 이미 있으면 포기하고 needs_human + 통지.
    - publish_ready는 여기 오지 않는다(부분발행 중복 위험 → 재시도 대상 제외).
    """
    page_id = card["page_id"]
    cid = card.get("content_id") or page_id
    err = f"{type(exc).__name__}: {exc}"
    already_retried = card.get("last_error", "").startswith(_RETRY_MARK)
    can_retry = (stage in _REQUEUE_STATUS or stage in _STATUS_AGNOSTIC)

    if can_retry and not already_retried:
        fields = {"last_error": f"{_RETRY_MARK} {err}"[:1500]}
        if stage in _REQUEUE_STATUS:
            fields["status"] = _REQUEUE_STATUS[stage]
        notion_state.update_card(page_id, **fields)
        log(f"{cid} {stage} 실패 → 다음 실행에서 1회 자동 재시도 ({err[:120]})")
        return

    fields = {"status": "failed", "last_error": err[:1500]}
    if stage in _STATUS_AGNOSTIC:
        fields["approval_status"] = "failed"  # status 무시 쿼리에서 빼내 무한 재시도 방지
    notion_state.update_card(page_id, **fields)
    notion_state.notify(
        page_id,
        f"⚠️ [{cid}] '{stage}' 처리가 실패해 멈췄습니다: {err[:300]} — 확인이 필요합니다.",
    )
    log(f"{cid} {stage} 실패 → needs_human 통지")


def _sweep_stale_running(now_limit: int = STALE_RUNNING_MINUTES):
    """brief/draft 단계에서 running으로 오래 멈춘 고아 카드를 재큐한다(A4).

    handle_keyword_approved가 brief/running·draft/running으로 상태를 바꿔가며 여러 번
    LLM을 호출하는데, 도중에 Actions가 죽으면 그 stage를 다시 집는 핸들러가 없어
    카드가 영구 고아가 된다. 일정 시간 방치되면 keyword_approval/approved로 되돌려
    재생성 경로에 다시 태운다.
    """
    for stage in ("brief", "draft"):
        for card in notion_state.query_cards(stage=stage, status="running", page_size=20):
            age = notion_state.age_minutes(card)
            if age < now_limit:
                continue
            if not card.get("approved_keyword", "").strip():
                continue  # 키워드가 없으면 재생성 불가 — 건너뛴다
            notion_state.update_card(
                card["page_id"], stage="keyword_approval", status="running",
                approval_status="approved",
            )
            cid = card.get("content_id") or card["page_id"]
            notion_state.notify(
                card["page_id"],
                f"🔁 [{cid}] 초안 생성이 {age:.0f}분째 멈춰 있어 재시도합니다.",
            )
            log(f"{cid} {stage} 고아({age:.0f}분) → 재초안 큐")


def run(only_stage: str | None = None):
    notion_state.require_backend()
    if not only_stage:
        try:
            _sweep_stale_running()
        except Exception as e:  # noqa: BLE001 — 청소 실패가 본 처리를 막으면 안 됨
            log(f"고아 카드 청소 실패(계속 진행): {e}")
    processed = 0
    for stage, status, approval, handler in DISPATCH:
        if only_stage and stage != only_stage:
            continue
        cards = notion_state.query_cards(
            stage=stage, status=status, approval_status=approval,
        )
        for card in cards:
            if processed >= MAX_CARDS_PER_RUN:
                log(f"실행당 최대 {MAX_CARDS_PER_RUN}개 도달, 다음 cron에 계속")
                return
            try:
                handler(card)
                processed += 1
            except Exception as e:
                traceback.print_exc()
                _handle_failure(card, stage, e)
    log(f"완료: {processed}개 카드 처리")


if __name__ == "__main__":
    stage_arg = None
    if "--stage" in sys.argv:
        stage_arg = sys.argv[sys.argv.index("--stage") + 1]
    if stage_arg == "rubric_backfill":
        notion_state.require_backend()
        handle_rubric_backfill()
    else:
        run(stage_arg)
