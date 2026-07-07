"""발행 직전 미리보기(드라이런) - 실제 발행 없이 결과물을 눈으로 확인한다.

파이프라인과 동일한 브리프→토론 초안 생성을 거친 뒤, 실제 발행에 쓰이는
publish.split_posts(스레드 체인)와 stibee.markdown_to_html(뉴스레터 HTML)로 렌더링해
파일로 저장한다. 발행 API를 전혀 건드리지 않으므로 시크릿 없이도 돌아간다.

실행:
  python3 -m orchestrator.preview --topic "주제" --audience "초등 저학년 학부모" \
      --formats thread,newsletter --out /path/to/out
  # --topic 생략 시 TOPIC_IDEAS로 오늘의 주제를 자동 발제
"""
import argparse
import html as _html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator import agent_dialogue, llm, prompts, publish, stibee


def log(msg: str):
    print(f"[preview] {msg}", flush=True)


def pick_topic(audience: str) -> str:
    ideas = llm.call_json(
        prompts.TOPIC_IDEAS.format(count=1, audience=audience, existing="(없음)"),
        system=prompts.get_system(),
    )
    topics = ideas.get("topics", [])
    return (topics[0].get("topic") if topics else "").strip() or "초등 아이 훈육 고민"


def make_brief(topic: str, audience: str) -> dict:
    return llm.call_json(
        prompts.BRIEF.format(keyword=topic, topic=topic, audience=audience, context=""),
        system=prompts.get_system(),
    )


def render_thread(draft: str) -> str:
    posts = publish.split_posts(draft)
    lines = [f"# 스레드 발행 미리보기 — 총 {len(posts)}개 글\n"]
    for i, p in enumerate(posts, 1):
        over = "  ⚠️500자 초과" if len(p) > publish.POST_CHAR_LIMIT else ""
        lines.append(f"\n{'='*48}\n[{i}/{len(posts)}]  ({len(p)}자{over})\n{'='*48}\n{p}")
    return "\n".join(lines)


def render_newsletter_html(draft: str) -> tuple[str, str]:
    subject = stibee.extract_subject(draft)
    body_html = stibee.markdown_to_html(draft)
    page = (
        "<!DOCTYPE html><html lang='ko'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{_html.escape(subject)}</title>"
        "<style>body{background:#f4f4f5;margin:0;padding:24px;"
        "font-family:'Apple SD Gothic Neo','Malgun Gothic','Noto Sans KR',sans-serif}"
        ".mail{background:#fff;border-radius:12px;padding:32px 24px;"
        "box-shadow:0 2px 12px rgba(0,0,0,.06)}"
        ".subject{font-size:20px;font-weight:700;color:#111;border-bottom:2px solid #eee;"
        "padding-bottom:14px;margin-bottom:20px}</style></head>"
        f"<body><div class='mail'><div class='subject'>📧 제목: {_html.escape(subject)}</div>"
        f"{body_html}</div></body></html>"
    )
    return subject, page


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", default="")
    ap.add_argument("--audience", default="초등 저학년 학부모")
    ap.add_argument("--formats", default="thread,newsletter")
    ap.add_argument("--out", default="preview_out")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    formats = [f.strip() for f in args.formats.split(",") if f.strip()]

    topic = args.topic.strip() or pick_topic(args.audience)
    log(f"주제: {topic} / 대상: {args.audience}")

    brief = make_brief(topic, args.audience)
    (out / "00_brief.json").write_text(
        json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log(f"브리프 완성: {brief.get('brief_title', '')}")

    summary = {"topic": topic, "audience": args.audience, "brief_title": brief.get("brief_title", ""), "formats": {}}
    for fmt in formats:
        log(f"[{fmt}] 초안 생성 중 (작가↔비평가↔검수)...")
        result = agent_dialogue.run_draft_dialogue(brief, fmt)
        draft, review = result["draft"], result["review"]
        (out / f"{fmt}_draft.md").write_text(draft, encoding="utf-8")
        review_line = f"{review.get('review_status')} / risk={review.get('risk_level')}"

        if fmt == "thread":
            (out / "thread_preview.txt").write_text(render_thread(draft), encoding="utf-8")
            n = len(publish.split_posts(draft))
            summary["formats"]["thread"] = {"review": review_line, "posts": n}
            log(f"[thread] 검수={review_line}, 글 {n}개 → thread_preview.txt")
        elif fmt == "newsletter":
            subject, page = render_newsletter_html(draft)
            (out / "newsletter_preview.html").write_text(page, encoding="utf-8")
            summary["formats"]["newsletter"] = {"review": review_line, "subject": subject, "chars": len(draft)}
            log(f"[newsletter] 검수={review_line}, {len(draft)}자 → newsletter_preview.html")

    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log(f"완료 → {out.resolve()}")


if __name__ == "__main__":
    main()
