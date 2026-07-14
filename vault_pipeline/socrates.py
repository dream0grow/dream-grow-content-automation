"""socrates 새벽 질문 잡 — 2→3단계(의견) 병목 전담 에이전트의 자동 실행체

매일 새벽: 제텔카스텐에서 재료 하나를 골라 전제를 흔드는 질문을 만들어
_system/dialogues/YYYY-MM-DD.md 에 남기고 텔레그램으로 보낸다.
사용자가 그 파일(또는 답장)에 몇 줄 적으면 — 그것이 그날의 의견(O노트) 원석이 된다.

어제 대화에 사용자의 답이 달려 있으면 후속 질문으로 잇는다 (대화 누적 구조).
직관 줄에는 개입하지 않는다.

실행: python3 -m vault_pipeline.socrates  (vault-agents.yml, KST 05:08)
"""
import re
from datetime import timedelta
from pathlib import Path

from vault_pipeline import telegram_notify
from vault_pipeline.vault_io import (
    log_line, now_kst, parse_frontmatter, today, vault_root,
)

from orchestrator import llm

SYSTEM = """당신은 소크라테스입니다. 이한결(초등교사 22년, 교육운동가이자 사업가)의
생각을 깊게 만드는 것이 임무입니다. 답을 주지 말고 질문만 하십시오.
질문은 짧고 구체적으로 — 아침에 커피 마시며 몇 줄로 답할 수 있는 크기로.

가장 중요한 규칙: 질문은 반드시 노트가 실제로 다루는 주제와 맥락 안에서 나와야 합니다.
비즈니스 노트면 그 비즈니스의 논리를 더 깊게 파는 질문을, 교육 노트면 교육을 더 깊게
고민하게 하는 질문을, 방법론 노트면 그 방법론 자체를 검증하는 질문을 하십시오.
노트의 주제를 다른 영역(교실, 학부모, 드림그로우 콘텐츠 등)에 적용해 보라는 식으로
맥락을 갈아끼우는 질문은 금지합니다 — 창의적 연결이 아니라 논리적 심화가 목적입니다."""

PROMPT = """아래는 이한결의 제텔카스텐 노트입니다.

[재료: {title}]
{body}

{followup}

먼저 이 노트의 주제 영역(비즈니스/교육/방법론/기타)과 핵심 주장을 파악하세요.
그다음 **그 주제 안에서**, 노트의 용어를 그대로 써서 논리를 더 깊게 만드는
오늘의 질문 3개를 만드세요:
1. 전제 검증: 이 주장이 성립하려면 무엇이 참이어야 하는가? 그 전제는 정말 참인가
2. 반례와 경계: 이 논리가 깨지는 경우는 언제인가? 어디까지 적용되고 어디서부터 안 되는가
3. 재정의 또는 다음 단계: 이것은 사실 무엇에 관한 문제인가, 혹은 이 주장을 끝까지 밀면 어떤 결론에 닿는가

세 질문 모두 노트가 다루는 주제를 벗어나면 안 됩니다 (다른 영역으로의 번역·적용 금지).

JSON만 출력: {{"질문": ["질문1", "질문2", "질문3"]}}"""


def _dialogues_dir() -> Path:
    return vault_root() / "_system" / "dialogues"


def _used_materials() -> set[str]:
    """이미 질문 재료로 쓴 노트 제목들 (dialogue frontmatter 재료 필드)."""
    used = set()
    d = _dialogues_dir()
    if not d.exists():
        return used
    for p in d.glob("*.md"):
        meta, _ = parse_frontmatter(p.read_text(encoding="utf-8", errors="ignore"))
        if meta.get("재료"):
            used.add(str(meta["재료"]))
    return used


def pick_material() -> tuple[str, str] | None:
    """(제목, 본문) — 아직 질문하지 않은 최신 노트. 키워드 우선, 없으면 메모."""
    used = _used_materials()
    for rel in ("제텔카스텐/2. 키워드", "제텔카스텐/3. 의견", "제텔카스텐/1. 메모"):
        directory = vault_root() / rel
        if not directory.exists():
            continue
        files = [p for p in directory.glob("*.md") if p.name != ".gitkeep"]
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for p in files:
            if p.stem in used:
                continue
            _, body = parse_frontmatter(
                p.read_text(encoding="utf-8", errors="ignore"))
            if body.strip():
                return p.stem, body.strip()[:4000]
    return None


def yesterday_followup() -> str:
    """어제 대화에 사용자 답이 있으면 후속 질문 재료로 넘긴다."""
    y = (now_kst() - timedelta(days=1)).strftime("%Y-%m-%d")
    p = _dialogues_dir() / f"{y}.md"
    if not p.exists():
        return ""
    text = p.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"## 나의 답\n(.*)", text, re.DOTALL)
    answer = m.group(1).strip() if m else ""
    if not answer or answer.startswith("(여기에"):
        return ""
    return ("[어제의 대화 — 사용자가 이렇게 답했다. 이 답을 더 깊게 파는 "
            f"후속 질문을 우선하라]\n{answer[:2000]}\n")


def main() -> None:
    date = today()
    out = _dialogues_dir() / f"{date}.md"
    if out.exists():
        log_line("socrates: 오늘 대화 노트가 이미 있음 — 생략")
        return
    material = pick_material()
    if not material:
        log_line("socrates: 질문할 재료가 없음 (제텔카스텐이 비어 있음)")
        return
    title, body = material
    result = llm.call_json(
        PROMPT.format(title=title, body=body, followup=yesterday_followup()),
        system=SYSTEM, max_tokens=1500,
    )
    questions = [str(q).strip() for q in (result.get("질문") or []) if str(q).strip()]
    if not questions:
        log_line("socrates: 질문 생성 실패")
        return

    out.parent.mkdir(parents=True, exist_ok=True)
    q_lines = "\n".join(f"{i}. {q}" for i, q in enumerate(questions, 1))
    out.write_text(
        f"---\ndate: {date}\n재료: {title}\nauthor: AI\n---\n\n"
        f"# 오늘의 질문 — [[{title}]]\n\n{q_lines}\n\n"
        "## 직관 (논리로 답하기 전, 판단 없이 한 줄)\n\n(여기에)\n\n"
        "## 나의 답\n\n(여기에 몇 줄 — 이 답이 3단계 의견의 원석이 됩니다)\n",
        encoding="utf-8")
    log_line(f"socrates: 질문 3개 생성 ← {title}")
    telegram_notify.send(
        f"❓ 오늘의 질문 — {title}\n\n{q_lines}\n\n"
        f"옵시디언 _system/dialogues/{date}.md 에 직관 한 줄 + 답을 적어주세요.")


if __name__ == "__main__":
    main()
