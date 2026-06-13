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
    agent_dialogue, llm, manus_research, naver_keywords, notion_state, prompts,
)
from orchestrator.config import MAX_CARDS_PER_RUN, require_notion


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
    research = notion_state.read_sections(card["page_id"])
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
    notion_state.update_card(
        card["page_id"], stage="keyword_approval", status="needs_human",
        approval_status="requested",
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
    context = notion_state.read_sections(page_id)
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

        # 자동 글 평가 - 사람 검수자가 승인 판단에 참고
        try:
            score = llm.call_json(
                prompts.QUALITY_SCORE.format(format=fmt, draft=result["draft"]),
                system=prompts.get_system(),
            )
            notion_state.append_formatted_section(
                page_id,
                f"📊 글 평가 ({fmt}) - 총 {score.get('total', '?')}/50점",
                _fmt_score(score),
            )
        except Exception as e:
            log(f"{card['content_id']} 글 평가 실패 ({fmt}): {e}")

    notion_state.append_section(
        page_id, "⏸️ 발행 승인 요청",
        "확인 순서: 📊 글 평가 점수 → ✅ 검수 결과 → ✍️ 초안 본문.\n"
        "초안을 직접 수정해도 됩니다 ('✍️ 초안' 토글 안에서만, AI 원본은 그대로 두세요). "
        "수정분은 발행 시 자동으로 문체 학습에 반영됩니다.\n"
        "approval_status를 approved로 바꾸면 thread는 Threads에 자동 발행되고, "
        "newsletter는 Maily 붙여넣기용 최종본이 안내됩니다. "
        "수정 요청은 approval_status=revision_requested + 코멘트.",
    )
    notion_state.update_card(
        page_id, stage="approval", status="needs_human",
        review_status=worst_review,
        approval_status="requested",
    )
    log(f"{card['content_id']} 초안 {len(supported)}종 + 검수/평가 완료 → 발행 승인 대기 ⏸️")


def handle_final_approved(card: dict):
    """approval + approved + 검수 통과 → publish_ready (같은 실행에서 발행까지 이어짐)."""
    if card["review_status"] != "approved":
        log(f"{card['content_id']} review_status={card['review_status']} → 게이트 차단")
        return
    notion_state.update_card(card["page_id"], stage="publish_ready", status="queued")
    log(f"{card['content_id']} publish_ready → 발행 대기열")


def handle_publish(card: dict):
    """publish_ready/queued → Threads 자동 발행 (로드맵 2단계)."""
    from orchestrator import publish
    publish.handle_publish(card)
    log(f"{card['content_id']} 발행 처리 완료")


# ---------- 디스패처 ----------

DISPATCH = [
    # (stage, status, approval_status, handler)
    ("intake", "queued", None, handle_intake),
    ("research", "running", None, handle_research),
    ("keyword", "queued", None, handle_keyword),
    ("keyword_approval", None, "approved", handle_keyword_approved),
    ("approval", None, "approved", handle_final_approved),
    ("publish_ready", "queued", None, handle_publish),
]


def run(only_stage: str | None = None):
    require_notion()
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
    log(f"완료: {processed}개 카드 처리")


if __name__ == "__main__":
    stage_arg = None
    if "--stage" in sys.argv:
        stage_arg = sys.argv[sys.argv.index("--stage") + 1]
    run(stage_arg)
