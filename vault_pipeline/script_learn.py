"""원고 수정 학습 루프 — 사람이 고친 원고(유튜브·릴스·블로그·스레드·뉴스레터)를 AI 원본과 비교해 배운다.

흐름
  1. 오케스트레이터가 원고를 만들 때 AI 원본을 `_system/ai_originals/원고/<파일명>` 에 남긴다
     (orchestrator.extra_formats.save_ai_original — youtube_script 도 같은 함수를 호출).
  2. 사람이 옵시디언에서 원고를 고치고 `05 리뷰/완료` 로 옮기거나(또는 frontmatter 상태를
     리뷰완료/발행완료 로 바꾸거나) `06 제작/64 발행완료` 에 두면 "확정본"으로 본다.
  3. 이 스크립트(orchestrator.yml 매 실행)가 확정본 ↔ AI 원본 diff 를 Claude 로 분석해
       · Honcho `{채널}-corrections` 세션에 저장 → 다음 원고의 작가 프롬프트에 자동 주입
         (orchestrator.agent_dialogue.get_style_context → style_learn.get_corrections_context)
       · 사람이 읽을 수 있게 `07 운영/62 셀프 피드백/원고 수정 학습.md` 에 누적 기록
     한 번 학습한 파일은 장부(`_system/logs/script_learn_ledger.json`)에 적어 다시 학습하지 않는다.
     (파일 내용이 다시 바뀌면 해시가 달라져 재학습한다)

실행: python3 -m vault_pipeline.script_learn [--dry-run] [--max N]
환경: DG_VAULT_ROOT, VAULT_SCRIPT_PATH(05 리뷰/대기 위치 → 형제 폴더 "완료" 사용), ANTHROPIC_API_KEY,
      HONCHO_API_KEY(없으면 볼트 기록만)
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vault_pipeline.vault_io import now_kst, parse_frontmatter, vault_root  # noqa: E402

SCRIPT_DIR_DEFAULT = "SNS 콘텐츠 제작 시스템/05 리뷰/대기"
DONE_DIRS_EXTRA = ["SNS 콘텐츠 제작 시스템/06 제작/64 발행완료"]
DONE_STATES = {"리뷰완료", "발행완료", "발행됨", "완료", "확정"}
LEARN_NOTE = "SNS 콘텐츠 제작 시스템/07 운영/62 셀프 피드백/원고 수정 학습.md"
LEDGER = "_system/logs/script_learn_ledger.json"
ORIGINALS = "_system/ai_originals/원고"

CHANNEL_BY_TYPE = {
    "youtube-script": "youtube",
    "reels-script": "reels",
    "blog-post": "blog",
    "thread": "thread",
    "threads": "thread",
    "newsletter": "newsletter",
}


def _channel_of(meta: dict, name: str) -> str:
    t = str(meta.get("type") or "").strip().lower()
    if t in CHANNEL_BY_TYPE:
        return CHANNEL_BY_TYPE[t]
    ch = str(meta.get("채널") or "").strip().lower()
    if ch in ("youtube", "reels", "blog", "thread", "newsletter"):
        return ch
    for key, val in (("YT롱폼", "youtube"), ("릴스", "reels"), ("블로그", "blog"), ("스레드", "thread"), ("뉴스레터", "newsletter")):
        if key in name:
            return val
    return "youtube"


def _candidates() -> list[Path]:
    root = vault_root()
    pending = root / os.getenv("VAULT_SCRIPT_PATH", SCRIPT_DIR_DEFAULT).strip("/")
    dirs = [pending.parent / "완료"] + [root / d for d in DONE_DIRS_EXTRA]
    out: list[Path] = []
    for d in dirs:
        if d.exists():
            out.extend(p for p in d.glob("*.md") if p.name != "README.md")
    # 대기 폴더에 있어도 상태가 확정이면 학습 대상
    if pending.exists():
        for p in pending.glob("*.md"):
            try:
                meta, _ = parse_frontmatter(p.read_text(encoding="utf-8", errors="ignore"))
            except Exception:
                continue
            st = str(meta.get("상태") or meta.get("검수상태") or "").strip()
            if st in DONE_STATES:
                out.append(p)
    return out


def _body(text: str) -> str:
    _, body = parse_frontmatter(text)
    return body.strip()


def compute_diff(original: str, edited: str) -> dict:
    a = original.splitlines()
    b = edited.splitlines()
    added = [l for l in difflib.ndiff(a, b) if l.startswith("+ ") and l[2:].strip()]
    removed = [l for l in difflib.ndiff(a, b) if l.startswith("- ") and l[2:].strip()]
    ratio = difflib.SequenceMatcher(None, original, edited).ratio()
    return {
        "added": [l[2:] for l in added],
        "removed": [l[2:] for l in removed],
        "total_changes": len(added) + len(removed),
        "length_change": len(edited) - len(original),
        "similarity": round(ratio, 3),
    }


def analyze(channel: str, original: str, edited: str, stats: dict) -> str:
    from orchestrator import llm

    prompt = f"""아래는 '{channel}' 채널용 원고의 AI 초안과, 사람이 최종 확정한 수정본입니다.
다음 원고를 쓸 때 반영할 수정 패턴을 뽑아주세요 (한국어, 총 300자 이내, 각 항목 1~2문장).

## AI 초안
{original[:6000]}

## 사람 확정본
{edited[:6000]}

## 변경 통계
- 추가 줄 {len(stats['added'])} · 삭제 줄 {len(stats['removed'])} · 길이 변화 {stats['length_change']:+d}자 · 유사도 {stats['similarity']}

항목
1. 삭제된 패턴 (AI 가 썼지만 사람이 지운 표현·구조 → 피할 것)
2. 추가된 패턴 (사람이 새로 넣은 표현·구조 → 따라할 것)
3. 톤/어미 변화
4. 구조 변화
5. 핵심 규칙 1~3개 (다음 원고에 바로 적용할 문장으로)"""
    return llm.call(prompt, max_tokens=700).strip()


def store_honcho(channel: str, topic: str, analysis: str, stats: dict) -> bool:
    try:
        from memory_manager import get_honcho_client

        client = get_honcho_client()
        if not client:
            return False
        user = client.peer("content-creator")
        session = client.session(f"{channel}-corrections")
        msg = (
            f"[원고 수정학습 {now_kst().strftime('%Y-%m-%d %H:%M')}] 주제: {topic}\n"
            f"변경량: {stats['total_changes']}줄, 길이변화: {stats['length_change']:+d}자, 유사도 {stats['similarity']}\n"
            f"분석:\n{analysis}"
        )
        session.add_messages([user.message(msg)])
        return True
    except Exception as e:  # pragma: no cover
        print(f"  Honcho 저장 실패(무시): {e}")
        return False


def append_note(channel: str, name: str, topic: str, analysis: str, stats: dict, honcho_ok: bool, dry_run: bool) -> None:
    path = vault_root() / LEARN_NOTE
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() and not dry_run:
        path.write_text(
            "---\ntype: learning-log\n설명: 사람이 고친 원고와 AI 초안의 차이에서 배운 규칙. 오케스트레이터가 자동 누적하며 다음 원고 프롬프트에 반영된다.\n---\n\n# 원고 수정 학습\n\n",
            encoding="utf-8",
        )
    block = (
        f"## {now_kst().strftime('%Y-%m-%d %H:%M')} · {channel} · {name}\n"
        f"- 주제: {topic}\n"
        f"- 변경: +{len(stats['added'])}줄 / -{len(stats['removed'])}줄 · 길이 {stats['length_change']:+d}자 · 유사도 {stats['similarity']}"
        f" · Honcho {'저장' if honcho_ok else '미저장'}\n\n{analysis}\n\n"
    )
    if dry_run:
        print(block)
        return
    with path.open("a", encoding="utf-8") as f:
        f.write(block)


def _ledger_path() -> Path:
    return vault_root() / LEDGER


def load_ledger() -> dict:
    p = _ledger_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_ledger(ledger: dict) -> None:
    p = _ledger_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(ledger, ensure_ascii=False, indent=1), encoding="utf-8")


def run(dry_run: bool = False, max_items: int = 5) -> int:
    root = vault_root()
    originals = root / ORIGINALS
    ledger = load_ledger()
    learned = ledger.setdefault("learned", {})
    done = 0
    for path in _candidates():
        if done >= max_items:
            break
        orig = originals / path.name
        if not orig.exists():
            # 재초안(-2.md 등) 이름도 시도
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
        if learned.get(path.name, {}).get("hash") == digest:
            continue
        original_body = _body(orig.read_text(encoding="utf-8", errors="ignore"))
        edited_body = _body(text)
        if not original_body or not edited_body:
            continue
        stats = compute_diff(original_body, edited_body)
        if stats["total_changes"] == 0 or stats["similarity"] > 0.985:
            learned[path.name] = {"hash": digest, "at": now_kst().isoformat(), "skipped": "no-change"}
            continue
        meta, _ = parse_frontmatter(text)
        channel = _channel_of(meta, path.name)
        topic = str(meta.get("카테고리") or meta.get("topic") or path.stem)
        print(f"학습: {path.name} ({channel}) 변경 {stats['total_changes']}줄, 유사도 {stats['similarity']}")
        try:
            analysis = analyze(channel, original_body, edited_body, stats)
        except Exception as e:
            print(f"  분석 실패(다음 실행에 재시도): {e}")
            continue
        honcho_ok = False if dry_run else store_honcho(channel, topic, analysis, stats)
        append_note(channel, path.name, topic, analysis, stats, honcho_ok, dry_run)
        learned[path.name] = {"hash": digest, "at": now_kst().isoformat(), "channel": channel, "honcho": honcho_ok}
        done += 1
    if not dry_run:
        save_ledger(ledger)
    print(f"원고 수정 학습: {done}건 처리")
    return done


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max", type=int, default=5)
    args = ap.parse_args()
    run(dry_run=args.dry_run, max_items=args.max)


if __name__ == "__main__":
    main()
