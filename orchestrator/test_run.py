"""run.py의 안정성 수리(A1~A5)에 대한 단위테스트.

노션/옵시디언 백엔드 없이 orchestrator.run 이 참조하는 state 함수만 가짜로 갈아끼운다.
실행: python3 -m pytest orchestrator/test_run.py -q
"""
import types

from orchestrator import publish, run


class FakeState:
    """update_card/notify/read_latest_section/query_cards를 기록하는 가짜 백엔드."""

    def __init__(self, cards=None, sections=None):
        self.updates = []          # (page_id, fields) 누적
        self.notes = []            # (page_id, message)
        self._cards = cards or []
        self._sections = sections or {}  # (page_id, prefix) -> text

    def update_card(self, page_id, **fields):
        self.updates.append((page_id, fields))

    def notify(self, page_id, message):
        self.notes.append((page_id, message))

    def read_latest_section(self, page_id, prefix):
        return self._sections.get((page_id, prefix), "")

    def query_cards(self, stage=None, status=None, approval_status=None, page_size=20):
        out = []
        for c in self._cards:
            if stage and c.get("stage") != stage:
                continue
            if status and c.get("status") != status:
                continue
            if approval_status and c.get("approval_status") != approval_status:
                continue
            out.append(c)
        return out

    def age_minutes(self, card):
        return card.get("_age", 0.0)

    # run 이 호출할 수 있는 나머지는 no-op
    def require_backend(self):
        pass


def _patch(monkey_state):
    run.store = monkey_state
    publish.store = monkey_state


def _last_update(state, page_id):
    """가장 최근 update 병합 결과."""
    merged = {}
    for pid, fields in state.updates:
        if pid == page_id:
            merged.update(fields)
    return merged


# ---------- A2: 검수 미통과 승인은 조용히 막지 않고 통지 ----------

def test_final_approved_blocked_notifies():
    st = FakeState()
    _patch(st)
    card = {"page_id": "p1", "content_id": "DG-1", "review_status": "revise"}
    run.handle_final_approved(card)
    merged = _last_update(st, "p1")
    assert merged.get("status") == "needs_human"
    assert merged.get("approval_status") == "blocked"
    assert st.notes and "DG-1" in st.notes[-1][1]


def test_final_approved_ok_goes_publish_ready():
    st = FakeState()
    _patch(st)
    card = {"page_id": "p1", "content_id": "DG-1", "review_status": "approved"}
    run.handle_final_approved(card)
    merged = _last_update(st, "p1")
    assert merged.get("stage") == "publish_ready"
    assert merged.get("status") == "queued"


# ---------- A1: 수정 요청은 재초안 큐로 되돌린다 ----------

def test_revision_requested_reenqueues():
    st = FakeState(sections={("p1", run.REVISION_SECTION): "사례를 빼줘"})
    _patch(st)
    card = {"page_id": "p1", "content_id": "DG-1", "approved_keyword": "스마트폰 규칙"}
    run.handle_revision_requested(card)
    merged = _last_update(st, "p1")
    assert merged.get("stage") == "keyword_approval"
    assert merged.get("approval_status") == "approved"
    assert merged.get("status") == "running"


def test_revision_requested_without_keyword_goes_keyword_gate():
    st = FakeState()
    _patch(st)
    card = {"page_id": "p1", "content_id": "DG-1", "approved_keyword": ""}
    run.handle_revision_requested(card)
    merged = _last_update(st, "p1")
    assert merged.get("stage") == "keyword_approval"
    assert merged.get("approval_status") == "requested"
    assert st.notes  # 사람에게 통지


# ---------- A3: 실패는 1회 재시도 후 통지 ----------

def test_failure_retries_once_then_notifies():
    st = FakeState()
    _patch(st)
    card = {"page_id": "p1", "content_id": "DG-1", "last_error": ""}
    # 1차 실패: keyword 는 재큐 대상 → status=queued + 재시도 표식, 통지 없음
    run._handle_failure(card, "keyword", RuntimeError("boom"))
    merged = _last_update(st, "p1")
    assert merged.get("status") == "queued"
    assert merged.get("last_error", "").startswith(run._RETRY_MARK)
    assert not st.notes

    # 2차 실패(표식 있음): failed + 통지
    st2 = FakeState()
    _patch(st2)
    card2 = {"page_id": "p1", "content_id": "DG-1",
             "last_error": f"{run._RETRY_MARK} boom"}
    run._handle_failure(card2, "keyword", RuntimeError("boom again"))
    merged2 = _last_update(st2, "p1")
    assert merged2.get("status") == "failed"
    assert st2.notes


def test_failure_status_agnostic_dequeues_on_final():
    st = FakeState()
    _patch(st)
    card = {"page_id": "p1", "content_id": "DG-1",
            "last_error": f"{run._RETRY_MARK} x"}
    run._handle_failure(card, "keyword_approval", RuntimeError("boom"))
    merged = _last_update(st, "p1")
    assert merged.get("status") == "failed"
    assert merged.get("approval_status") == "failed"  # 무한 재시도 방지


def test_failure_publish_ready_revision_retries_then_dequeues():
    """publish_ready+revision_requested 항목은 발행이 아니라 재시도해도 안전 —
    1회 재시도 후에도 실패하면 approval_status=failed로 디큐해 무한 재시도를 막는다."""
    st = FakeState()
    _patch(st)
    card = {"page_id": "p1", "content_id": "DG-1", "last_error": ""}
    run._handle_failure(card, "publish_ready", RuntimeError("boom"),
                        approval="revision_requested")
    merged = _last_update(st, "p1")
    assert "status" not in merged  # 쿼리가 status 무시 → 그대로 두면 재시도됨
    assert merged.get("last_error", "").startswith(run._RETRY_MARK)
    assert not st.notes

    st2 = FakeState()
    _patch(st2)
    card2 = {"page_id": "p1", "content_id": "DG-1",
             "last_error": f"{run._RETRY_MARK} boom"}
    run._handle_failure(card2, "publish_ready", RuntimeError("boom again"),
                        approval="revision_requested")
    merged2 = _last_update(st2, "p1")
    assert merged2.get("status") == "failed"
    assert merged2.get("approval_status") == "failed"
    assert st2.notes


# ---------- 사각지대 해소: publish_ready + revision_requested도 재초안 경로 ----------

def test_dispatch_covers_publish_ready_revision_before_publish():
    """발행 실패 후 수정 요청이 접수된 카드(publish_ready+revision_requested)를
    handle_publish보다 먼저 handle_revision_requested가 집어야 한다."""
    entry = ("publish_ready", None, "revision_requested", run.handle_revision_requested)
    publish_entry = ("publish_ready", "queued", None, run.handle_publish)
    assert entry in run.DISPATCH
    assert run.DISPATCH.index(entry) < run.DISPATCH.index(publish_entry)


class MutatingState(FakeState):
    """update_card가 카드 dict에도 반영되는 가짜 백엔드 — run() 통합 경로용."""

    def update_card(self, page_id, **fields):
        super().update_card(page_id, **fields)
        for c in self._cards:
            if c.get("page_id") == page_id:
                c.update(fields)


def test_run_reroutes_failed_publish_ready_revision():
    card = {"page_id": "p1", "content_id": "DG-1", "stage": "publish_ready",
            "status": "failed", "approval_status": "revision_requested",
            "approved_keyword": "유튜브 그만"}
    st = MutatingState(cards=[card])
    _patch(st)
    run.run(only_stage="publish_ready")
    assert card["stage"] == "keyword_approval"  # 재초안 경로로 복귀
    assert card["status"] == "running"
    assert card["approval_status"] == "approved"


# ---------- A4: 오래 멈춘 draft/brief 는 재큐 ----------

def test_sweep_stale_running_requeues():
    stale = {"page_id": "p1", "content_id": "DG-1", "stage": "draft",
             "status": "running", "approved_keyword": "kw", "_age": 120.0}
    fresh = {"page_id": "p2", "content_id": "DG-2", "stage": "draft",
             "status": "running", "approved_keyword": "kw", "_age": 5.0}
    st = FakeState(cards=[stale, fresh])
    _patch(st)
    run._sweep_stale_running(now_limit=60)
    assert _last_update(st, "p1").get("stage") == "keyword_approval"
    assert not any(pid == "p2" for pid, _ in st.updates)  # 신선한 카드는 안 건드림


# ---------- A5: split_posts 는 글을 유실하지 않는다 ----------

def test_split_posts_no_text_loss_on_long_paragraph():
    sentences = [f"이건 {i}번째 문장입니다." for i in range(60)]
    draft = " ".join(sentences)  # 500자 훨씬 초과 단일 문단
    posts = publish.split_posts(draft)
    assert len(posts) > 1
    for p in posts:
        assert len(p) <= publish.POST_CHAR_LIMIT
    joined = " ".join(posts)
    for i in range(60):
        assert f"이건 {i}번째 문장입니다." in joined


def test_split_posts_respects_separator():
    draft = "가나다\n---\n라마바"
    assert publish.split_posts(draft) == ["가나다", "라마바"]


# ---------- 발행 회복력: threads_publish 재시도 + 부분 발행 재개 ----------

class _FakeResp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


class _FakeRequests:
    """publish가 부르는 requests.post/get을 흉내낸다. 큐에서 응답을 꺼내 준다."""

    def __init__(self, publish_responses):
        self.publish_responses = list(publish_responses)  # threads_publish 응답 큐
        self.container_calls = []   # 컨테이너 생성 params 기록
        self.publish_calls = 0
        self._container_seq = 0

    def post(self, url, params=None, timeout=None):
        if url.endswith("/threads_publish"):
            self.publish_calls += 1
            return self.publish_responses.pop(0)
        self._container_seq += 1
        self.container_calls.append(dict(params or {}))
        return _FakeResp(200, {"id": f"c{self._container_seq}"})

    def get(self, url, params=None, timeout=None):
        return _FakeResp(200, {"permalink": "https://threads.net/x"})


def _patch_publish_io(fake):
    publish.requests = fake
    publish.time = types.SimpleNamespace(sleep=lambda s: None)


def test_publish_container_retries_then_succeeds():
    """전파 지연('Media Not Found' 등)으로 발행이 즉시 실패해도 재시도로 성공한다."""
    fake = _FakeRequests([
        _FakeResp(400, {"error": {"message": "Media Not Found", "code": 24}}),
        _FakeResp(200, {"id": "m1"}),
    ])
    _patch_publish_io(fake)
    media_ids, permalink = publish.publish_chain(["글 하나"])
    assert media_ids == ["m1"]
    assert fake.publish_calls == 2  # 1회 실패 후 재시도 성공


def test_publish_container_gives_up_after_attempts():
    fake = _FakeRequests([
        _FakeResp(400, {"error": {"code": 24}})
    ] * publish.PUBLISH_ATTEMPTS)
    _patch_publish_io(fake)
    try:
        publish.publish_chain(["글 하나"])
        assert False, "실패해야 한다"
    except RuntimeError as e:
        assert "발행 실패 [1]" in str(e)
    assert fake.publish_calls == publish.PUBLISH_ATTEMPTS


def test_publish_chain_resumes_from_done_ids():
    """부분 발행 재개: 기발행 글은 건너뛰고 마지막 발행 글에 답글로 이어 붙인다."""
    fake = _FakeRequests([_FakeResp(200, {"id": "m3"})])
    _patch_publish_io(fake)
    progress = []
    media_ids, _ = publish.publish_chain(
        ["글1", "글2", "글3"], done_ids=["m1", "m2"],
        on_progress=lambda ids: progress.append(list(ids)),
    )
    assert media_ids == ["m1", "m2", "m3"]
    assert len(fake.container_calls) == 1          # 남은 1개만 새로 만든다
    assert fake.container_calls[0]["reply_to_id"] == "m2"  # 순차 체인 부모 유지
    assert progress == [["m1", "m2", "m3"]]         # 진행분 콜백 호출됨


def test_publish_chain_replies_to_previous_post():
    """연속 글은 직전 글에 답글로 달려야 피드에서 1/N…N/N으로 엮인다.

    전부 첫 글에 달면 Threads가 1/2·2/2로만 묶고 나머지는 접힌 댓글이 된다.
    """
    fake = _FakeRequests([
        _FakeResp(200, {"id": "m1"}),
        _FakeResp(200, {"id": "m2"}),
        _FakeResp(200, {"id": "m3"}),
    ])
    _patch_publish_io(fake)
    media_ids, _ = publish.publish_chain(["글1", "글2", "글3"])
    assert media_ids == ["m1", "m2", "m3"]
    assert "reply_to_id" not in fake.container_calls[0]      # 첫 글은 루트
    assert fake.container_calls[1]["reply_to_id"] == "m1"    # 2번째 → 1번째
    assert fake.container_calls[2]["reply_to_id"] == "m2"    # 3번째 → 2번째


# ---------- B5: 벤치마킹·후킹은 첫 집필에만 주입 ----------

def test_benchmark_and_hooks_only_in_first_draft(monkeypatch):
    from orchestrator import agent_dialogue as ad

    writer_prompts = []

    class FakeLLM:
        calls = {"json": 0}

        @staticmethod
        def call_writing(prompt, system="", max_tokens=8000):
            writer_prompts.append(prompt)
            return "초안 본문"

        @staticmethod
        def call_json(prompt, system="", **kw):
            FakeLLM.calls["json"] += 1
            if FakeLLM.calls["json"] == 1:
                # 비평가 1라운드: revise → 재작성 유발
                return {"verdict": "revise", "issues": ["더 구체적으로"],
                        "suggestions": []}
            if FakeLLM.calls["json"] == 2:
                return {"verdict": "pass"}
            # 교육윤리 검수: approved → 추가 재작성 없음
            return {"review_status": "approved", "risk_level": "low"}

    monkeypatch.setattr(ad, "llm", FakeLLM)
    brief = {"core_message": "핵심", "cta": "행동"}
    ad.run_draft_dialogue(
        brief, "thread", style_context="학습된 문체",
        hook_examples="후킹패턴XYZ", benchmark="벤치마킹ABC",
    )
    assert len(writer_prompts) >= 2          # v1 + 재작성 최소 1회
    assert "벤치마킹ABC" in writer_prompts[0]  # 첫 집필엔 있음
    assert "후킹패턴XYZ" in writer_prompts[0]
    assert "벤치마킹ABC" not in writer_prompts[1]  # 재작성엔 없음(B5)
    assert "후킹패턴XYZ" not in writer_prompts[1]
    assert "학습된 문체" in writer_prompts[1]      # 스타일은 계속 유지


# ---------- 새 카드 접수 텔레그램 통지 ----------

def test_intake_notifies_new_card(monkeypatch):
    state = FakeState()
    state.append_formatted_section = lambda *a, **k: None
    _patch(state)
    fake_manus = types.SimpleNamespace(
        available=lambda: False,
        claude_research_fallback=lambda topic, audience: [],
    )
    monkeypatch.setattr(run, "manus_research", fake_manus)
    run.handle_intake({
        "page_id": "p1", "content_id": "DG-2026-0009",
        "idempotency_key": "", "topic": "받아쓰기 우는 아이", "audience": "학부모",
    })
    assert any("🆕" in msg and "받아쓰기 우는 아이" in msg for _, msg in state.notes)


# ---------- 열람 사본 내보내기 ----------

def test_review_copy_export_writes_named_file(tmp_path, monkeypatch):
    from orchestrator import review_copy
    monkeypatch.setenv("DG_VAULT_ROOT", str(tmp_path))
    monkeypatch.delenv("VAULT_SCRIPT_PATH", raising=False)
    card = {"topic": "받아쓰기 시험만 보면 우는 아이", "content_id": "DG-2026-0001",
            "approved_keyword": "받아쓰기 불안"}
    name = review_copy.export(card, "thread", "초안 본문입니다.")
    assert name.startswith("스레드_") and name.endswith(".md")
    saved = (tmp_path / "SNS 콘텐츠 제작 시스템/05 리뷰/대기" / name).read_text(
        encoding="utf-8")
    # content_id로 카드와 연결되고, 검수상태 대기라 script_feedback이 알림을 보낸다.
    assert "content_id: DG-2026-0001" in saved
    assert "검수상태: 대기" in saved
    assert "초안 본문입니다." in saved
    # 재초안 시 같은 이름으로 덮어써 최신 초안을 비춘다.
    assert review_copy.export(card, "thread", "수정된 본문") == name


# ---------- 글감 카드: 리서치 생략 + 작가에 원문 주입 ----------

def test_intake_with_source_material_skips_research(monkeypatch):
    st = FakeState(sections={("p1", run.SOURCE_SECTION): "완성된 글감 원문"})
    _patch(st)

    def _fail(*a, **k):
        raise AssertionError("글감 카드는 리서치를 호출하면 안 됨")

    monkeypatch.setattr(run, "manus_research", types.SimpleNamespace(
        available=_fail, create_research_tasks=_fail, claude_research_fallback=_fail,
    ))
    run.handle_intake({
        "page_id": "p1", "content_id": "DG-2026-0047",
        "idempotency_key": "", "topic": "물건으로 관계 맺는 아이", "audience": "학부모",
    })
    merged = _last_update(st, "p1")
    assert merged.get("stage") == "keyword"
    assert merged.get("status") == "queued"
    assert any("글감" in msg for _, msg in st.notes)


def test_dialogue_source_material_kept_across_rewrites(monkeypatch):
    from orchestrator import agent_dialogue as ad

    writer_prompts = []

    class FakeLLM:
        calls = {"json": 0}

        @staticmethod
        def call_writing(prompt, system="", max_tokens=8000):
            writer_prompts.append(prompt)
            return "초안 본문"

        @staticmethod
        def call_json(prompt, system="", **kw):
            FakeLLM.calls["json"] += 1
            if FakeLLM.calls["json"] == 1:
                return {"verdict": "revise", "issues": ["수정"], "suggestions": []}
            if FakeLLM.calls["json"] == 2:
                return {"verdict": "pass"}
            return {"review_status": "approved", "risk_level": "low"}

    monkeypatch.setattr(ad, "llm", FakeLLM)
    ad.run_draft_dialogue(
        {"core_message": "핵심", "cta": "행동"}, "thread",
        benchmark="벤치마킹ABC", source_material="글감원문QRS",
    )
    assert len(writer_prompts) >= 2
    # 글감은 첫 집필과 재작성 모두에 유지된다(원문 보존 기준).
    for p in writer_prompts:
        assert "글감원문QRS" in p
    assert "벤치마킹ABC" not in writer_prompts[1]  # 벤치마킹은 여전히 첫 집필만


# ---------- 발행 예약 (publish_at) ----------

def _future_kst(minutes=90):
    from datetime import datetime, timedelta
    return (datetime.now(run.KST) + timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M")


def _past_kst(minutes=90):
    return _future_kst(-minutes)


def test_publish_waits_until_scheduled_time(monkeypatch):
    """publish_at이 미래면 발행하지 않고 상태도 건드리지 않는다(다음 cron에서 재시도)."""
    st = FakeState()
    _patch(st)
    called = []
    monkeypatch.setattr(publish, "handle_publish", lambda card: called.append(card))
    card = {"page_id": "p1", "content_id": "DG-1", "stage": "publish_ready",
            "status": "queued", "publish_at": _future_kst()}
    run.handle_publish(card)
    assert not called
    assert not st.updates and not st.notes


def test_publish_fires_after_scheduled_time(monkeypatch):
    st = FakeState()
    _patch(st)
    called = []
    monkeypatch.setattr(publish, "handle_publish", lambda card: called.append(card))
    card = {"page_id": "p1", "content_id": "DG-1", "publish_at": _past_kst()}
    run.handle_publish(card)
    assert called


def test_publish_without_schedule_fires_immediately(monkeypatch):
    """publish_at이 비어 있으면 기존처럼 즉시 발행(회귀 방지)."""
    st = FakeState()
    _patch(st)
    called = []
    monkeypatch.setattr(publish, "handle_publish", lambda card: called.append(card))
    run.handle_publish({"page_id": "p1", "content_id": "DG-1", "publish_at": ""})
    assert called


def test_publish_invalid_schedule_dequeues_and_notifies(monkeypatch):
    """publish_at 형식 오류는 조용히 무한 보류하지 않고 needs_human + 통지."""
    st = FakeState()
    _patch(st)
    called = []
    monkeypatch.setattr(publish, "handle_publish", lambda card: called.append(card))
    card = {"page_id": "p1", "content_id": "DG-1", "publish_at": "내일 아침"}
    run.handle_publish(card)
    assert not called
    merged = _last_update(st, "p1")
    assert merged.get("status") == "needs_human"
    assert st.notes and "publish_at" in st.notes[-1][1]


def test_final_approved_future_schedule_notifies():
    st = FakeState()
    _patch(st)
    when = _future_kst()
    card = {"page_id": "p1", "content_id": "DG-1", "review_status": "approved",
            "publish_at": when}
    run.handle_final_approved(card)
    merged = _last_update(st, "p1")
    assert merged.get("stage") == "publish_ready"
    assert st.notes and when in st.notes[-1][1]  # 예약 안내 통지


def test_final_approved_stamps_default_publish_time(monkeypatch):
    """DG_DEFAULT_PUBLISH_TIME이 설정되면 publish_at이 빈 카드에 다음 도래 시각을 기입."""
    st = FakeState()
    _patch(st)
    monkeypatch.setattr(run, "DEFAULT_PUBLISH_TIME", "08:00")
    card = {"page_id": "p1", "content_id": "DG-1", "review_status": "approved",
            "publish_at": ""}
    run.handle_final_approved(card)
    merged = _last_update(st, "p1")
    assert merged.get("stage") == "publish_ready"
    stamped = merged.get("publish_at", "")
    assert stamped.endswith("08:00")
    assert run._parse_publish_at(stamped) is not None


def test_next_default_publish_at_rolls_to_tomorrow():
    from datetime import datetime
    now = datetime(2026, 8, 24, 9, 30, tzinfo=run.KST)
    orig = run.DEFAULT_PUBLISH_TIME
    try:
        run.DEFAULT_PUBLISH_TIME = "08:00"
        assert run._next_default_publish_at(now) == "2026-08-25 08:00"
        run.DEFAULT_PUBLISH_TIME = "10:00"
        assert run._next_default_publish_at(now) == "2026-08-24 10:00"
        run.DEFAULT_PUBLISH_TIME = "잘못됨"
        assert run._next_default_publish_at(now) == ""
    finally:
        run.DEFAULT_PUBLISH_TIME = orig
