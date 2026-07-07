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
from orchestrator.config import AUTO_APPROVE_KEYWORD, MAX_CARDS_PER_RUN


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
    # 토큰 절약: 카드 본문 전체 대신 리서치 섹션만 넣는다
    research = (notion_state.read_sections_by_prefix(card["page_id"], "🔍 리서치")
                or notion_state.read_sections(card["page_id"]))
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
    # 토큰 절약: 브리프에 필요한 섹션(리서치+키워드 표+상세)만 넣는다
    context = "\n\n".join(filter(None, (
        notion_state.read_sections_by_prefix(page_id, "🔍 리서치"),
        notion_state.read_sections_by_prefix(page_id, "🏷️ 키워드 후보"),
        notion_state.read_sections_by_prefix(page_id, "📋 상세"),
    ))) or notion_state.read_sections(page_id)
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

        # 평가표(사용자 글 기준) AI 검토 + 2차안(줄바꿈 교정) 토글 추가.
        # 별도 글 평가(QUALITY_SCORE)는 평가표 채점과 중복이라 제거했다 (토큰 절약)
        try:
            from orchestrator import rubric_review
            if rubric_review.run_for_card(page_id, fmt, skip_if_exists=True):
                log(f"{card['content_id']} 2차안 추가 ({fmt})")
        except Exception as e:
            log(f"{card['content_id']} 평가표 검토/2차안 실패 ({fmt}): {e}")

    notion_state.append_section(
        page_id, "⏸️ 발행 승인 요청",
        "확인 순서: 📐 평가표 점검 → ✅ 검수 결과 → ✍️ 초안 본문.\n"
        "초안을 직접 수정해도 됩니다 ('✍️ 초안' 토글 안에서만, AI 원본은 그대로 두세요). "
        "수정분은 발행 시 자동으로 문체 학습에 반영됩니다.\n"
        "① 발행: approval_status를 approved로 — thread는 Threads, newsletter는 스티비로 자동 발행.\n"
        "② AI에게 수정 시키기: '🛠 수정 지시' 섹션(토글)을 만들어 지시를 적고 "
        "approval_status를 revision_requested로 — 다음 실행이 재작성해 다시 승인 요청합니다.",
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
    """approval + approved + 검수 통과 → publish_ready (같은 실행에서 발행까지 이어짐)."""
    if card["review_status"] != "approved":
        # 조용히 차단하면 카드가 영구 정체된다(과거 6장 데드엔드의 원인).
        # 승인 요청 상태로 되돌리고 이유와 다음 행동을 사람에게 통지한다.
        notion_state.update_card(
            card["page_id"], status="needs_human", approval_status="requested",
        )
        notion_state.notify(
            card["page_id"],
            f"⛔ [{card['content_id']}] 승인하셨지만 검수 상태가 "
            f"'{card['review_status']}'라 발행을 막았습니다. 선택지:\n"
            "① AI 재작성: '🛠 수정 지시' 섹션에 지시를 적고 "
            "approval_status=revision_requested\n"
            "② 검수 무시하고 발행: review_status를 approved로 바꾼 뒤 "
            "approval_status를 다시 approved로",
        )
        log(f"{card['content_id']} review_status={card['review_status']} → 게이트 차단 통지")
        return
    notion_state.update_card(card["page_id"], stage="publish_ready", status="queued")
    log(f"{card['content_id']} publish_ready → 발행 대기열")


def handle_revision_requested(card: dict):
    """approval + revision_requested → 사람 지시대로 초안 재작성 → 재승인 요청.

    지시는 '🛠 수정 지시' 섹션에서 읽는다. 지시가 없으면 어디에 적어야 하는지
    알려주고 대기한다 (조용한 방치 금지).
    """
    page_id = card["page_id"]
    instruction = notion_state.read_latest_section(page_id, "🛠 수정 지시").strip()
    if not instruction:
        if card["status"] != "needs_human":
            notion_state.update_card(page_id, status="needs_human")
            notion_state.notify(
                page_id,
                f"✏️ [{card['content_id']}] 수정 요청을 받았지만 지시문이 없습니다. "
                "'🛠 수정 지시' 섹션(토글)을 만들어 무엇을 어떻게 고칠지 적어주세요. "
                "다음 실행이 재작성합니다.",
            )
        return

    notion_state.update_card(page_id, status="running",
                             approval_status="not_requested")
    brief_text = notion_state.read_sections_by_prefix(page_id, "📝 브리프")[:6000]
    formats = [f.strip() for f in card["format"].split(",") if f.strip()]
    supported = [f for f in formats if f in ("thread", "newsletter")] or ["thread"]
    for fmt in supported:
        draft = notion_state.read_latest_section(page_id, f"✍️ 초안 ({fmt})")
        if not draft.strip():
            continue
        revised = llm.call_writing(
            prompts.WRITER.format(
                format=fmt, brief=brief_text, style_context="", hook_examples="",
                feedback_block=(
                    "[사용자 수정 지시 — 최우선으로 반영하라. 지시 밖의 내용은 "
                    "가능한 한 직전 초안을 유지하라]\n"
                    f"{instruction}\n\n[직전 초안]\n{draft}"
                ),
            ),
            system=prompts.get_system(),
            max_tokens=16000 if fmt == "newsletter" else 8000,
        )
        notion_state.append_section(page_id, f"✍️ 초안 ({fmt})", revised)
    notion_state.update_card(
        page_id, stage="approval", status="needs_human",
        approval_status="requested",
    )
    notion_state.notify(
        page_id,
        f"✏️ [{card['content_id']}] 수정 지시를 반영해 재작성했습니다. "
        "새 '✍️ 초안'을 확인하고 approval_status를 approved로 바꾸면 발행됩니다.",
    )
    log(f"{card['content_id']} 수정 지시 반영 → 재승인 대기 ⏸️")


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
    ("approval", None, "revision_requested", handle_revision_requested),
    ("approval", None, "approved", handle_final_approved),
    ("publish_ready", "queued", None, handle_publish),
]

# 중간 크래시(Actions 타임아웃 등)로 running에 멈춘 카드를 재큐하는 임계 시간
STUCK_RUNNING_MINUTES = int(os.getenv("DG_STUCK_RUNNING_MINUTES", "60"))
RETRY_MARK = "[자동재시도] "


def sweep_stuck_cards():
    """조용히 죽은 카드를 되살리거나 사람에게 알린다 (무개입 자동화의 안전망).

    1. status=failed: 1회 자동 재큐(RETRY_MARK로 표시). 재시도 후 또 실패하면
       그대로 두고 알림만 보낸다 (무한 재시도 방지).
    2. brief/draft가 running인 채 STUCK_RUNNING_MINUTES 초과: 실행 도중 크래시로
       고아가 된 것 → keyword_approval/approved로 되돌려 다음 루프가 재생성.
    """
    for card in notion_state.query_cards(status="failed", page_size=10):
        pid, cid = card["page_id"], card.get("content_id") or "?"
        # 재시도 여부는 idempotency_key의 RETRY_MARK 접두사로 표시한다
        if card["idempotency_key"].startswith(RETRY_MARK):
            continue  # 이미 한 번 재시도한 카드 — 사람 판단 대기
        retry_status = {"research": "running"}.get(card["stage"], "queued")
        notion_state.update_card(
            pid, status=retry_status,
            idempotency_key=RETRY_MARK + card["idempotency_key"],
        )
        notion_state.notify(
            pid, f"🔁 [{cid}] 실패한 카드를 자동 재시도합니다 "
                 f"(stage={card['stage']}). 또 실패하면 다시 알립니다.")
        log(f"{cid} failed → 자동 재시도 ({card['stage']}/{retry_status})")

    for stage in ("brief", "draft"):
        for card in notion_state.query_cards(stage=stage, status="running",
                                             page_size=10):
            if notion_state.age_minutes(card) < STUCK_RUNNING_MINUTES:
                continue
            notion_state.update_card(
                card["page_id"], stage="keyword_approval", status="queued",
                approval_status="approved",
            )
            log(f"{card.get('content_id')} {stage}/running "
                f"{STUCK_RUNNING_MINUTES}분 초과 고아 → 재생성 큐")


def run(only_stage: str | None = None):
    notion_state.require_backend()
    if not only_stage:
        try:
            sweep_stuck_cards()
        except Exception as e:
            log(f"고아 카드 청소 실패 (계속 진행): {e}")
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
                notion_state.update_card(
                    card["page_id"], status="failed",
                    last_error=f"{type(e).__name__}: {e}"[:1500],
                )
                log(f"{card.get('content_id') or card['page_id']} 실패: {e}")
                # 침묵 금지: 재시도까지 실패한 카드는 사람이 알아야 한다.
                # (첫 실패는 다음 실행의 sweep이 자동 재시도하므로 알리지 않는다)
                if card["idempotency_key"].startswith(RETRY_MARK):
                    try:
                        notion_state.notify(
                            card["page_id"],
                            f"🚨 [{card.get('content_id') or '?'}] 자동 재시도까지 "
                            f"실패했습니다 (stage={stage}). last_error를 확인해주세요: "
                            f"{type(e).__name__}: {str(e)[:200]}",
                        )
                    except Exception as ne:
                        log(f"실패 알림 발송 실패: {ne}")
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
