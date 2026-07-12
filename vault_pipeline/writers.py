"""triage 결과를 볼트 노트로 기록 — 3종 시스템의 쓰기 계층

볼트 헌법 준수 사항:
- 초록 사례만 자동 입고, 노랑은 _노랑대기 + 결재함, 빨강은 로그 한 줄만
- 발화 발췌 노트는 author: 이한결(구술) + verbatim: true
- AI 구조화 노트(키워드)는 파일명 K_ai + author: AI
- 기존 파일은 덮지 않는다 (vault_io.write_note가 보장)
"""
from vault_pipeline import prompts
from vault_pipeline.plaud_client import Recording
from vault_pipeline.vault_io import (
    append_review_queue, log_line, parse_frontmatter, today, vault_root,
    write_note,
)

from orchestrator import llm


def load_style_samples(rel_dir: str, limit: int = 3,
                       chars_per_sample: int = 1800) -> str:
    """raw/블로그글·페이스북글의 본인 글을 문체 벤치마크로 읽는다 (최신 우선)."""
    directory = vault_root() / rel_dir
    if not directory.exists():
        return ""
    files = [p for p in directory.glob("*.md") if p.stem.lower() != "readme"]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    samples = []
    for p in files[:limit]:
        _, body = parse_frontmatter(p.read_text(encoding="utf-8", errors="ignore"))
        body = body.strip()
        if body:
            samples.append(body[:chars_per_sample])
    if not samples:
        return ""
    joined = "\n\n---\n\n".join(samples)
    return (
        "\n\n[문체 벤치마크 — 아래는 이한결이 직접 쓴 글이다. 이 목소리·리듬·"
        "어휘를 따르라. 내용을 베끼지는 말 것]\n\n" + joined
    )


def load_style_lessons(channel: str, max_chars: int = 2000) -> str:
    """_system/style_lessons.md에서 해당 채널의 학습된 편집 규칙을 읽는다.

    사용자가 초안을 고쳐 발행할 때마다 feedback.py가 규칙을 누적하므로,
    글을 쓸수록 초안이 사용자 문체에 수렴한다 (시스템의 핵심 요구 1번).
    """
    path = vault_root() / "_system" / "style_lessons.md"
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="ignore")
    # "## 채널명" 섹션만 추출
    import re
    m = re.search(rf"^## {re.escape(channel)}\n(.*?)(?=^## |\Z)", text,
                  re.MULTILINE | re.DOTALL)
    if not m:
        return ""
    section = m.group(1).strip()
    if not section:
        return ""
    if len(section) > max_chars:      # 최근 교훈 우선 (뒤쪽이 최신)
        section = section[-max_chars:]
    return (
        "\n\n[문체 학습 — 이 채널에서 사용자가 초안을 직접 고친 패턴에서 배운 "
        "규칙이다. 반드시 전부 적용하라]\n" + section
    )


def save_ai_original(draft_path, body: str, dry_run: bool = False) -> None:
    """초안의 AI 원본 사본을 저장한다 — 사용자 수정본과의 diff 학습 재료.

    경로: _system/ai_originals/<초안 폴더명>/<초안 파일명>
    """
    if dry_run:
        return
    dest = (vault_root() / "_system" / "ai_originals"
            / draft_path.parent.name / draft_path.name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(body.rstrip() + "\n", encoding="utf-8")


def _meta_base(rec: Recording) -> dict:
    return {
        "출처": f"plaud:{rec.id}",
        "녹음": rec.name,
        "recorded": rec.recorded,
        "created": today(),
    }


# -------------------------------------------------------------- 1) 사례은행

def write_cases(rec: Recording, cases: list[dict], dry_run: bool) -> dict:
    """반환: {"artifacts": [...], "green": n, "yellow": n} (빨강은 로그만)."""
    artifacts: list[str] = []
    green = yellow = 0
    queue_lines: list[str] = []
    red_reasons: list[str] = []
    for case in cases:
        light = str(case.get("신호등", "")).strip()
        title = str(case.get("제목", "")).strip()
        if light == "빨강":
            red_reasons.append(str(case.get("판정사유", "사유 미기재")))
            continue
        if not title or not str(case.get("발화_원문", "")).strip():
            continue
        meta = {
            "title": title,
            "author": "이한결(구술)",
            "source_type": "experience",
            "verbatim": True,
            **_meta_base(rec),
            "신호등": light,
        }
        body = (
            f"> \"{case['발화_원문'].strip()}\"\n\n"
            f"**맥락**: {str(case.get('맥락', '')).strip()}\n\n"
            f"**판정**: {light} — {str(case.get('판정사유', '')).strip()}\n"
        )
        if light == "초록":
            green += 1
            path = write_note("제텔카스텐/6. 사례은행", f"사례 - {title}", meta, body,
                              dry_run=dry_run)
        else:  # 노랑 (그 외 값도 안전하게 노랑으로)
            yellow += 1
            meta["status"] = "결재대기"
            path = write_note("제텔카스텐/6. 사례은행/_노랑대기", f"사례 - {title}",
                              meta, body, dry_run=dry_run)
            queue_lines.append(
                f"- [ ] 노랑 사례 결재: [[{path.stem}]] — {case.get('판정사유', '')}")
        artifacts.append(path.name)
    if queue_lines:
        append_review_queue(queue_lines, dry_run=dry_run)
    if red_reasons:
        # 빨강은 내용을 어디에도 저장하지 않는다 — 건수와 사유만 로그
        log_line(f"빨강 차단 {len(red_reasons)}건 ({rec.id}): "
                 + " / ".join(red_reasons), dry_run=dry_run)
    return {"artifacts": artifacts, "green": green, "yellow": yellow}


# -------------------------------------------------- 2) 제텔카스텐 1→2→3단계

def write_memos(rec: Recording, memos: list[dict], dry_run: bool) -> dict[str, str]:
    """1단계 메모 생성. {메모 제목: 파일 stem} 반환 (키워드 링크용)."""
    created: dict[str, str] = {}
    for memo in memos:
        title = str(memo.get("제목", "")).strip()
        excerpt = str(memo.get("발췌", "")).strip()
        if not title or not excerpt:
            continue
        meta = {
            "title": title,
            "author": "이한결(구술)",
            "source_type": "own_script",
            "verbatim": True,
            **_meta_base(rec),
            "tags": [str(memo.get("주제", "")).strip()] if memo.get("주제") else [],
        }
        body = f"> \"{excerpt}\"\n"
        path = write_note("제텔카스텐/1. 메모", title, meta, body, dry_run=dry_run)
        created[title] = path.stem
    return created


def write_keywords(rec: Recording, keywords: list[dict],
                   memo_stems: dict[str, str], dry_run: bool) -> list[str]:
    """2단계 키워드 — AI 구조화 산출물이므로 K_ai 딱지 + author: AI."""
    artifacts = []
    for kw in keywords:
        word = str(kw.get("키워드", "")).strip()
        if not word:
            continue
        links = [f"[[{memo_stems[t]}]]" for t in kw.get("관련_메모", [])
                 if t in memo_stems]
        meta = {
            "title": word,
            "author": "AI",
            **_meta_base(rec),
        }
        body = (
            f"**What**: {str(kw.get('what', '')).strip()}\n\n"
            f"**Why**: {str(kw.get('why', '')).strip()}\n\n"
            f"**How**: {str(kw.get('how', '')).strip()}\n\n"
            f"**관련 메모**: {' '.join(links) if links else '(없음)'}\n\n"
            "> `_ai` 노트 — 읽고 자기 언어로 고친 뒤 `K - `로 승격하세요. "
            "승격 전에는 4·5단계에 인용 금지.\n"
        )
        path = write_note("제텔카스텐/2. 키워드", f"K_ai - {word}", meta, body,
                          dry_run=dry_run)
        artifacts.append(path.name)
    return artifacts


def write_opinions(rec: Recording, opinions: list[dict], dry_run: bool) -> list[str]:
    """3단계 의견 — 화자가 표명한 의견만. AI 창작분은 triage 프롬프트가 차단."""
    artifacts = []
    for op in opinions:
        title = str(op.get("제목", "")).strip()
        stance = str(op.get("의견", "")).strip()
        if not title or not stance:
            continue
        meta = {
            "title": title,
            "author": "이한결(구술)",
            "source_type": "own_script",
            **_meta_base(rec),
        }
        body = (
            f"{stance}\n\n"
            f"**근거 발화**:\n> \"{str(op.get('근거_발화', '')).strip()}\"\n"
        )
        path = write_note("제텔카스텐/3. 의견", f"O - {title}", meta, body,
                          dry_run=dry_run)
        artifacts.append(path.name)
    return artifacts


# ---------------------------- 3) 교육운동 활동기록 + 교사그룹 대상 블로그·페북 초안

MOVEMENT_GROUPS = ("꿈들", "새넷", "전교조")


def write_activity_record(rec: Recording, seed: dict, dry_run: bool) -> list[str]:
    """꿈들·새넷·전교조 활동 녹음이면 프로젝트/교육운동/활동기록에 요약을 남긴다."""
    group = str(seed.get("활동", "")).strip()
    summary = str(seed.get("활동_요약", "")).strip()
    if group not in MOVEMENT_GROUPS or not summary:
        return []
    meta = {
        "title": f"{group} 활동 — {rec.name}",
        "author": "AI",
        "프로젝트": "교육운동",
        "활동": group,
        **_meta_base(rec),
    }
    body = summary + "\n\n> AI 요약 — 사실관계는 녹음 전사가 원본이다.\n"
    path = write_note("프로젝트/교육운동/활동기록",
                      f"{rec.recorded} {group} - {rec.name}", meta, body,
                      dry_run=dry_run)
    return [path.name]


def write_teacher_posts(rec: Recording, seed: dict, dry_run: bool) -> list[str]:
    """교사그룹 대상 글감이 적합 판정이면 블로그+페이스북 초안 생성. 발행은 사람.

    타겟 독자는 교사그룹 — 드림그로우(학부모)와 다른 채널이므로 frontmatter에 명시한다.
    """
    if not seed or not seed.get("적합"):
        return []
    topic = str(seed.get("주제", "")).strip()
    core = str(seed.get("핵심", "")).strip()
    group = str(seed.get("활동", "")).strip() or "일반"
    quotes = "\n".join(f"- \"{q}\"" for q in seed.get("근거_발화", []) if q)
    if not topic or not quotes:
        return []
    artifacts = []

    blog = llm.call_writing(
        prompts.TEACHER_BLOG.format(topic=topic, core=core, quotes=quotes),
        system=prompts.TEACHER_VOICE + load_style_samples("raw/블로그글")
               + load_style_lessons("블로그(교사)"),
    ).strip()
    blog_title = topic
    if blog.startswith("# "):
        blog_title, _, blog_rest = blog.partition("\n")
        blog_title = blog_title[2:].strip() or topic
        blog = blog_rest.strip()
    meta = {
        "title": blog_title,
        "채널": "블로그(교사)",
        "상태": "리뷰대기",          # 발행완료는 사람만 바꾼다
        "타겟": "교사그룹",          # 학부모(드림그로우) 채널과 절대 혼용 금지
        "프로젝트": "교육운동",
        "활동": group,
        **_meta_base(rec),
    }
    path = write_note("프로젝트/교육운동/블로그_초안", f"{today()} {blog_title}", meta,
                      f"# {blog_title}\n\n{blog}", dry_run=dry_run)
    save_ai_original(path, f"# {blog_title}\n\n{blog}", dry_run=dry_run)
    artifacts.append(f"프로젝트/교육운동/블로그_초안/{path.name}")

    fb = llm.call_writing(
        prompts.TEACHER_FACEBOOK.format(topic=topic, core=core, quotes=quotes),
        system=prompts.TEACHER_VOICE + load_style_samples("raw/페이스북글")
               + load_style_lessons("페이스북(교사)"),
    ).strip()
    meta_fb = dict(meta, 채널="페이스북(교사)", title=topic)
    path_fb = write_note("프로젝트/교육운동/페이스북_초안", f"{today()} {topic}",
                         meta_fb, fb, dry_run=dry_run)
    save_ai_original(path_fb, fb, dry_run=dry_run)
    artifacts.append(f"프로젝트/교육운동/페이스북_초안/{path_fb.name}")
    return artifacts
