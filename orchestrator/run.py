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
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator import agent_dialogue, llm, manus_research, notion_state, prompts
from orchestrator.config import MAX_CARDS_PER_RUN, require_notion


def log(msg: str):
    print(f"[orchestrator] {msg}", flush=True)


def _fmt_json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


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


def handle_research(card: dict):
    """research/running → Manus 완료 폴링 → 키워드 단계로."""
    task_ids = [t for t in card["manus_task_ids"].split(",") if t.strip()]
    if not task_ids:
        return
    all_done, results = manus_research.poll_results(task_ids)
    if not all_done:
        log(f"{card['content_id']} 리서치 진행 중 ({len(results)}/{len(task_ids)})")
        return
    _save_research(card["page_id"], results)
    notion_state.update_card(card["page_id"], stage="keyword", status="queued")
    log(f"{card['content_id']} 리서치 완료 → keyword")


def _save_research(page_id: str, results: list[dict]):
    for r in results:
        notion_state.append_section(
            page_id, f"🔍 리서치: {r.get('research_focus', '')[:40]}", _fmt_json(r),
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
    table = "\n".join(
        f"{k.get('keyword_id')}. {k.get('keyword')} (총 {k.get('total_score')}점) "
        f"- {k.get('core_message', '')}"
        for k in keywords
    )
    notion_state.append_section(
        card["page_id"], "🏷️ 키워드 후보 (승인 필요)",
        f"{table}\n\n승인 방법: approved_keyword 속성에 선택한 키워드를 입력하고 "
        f"approval_status를 approved로 변경하세요.\n\n상세:\n{_fmt_json(keywords)}",
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
    notion_state.append_section(page_id, "📝 브리프", _fmt_json(brief))

    fmt = (card["format"].split(",")[0] if card["format"] else "thread").strip()
    notion_state.update_card(page_id, stage="draft", status="running")
    result = agent_dialogue.run_draft_dialogue(
        brief, fmt, style_context=agent_dialogue.get_style_context(fmt),
    )
    notion_state.append_section(
        page_id, f"💬 에이전트 토론 ({result['rounds']}라운드)", result["transcript"],
    )
    notion_state.append_section(page_id, f"✍️ 초안 ({fmt})", result["draft"])

    review = result["review"]
    notion_state.append_section(page_id, "✅ 교육윤리 검수", _fmt_json(review))
    notion_state.update_card(
        page_id, stage="approval", status="needs_human",
        review_status=review.get("review_status", "revise"),
        approval_status="requested",
    )
    log(f"{card['content_id']} 초안 + 검수 완료 → 발행 승인 대기 ⏸️")


def handle_final_approved(card: dict):
    """approval + approved + 검수 통과 → publish_ready."""
    if card["review_status"] != "approved":
        log(f"{card['content_id']} review_status={card['review_status']} → 게이트 차단")
        return
    notion_state.update_card(card["page_id"], stage="publish_ready", status="done")
    log(f"{card['content_id']} publish_ready (발행은 기존 파이프라인 담당)")


# ---------- 디스패처 ----------

DISPATCH = [
    # (stage, status, approval_status, handler)
    ("intake", "queued", None, handle_intake),
    ("research", "running", None, handle_research),
    ("keyword", "queued", None, handle_keyword),
    ("keyword_approval", None, "approved", handle_keyword_approved),
    ("approval", None, "approved", handle_final_approved),
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
