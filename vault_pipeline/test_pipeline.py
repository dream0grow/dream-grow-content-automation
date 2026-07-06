"""플라우드 → 볼트 파이프라인 단위 테스트 (LLM은 mock, API 키 불필요)

실행: python3 -m pytest vault_pipeline/test_pipeline.py -v
"""
import json

import pytest

from orchestrator import llm
from vault_pipeline import run as pipeline_run
from vault_pipeline import vault_io
from vault_pipeline.plaud_client import fetch_inbox
from vault_pipeline.vault_io import safe_filename


TRIAGE_FIXTURE = {
    "요약": "수학 시간 관찰과 평가 제도에 대한 생각.",
    "사례": [
        {"제목": "틀리는 게 좋다고 말한 아이", "신호등": "초록",
         "발화_원문": "선생님, 저는 틀리는 게 좋아요. 다시 할 수 있으니까.",
         "맥락": "3학년 수학 시간, 오답 공유 활동 중.",
         "판정사유": "배움이 드러나고 개인정보 없음"},
        {"제목": "친구 다툼 이후 화해 장면", "신호등": "노랑",
         "발화_원문": "ㅇ이가 먼저 미안하다고 했어요.",
         "맥락": "쉬는 시간 다툼 뒤 중재.",
         "판정사유": "제3의 아이 등장 — 결재 필요"},
        {"제목": "", "신호등": "빨강", "발화_원문": "", "맥락": "",
         "판정사유": "가정사 관련 민감 발화"},
    ],
    "메모": [
        {"제목": "오답 공유가 수학 불안을 줄인다",
         "발췌": "오답을 같이 보는 순간 아이들 표정이 풀린다.", "주제": "수학교육"},
    ],
    "의견": [
        {"제목": "평가는 서열이 아니라 피드백이어야 한다",
         "의견": "평가의 목적은 줄 세우기가 아니라 다음 배움을 안내하는 것이다.",
         "근거_발화": "점수 말고 뭘 배웠는지 물어봐야 한다고 생각해요."},
    ],
    "키워드": [
        {"키워드": "오답 친화 교실", "what": "오답을 배움의 재료로 쓰는 교실 문화",
         "why": "수학 불안 감소", "how": "오답 공유 루틴",
         "관련_메모": ["오답 공유가 수학 불안을 줄인다"]},
    ],
    "교사_글감": {
        "적합": True, "주제": "오답이 환영받는 교실 만들기",
        "핵심": "평가를 피드백으로 되돌리자",
        "활동": "새넷",
        "활동_요약": "새넷 수업 나눔 모임에서 오답 공유 활동 사례를 발표하고 "
                   "다음 모임에서 평가 피드백 사례를 모으기로 했다.",
        "근거_발화": ["오답을 같이 보는 순간 아이들 표정이 풀린다."],
    },
}

TRANSCRIPT = (
    "[00:01 - 00:20] 이한결: 오늘 3학년 수학 시간에 오답 공유 활동을 했다. "
    "오답을 같이 보는 순간 아이들 표정이 풀린다. 한 아이가 말했다. "
    "선생님, 저는 틀리는 게 좋아요. 다시 할 수 있으니까. "
    "점수 말고 뭘 배웠는지 물어봐야 한다고 생각해요. "
    "평가의 목적은 줄 세우기가 아니라 다음 배움을 안내하는 것이다."
)


@pytest.fixture()
def vault(tmp_path, monkeypatch):
    """임시 볼트 + mock LLM."""
    monkeypatch.setenv("DG_VAULT_ROOT", str(tmp_path))
    inbox = tmp_path / "수집함" / "plaud"
    inbox.mkdir(parents=True)
    (inbox / "테스트 녹음.md").write_text(
        "---\nplaud_id: test-rec-001\nrecorded: 2026-07-05\n"
        "title: 수학 시간 성찰\n---\n" + TRANSCRIPT,
        encoding="utf-8",
    )
    monkeypatch.setattr(llm, "call_json",
                        lambda *a, **k: json.loads(json.dumps(TRIAGE_FIXTURE)))
    monkeypatch.setattr(llm, "call_writing",
                        lambda prompt, **k: "# 오답이 환영받는 교실\n\n본문입니다.")
    return tmp_path


def _run_once():
    recs = fetch_inbox()
    done = vault_io.processed_ids()
    created = []
    for rec in recs:
        if rec.id in done:
            continue
        artifacts = pipeline_run.process_recording(rec, dry_run=False)
        vault_io.mark_processed(rec.id, rec.name, artifacts)
        created.extend(artifacts)
    return created


def test_full_pipeline(vault):
    created = _run_once()
    assert created

    # ① 사례은행: 초록은 자동 입고, 노랑은 _노랑대기 + 결재함
    green = list((vault / "제텔카스텐/6. 사례은행").glob("사례 - *.md"))
    assert len(green) == 1
    text = green[0].read_text(encoding="utf-8")
    assert "틀리는 게 좋아요" in text
    assert "author: 이한결(구술)" in text
    assert "plaud:test-rec-001" in text

    yellow = list((vault / "제텔카스텐/6. 사례은행/_노랑대기").glob("*.md"))
    assert len(yellow) == 1
    queue = (vault / "_system/review_queue.md").read_text(encoding="utf-8")
    assert "노랑 사례 결재" in queue

    # 빨강: 볼트 어디에도 내용이 없다. 로그에 차단 통계만.
    all_md = "\n".join(p.read_text(encoding="utf-8")
                       for p in vault.rglob("*.md"))
    assert "가정사" not in all_md.replace("가정사 관련 민감 발화", "")
    logs = "\n".join(p.read_text(encoding="utf-8")
                     for p in (vault / "_system/logs").glob("*.log"))
    assert "빨강 차단 1건" in logs

    # ② 제텔카스텐 1→2→3단계
    memos = list((vault / "제텔카스텐/1. 메모").glob("*.md"))
    assert len(memos) == 1 and "오답 공유가 수학 불안을 줄인다" in memos[0].stem
    assert "verbatim: true" in memos[0].read_text(encoding="utf-8")

    kws = list((vault / "제텔카스텐/2. 키워드").glob("K_ai - *.md"))
    assert len(kws) == 1
    kw_text = kws[0].read_text(encoding="utf-8")
    assert "author: AI" in kw_text
    assert "[[오답 공유가 수학 불안을 줄인다]]" in kw_text  # 메모 링크

    ops = list((vault / "제텔카스텐/3. 의견").glob("O - *.md"))
    assert len(ops) == 1
    assert "author: 이한결(구술)" in ops[0].read_text(encoding="utf-8")

    # ③ 교사그룹 대상 초안: 블로그+페이스북, 상태는 리뷰대기 (발행은 사람)
    blog = list((vault / "프로젝트/교육운동/블로그_초안").glob("*.md"))
    fb = list((vault / "프로젝트/교육운동/페이스북_초안").glob("*.md"))
    assert len(blog) == 1 and len(fb) == 1
    blog_text = blog[0].read_text(encoding="utf-8")
    assert "상태: 리뷰대기" in blog_text
    assert "타겟: 교사그룹" in blog_text            # 학부모 채널과 혼용 금지 명시
    assert "타겟: 교사그룹" in fb[0].read_text(encoding="utf-8")

    # 교육운동 활동기록 (꿈들/새넷/전교조 녹음일 때)
    records = list((vault / "프로젝트/교육운동/활동기록").glob("*.md"))
    assert len(records) == 1
    rec_text = records[0].read_text(encoding="utf-8")
    assert "활동: 새넷" in rec_text and "프로젝트: 교육운동" in rec_text


def test_dedup_second_run(vault):
    first = _run_once()
    assert first
    # 인박스 파일이 남아 있어도(이관 전) 장부 기준으로 재처리하지 않는다
    second = _run_once()
    assert second == []
    memos = list((vault / "제텔카스텐/1. 메모").glob("*.md"))
    assert len(memos) == 1


def test_processed_ids_survives_ledger_loss(vault):
    _run_once()
    # 장부를 지워도 노트 frontmatter의 출처 필드에서 복원된다
    ledger = vault / "_system/logs/plaud_ledger.json"
    ledger.unlink()
    assert "test-rec-001" in vault_io.processed_ids()


def test_safe_filename():
    assert safe_filename('오답: "환영"받는 교실?') == "오답 환영 받는 교실"
    assert safe_filename("a/b\\c|d") == "a b c d"
    assert safe_filename("") == "무제"
    assert len(safe_filename("가" * 200)) <= 80


def test_no_files_on_llm_failure(vault, monkeypatch):
    """LLM 실패 시 파일을 만들지 않는다 (_검토필요 오염 재발 방지)."""
    def boom(*a, **k):
        raise ValueError("JSON 파싱 실패")
    monkeypatch.setattr(llm, "call_json", boom)
    recs = fetch_inbox()
    with pytest.raises(ValueError):
        pipeline_run.process_recording(recs[0], dry_run=False)
    assert not list((vault / "제텔카스텐/1. 메모").glob("*.md"))
    assert "test-rec-001" not in vault_io.processed_ids()
