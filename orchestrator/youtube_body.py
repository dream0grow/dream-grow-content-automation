"""유튜브 도입부 → 본문 자동 완성 파이프라인.

사용자가 벤치마킹 시트(분석 탭) X열 「만든 도입부」에 도입부를 써넣으면,
이 모듈이 (cron 폴링으로) 그 행을 찾아:
  ① 행 맥락(만든 제목 S, 키워드 L, 시청자 분석 E~H, 키워드 디벨롭 M)을 모으고
  ② 필수 메시지 정리(T08)를 설계한 뒤
  ③ 사용자 도입부를 **원문 그대로** 앞에 두고 본문·마무리·제작 메모를 이어 쓴다
     (문체는 data/youtube_voice.md — Roam 원고에서 실측 학습한 보이스 프로필).
완성 원고는 `vault/파이프라인/활성/` 카드(stage: draft, status: needs_human,
format: youtube)로 저장하고, `05 리뷰/대기`에도 사본을 둬 기존 텔레그램
핑퐁(script_feedback)이 알림·답장 수정을 잇는다. 시트 「완성 원고」열(Y)에는
카드 GitHub 링크를 되써넣는다.

재처리 규칙: 장부(_system/logs/youtube_body_ledger.json)에 행별 도입부 해시를
기록한다. 사용자가 X열 도입부를 고치면 해시가 바뀌어 다음 폴링에 새로 생성된다.
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator import gsheet, llm, prompts, youtube_script
from orchestrator import state as store
from orchestrator.thumbnail import col_letter
from vault_pipeline.vault_io import vault_root

VOICE_FILE = Path(__file__).resolve().parent.parent / "data" / "youtube_voice.md"
LEDGER_REL = Path("_system") / "logs" / "youtube_body_ledger.json"
LAST_COL = "AZ"  # 열 개편에 대비해 넉넉히 읽는다 (resolve가 이름으로 찾음)

# 기본 열 배치 (2026-08-19 분석 탭). 헤더 행을 이름으로 재해석하므로 폴백일 뿐이다.
COL_DEFAULT = {"date_kw": 0, "situation": 4, "worry": 5, "desire": 6, "plan": 7,
               "my_keyword": 11, "kw_develop": 12, "made_title": 18,
               "intro": 23, "result": 24}

_HEADER_PATTERNS = [
    ("intro", "만든도입부"),
    ("result", "완성원고"),
    ("made_title", "만든제목"),
    ("my_keyword", "내가만들"),
    ("kw_develop", "키워드로문구디벨롭"),
    ("kw_develop", "문구디벨롭"),
    ("date_kw", "날짜"),
    ("situation", "상황"), ("worry", "고민"), ("desire", "욕구"), ("plan", "계획"),
]


def log(msg: str):
    print(f"[youtube_body] {msg}", flush=True)


def _norm(cell) -> str:
    return re.sub(r"\s+", "", str(cell or ""))


def resolve_columns(header: list[str]) -> dict[str, int]:
    """헤더 행에서 열 이름을 찾아 {키: 인덱스}. 못 찾은 키는 기본값."""
    cols = dict(COL_DEFAULT)
    found: set[str] = set()
    for idx, cell in enumerate(header):
        name = _norm(cell)
        if not name:
            continue
        for key, pat in _HEADER_PATTERNS:
            if key not in found and name.startswith(pat):
                cols[key] = idx
                found.add(key)
                break
    # 「완성 원고」열이 시트에 없으면 도입부 바로 오른쪽 열을 쓴다
    if "result" not in found:
        cols["result"] = cols["intro"] + 1
    return cols


def find_header_row(rows: list[list[str]]) -> int:
    """「만든 도입부」가 있는 헤더 행 인덱스(0-base). 없으면 0."""
    for i, row in enumerate(rows[:6]):
        if any(_norm(c).startswith("만든도입부") for c in row):
            return i
    return 0


def _cell(row: list[str], idx: int) -> str:
    return (row[idx] if idx < len(row) else "").strip()


def intro_hash(text: str) -> str:
    return hashlib.sha1(_norm(text).encode("utf-8")).hexdigest()[:12]


# ---------- 장부 (도입부 해시로 재처리 방지) ----------

def _ledger_path() -> Path:
    return vault_root() / LEDGER_REL


def load_ledger() -> dict:
    try:
        return json.loads(_ledger_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_ledger(ledger: dict) -> None:
    p = _ledger_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(ledger, ensure_ascii=False, indent=1), encoding="utf-8")


def find_pending(rows: list[list[str]], cols: dict[str, int], header_i: int,
                 ledger: dict) -> list[int]:
    """도입부(X)가 있고, 장부에 같은 해시가 없는 행 인덱스(0-base) 목록."""
    out = []
    for i, row in enumerate(rows):
        if i <= header_i:
            continue
        intro = _cell(row, cols["intro"])
        if len(intro) < 50:  # 도입부라기엔 짧은 메모/빈 칸은 건너뜀
            continue
        if ledger.get(str(i + 1)) == intro_hash(intro):
            continue
        out.append(i)
    return out


# ---------- 생성 ----------

def load_voice() -> str:
    """Roam 원고에서 학습한 보이스 프로필. 없으면 빈 문자열(프롬프트 기본 원칙만)."""
    try:
        text = VOICE_FILE.read_text(encoding="utf-8").strip()
        return f"[보이스 프로필 — 사용자의 실제 원고에서 학습한 문체. 반드시 따를 것]\n{text}"
    except OSError:
        return ""


def row_context(row: list[str], cols: dict[str, int]) -> dict:
    viewer = "\n".join(
        f"- {label}: {_cell(row, cols[key])}"
        for label, key in (("상황", "situation"), ("고민", "worry"),
                           ("욕구", "desire"), ("계획", "plan"))
        if _cell(row, cols[key]))
    title = _cell(row, cols["made_title"]).split("\n")[0].strip()
    return {
        "title": title or _cell(row, cols["my_keyword"]) or "무제",
        "keyword": _cell(row, cols["my_keyword"]) or _cell(row, cols["date_kw"]),
        "intro": _cell(row, cols["intro"]),
        "viewer": viewer or "(시트에 분석 없음)",
        "develop": _cell(row, cols["kw_develop"])[:1500] or "(없음)",
    }


def generate_messages(ctx: dict, audience: str) -> str:
    """②단계 — 필수 메시지 정리(T08)."""
    prompt = prompts.YOUTUBE_BODY_MESSAGES.format(
        title=ctx["title"], keyword=ctx["keyword"], audience=audience,
        intro=ctx["intro"], viewer=ctx["viewer"], develop=ctx["develop"])
    out = llm.call_writing(prompt, system=prompts.get_system(), max_tokens=4000).strip()
    if len(out) < 200:
        raise RuntimeError(f"필수 메시지 정리가 비정상적으로 짧습니다 ({len(out)}자)")
    return out


def generate_body(ctx: dict, messages: str, audience: str) -> str:
    """③단계 — 본문·마무리·제작 메모 (도입부는 다시 쓰지 않는다)."""
    minutes = youtube_script.script_minutes()
    prompt = prompts.YOUTUBE_BODY.format(
        title=ctx["title"], audience=audience, minutes=minutes,
        chars=minutes * youtube_script.CHARS_PER_MINUTE,
        intro=ctx["intro"], messages=messages, voice=load_voice())
    out = llm.call_writing(prompt, system=prompts.get_system(), max_tokens=16000).strip()
    if len(out) < 500:
        raise RuntimeError(f"본문이 비정상적으로 짧습니다 ({len(out)}자)")
    return out


def assemble_script(ctx: dict, body: str) -> str:
    """사용자 도입부 원문을 앞에 두고 LLM 본문을 잇는다 — 도입부는 한 글자도 안 바뀐다."""
    return (f"# 영상 원고 -- {ctx['title']}\n\n"
            f"## 🎬 도입부 (0:00~0:30) — 사용자 원문\n\n{ctx['intro']}\n\n{body}\n")


def save_card(ctx: dict, messages: str, script: str, audience: str) -> str:
    """완성 원고를 파이프라인 활성 카드로 저장. page_id 반환.

    stage: draft + status: needs_human — run.py DISPATCH 어느 항목에도 걸리지 않아
    오케스트레이터가 재처리하지 않는다. 종착지는 사람의 촬영이다.
    """
    page_id = store.create_card(ctx["title"], stage="draft", status="needs_human",
                                audience=audience)
    store.update_card(page_id, format="youtube", approved_keyword=ctx["keyword"])
    store.append_section(page_id, "🧭 필수 메시지 정리 (자동)", messages)
    store.append_section(page_id, "✍️ 영상 원고 (도입부 사용자 원문 + 본문 자동)", script)
    return page_id


def process_row(row: list[str], cols: dict[str, int], rownum: int,
                audience: str, save_review: bool = True) -> dict:
    """행 하나를 도입부→완성 원고로 처리한다. 결과 dict 반환."""
    ctx = row_context(row, cols)
    log(f"행{rownum} 처리: {ctx['title'][:40]}")
    messages = generate_messages(ctx, audience)
    body = generate_body(ctx, messages, audience)
    script = assemble_script(ctx, body)
    page_id = save_card(ctx, messages, script, audience)
    m = re.search(r"(DG-\d{4}-\d{4})", page_id)
    cid = m.group(1) if m else page_id
    review_name = ""
    if save_review:  # 05 리뷰/대기 사본 → script_feedback 텔레그램 핑퐁이 잇는다
        try:
            review_name = youtube_script.save_to_review(
                {"topic": ctx["title"], "approved_keyword": ctx["keyword"],
                 "content_id": cid}, script)
        except Exception as e:  # noqa: BLE001 — 사본은 부가 경로, 실패해도 카드는 살아있다
            log(f"  리뷰 사본 저장 실패(계속): {e}")
    store.notify(page_id,
                 f"🎬 도입부→본문 완성: {ctx['title'][:60]}\n"
                 f"시트 행{rownum} 도입부를 받아 본문까지 썼습니다. 검토 후 촬영하세요."
                 + (f"\n리뷰 사본: {review_name}" if review_name else ""))
    return {"page_id": page_id, "content_id": cid, "review": review_name, "ctx": ctx}


def card_link(page_id: str) -> str:
    """카드 GitHub blob URL — 이 모듈이 만드는 카드는 항상 활성 폴더에 있다."""
    from vault_pipeline import telegram_notify
    return telegram_notify.note_url(f"파이프라인/활성/{Path(page_id).name}")


def run_sheet(audience: str, max_rows: int = 2, dry_run: bool = False):
    """시트 폴링 — 도입부 있는 새 행(또는 도입부가 바뀐 행)을 찾아 처리."""
    if not gsheet.available():
        log("GSHEET_SA_JSON 미설정 — 시트 모드를 건너뜁니다 (서비스 계정 키 필요)")
        return
    sheet_title = gsheet.resolve_title()
    rows = gsheet.read(f"A1:{LAST_COL}1000", sheet_title)
    header_i = find_header_row(rows)
    cols = resolve_columns(rows[header_i] if rows else [])
    ledger = load_ledger()

    pending = find_pending(rows, cols, header_i, ledger)
    if not pending:
        log("처리할 행 없음 (새 도입부 없음)")
        return
    log(f"대기 행 {len(pending)}개 → 최대 {max_rows}개 처리")

    for i in pending[:max_rows]:
        row, rownum = rows[i], i + 1
        if dry_run:
            log(f"행{rownum} (dry-run): {_cell(row, cols['intro'])[:60]}…")
            continue
        try:
            result = process_row(row, cols, rownum, audience)
        except Exception as e:  # noqa: BLE001 — 한 행 실패가 다음 행을 막지 않게
            log(f"  행{rownum} 실패: {e}")
            continue
        ledger[str(rownum)] = intro_hash(_cell(row, cols["intro"]))
        save_ledger(ledger)
        # 「완성 원고」열에 카드 링크 되써넣기 (실패해도 카드는 이미 볼트에 있다)
        try:
            gsheet.update(f"{col_letter(cols['result'])}{rownum}",
                          [[card_link(result["page_id"])]], sheet_title)
        except Exception as e:  # noqa: BLE001
            log(f"  행{rownum} 시트 되써넣기 실패(계속): {e}")
        log(f"  행{rownum} 완료 → {result['content_id']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audience", default="초등 저학년 학부모")
    ap.add_argument("--max-rows", type=int, default=2, help="한 번에 처리할 행 수")
    ap.add_argument("--dry-run", action="store_true", help="생성 없이 대기 행만 출력")
    args = ap.parse_args()
    run_sheet(args.audience, max_rows=args.max_rows, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
