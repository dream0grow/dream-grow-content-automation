"""Apple Notes → 제텔카스텐 1단계(메모) 변환기

Apple Notes 560개를 읽어:
1. AppleScript로 노트 제목/본문 추출
2. 중복 확인 (이미 제텔카스텐에 있는 것 건너뜀)
3. Claude API로 핵심 주장 1문장 추출 → 파일명으로 사용
4. 제텔카스텐 1단계 - 메모/ 에 저장

사용법:
  python3 apple_notes_to_zettel.py --count          # 노트 수 확인
  python3 apple_notes_to_zettel.py --export          # 노트 내보내기만 (raw/)
  python3 apple_notes_to_zettel.py --convert         # raw/ → 제텔카스텐 변환
  python3 apple_notes_to_zettel.py --all             # 내보내기 + 변환 전체
  python3 apple_notes_to_zettel.py --dry-run         # 변환 미리보기
  python3 apple_notes_to_zettel.py --batch N         # N개씩 배치 처리
"""
import claude_client; claude_client.patch_anthropic()
import os
import re
import sys
import json
import subprocess
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

ZETTEL_BASE = "/Users/lhg/Documents/obsidian/초생산/제텔카스텐/5. 제텔카스텐"
MEMO_DIR = os.path.join(ZETTEL_BASE, "1단계 - 메모")
RAW_EXPORT_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "apple_notes_raw"
)
PROGRESS_FILE = os.path.join(RAW_EXPORT_DIR, "_progress.json")


def run_applescript(script: str) -> str:
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=300
    )
    if result.returncode != 0:
        raise RuntimeError(f"AppleScript 오류: {result.stderr}")
    return result.stdout.strip()


def count_notes() -> int:
    return int(run_applescript('tell application "Notes" to count every note'))


def export_notes_batch(start: int, batch_size: int) -> list:
    """Apple Notes에서 배치로 노트를 내보냅니다."""
    script = f'''
    tell application "Notes"
        set noteList to every note
        set output to ""
        set endIdx to {start} + {batch_size} - 1
        if endIdx > (count of noteList) then set endIdx to (count of noteList)
        repeat with i from {start} to endIdx
            set n to item i of noteList
            set noteTitle to name of n
            set noteBody to plaintext of n
            set noteDate to creation date of n
            set output to output & "===NOTE_START===" & return
            set output to output & "TITLE:" & noteTitle & return
            set output to output & "DATE:" & (noteDate as string) & return
            set output to output & "BODY:" & return & noteBody & return
            set output to output & "===NOTE_END===" & return
        end repeat
        return output
    end tell
    '''
    raw = run_applescript(script)
    notes = []
    for block in raw.split("===NOTE_START==="):
        block = block.strip()
        if "===NOTE_END===" not in block:
            continue
        block = block.replace("===NOTE_END===", "").strip()
        lines = block.split("\n")
        title = ""
        date = ""
        body_lines = []
        in_body = False
        for line in lines:
            if line.startswith("TITLE:"):
                title = line[6:].strip()
            elif line.startswith("DATE:"):
                date = line[5:].strip()
            elif line.startswith("BODY:"):
                in_body = True
            elif in_body:
                body_lines.append(line)
        body = "\n".join(body_lines).strip()
        if title and body:
            notes.append({"title": title, "date": date, "body": body})
    return notes


def save_raw_notes(notes: list, batch_num: int):
    """내보낸 노트를 raw 파일로 저장합니다."""
    os.makedirs(RAW_EXPORT_DIR, exist_ok=True)
    for i, note in enumerate(notes):
        safe_title = re.sub(r'[/\\:*?"<>|]', '_', note["title"])[:80]
        filepath = os.path.join(RAW_EXPORT_DIR, f"{safe_title}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(note, f, ensure_ascii=False, indent=2)
    print(f"  배치 {batch_num}: {len(notes)}개 저장")


def get_existing_zettel_titles() -> set:
    """이미 제텔카스텐에 있는 제목들을 수집합니다."""
    titles = set()
    for stage_dir in os.listdir(ZETTEL_BASE):
        full_dir = os.path.join(ZETTEL_BASE, stage_dir)
        if not os.path.isdir(full_dir):
            continue
        for fname in os.listdir(full_dir):
            if fname.endswith(".md"):
                titles.add(fname.replace(".md", ""))
    return titles


def extract_claim(title: str, body: str) -> str:
    """Claude API로 핵심 주장 1문장을 추출합니다."""
    import anthropic
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    prompt = f"""다음 메모에서 핵심 주장을 1문장으로 추출해주세요.

제목: {title}
내용: {body[:2000]}

규칙:
- "~이다." 또는 "~것이다." 형태의 단정적 주장 1문장
- 50자 이내
- 구체적이고 독립적으로 이해 가능한 문장
- 예: "아이의 자존감은 칭찬이 아니라 실패 경험에서 자란다."

주장:"""

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=100,
        messages=[{"role": "user", "content": prompt}],
    )
    claim = message.content[0].text.strip().strip('"').strip("'")
    if not claim.endswith(".") and not claim.endswith("다."):
        claim += "."
    return claim


def convert_to_zettel(note: dict, existing: set, dry_run: bool = False) -> str | None:
    """단일 노트를 제텔카스텐 1단계 메모로 변환합니다."""
    title = note["title"]
    body = note["body"]

    if len(body) < 50:
        return None

    claim = extract_claim(title, body)

    safe_claim = re.sub(r'[/\\:*?"<>|]', '', claim)[:80]

    if safe_claim in existing:
        return None

    if dry_run:
        print(f"  [DRY] {title[:40]} → {safe_claim}")
        return safe_claim

    content = f"""---
출처: Apple Notes
원제: {title}
변환일: {datetime.now().strftime('%Y-%m-%d')}
단계: 1단계 메모
---

{body}
"""

    filepath = os.path.join(MEMO_DIR, f"{safe_claim}.md")
    os.makedirs(MEMO_DIR, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    return safe_claim


def load_progress() -> dict:
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r") as f:
            return json.load(f)
    return {"exported": 0, "converted": 0, "skipped": [], "errors": []}


def save_progress(progress: dict):
    os.makedirs(RAW_EXPORT_DIR, exist_ok=True)
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def cmd_count():
    total = count_notes()
    print(f"Apple Notes: {total}개")
    existing = get_existing_zettel_titles()
    print(f"기존 제텔카스텐: {len(existing)}개")
    progress = load_progress()
    print(f"내보내기 완료: {progress['exported']}개")
    print(f"변환 완료: {progress['converted']}개")


def cmd_export():
    """Apple Notes 전체를 raw JSON으로 내보냅니다."""
    total = count_notes()
    print(f"Apple Notes {total}개 내보내기 시작")

    progress = load_progress()
    batch_size = 20
    start = progress["exported"] + 1

    for batch_start in range(start, total + 1, batch_size):
        print(f"\n배치 처리: {batch_start}~{min(batch_start + batch_size - 1, total)}")
        try:
            notes = export_notes_batch(batch_start, batch_size)
            save_raw_notes(notes, batch_start // batch_size + 1)
            progress["exported"] = min(batch_start + batch_size - 1, total)
            save_progress(progress)
        except Exception as e:
            print(f"  오류: {e}")
            progress["errors"].append(f"batch {batch_start}: {str(e)}")
            save_progress(progress)
            break

    print(f"\n내보내기 완료: {progress['exported']}/{total}개")


def cmd_convert(dry_run: bool = False, batch_limit: int = 0):
    """raw JSON을 제텔카스텐으로 변환합니다."""
    if not os.path.isdir(RAW_EXPORT_DIR):
        print("먼저 --export로 노트를 내보내세요.")
        return

    files = [f for f in os.listdir(RAW_EXPORT_DIR) if f.endswith(".json") and f != "_progress.json"]
    existing = get_existing_zettel_titles()
    progress = load_progress()

    print(f"변환 대상: {len(files)}개 (기존 제텔: {len(existing)}개)")
    if dry_run:
        print("모드: DRY RUN")

    converted = 0
    skipped = 0
    errors = 0

    for fname in sorted(files):
        if batch_limit and converted >= batch_limit:
            print(f"\n배치 한도 도달: {batch_limit}개")
            break

        filepath = os.path.join(RAW_EXPORT_DIR, fname)
        with open(filepath, "r", encoding="utf-8") as f:
            note = json.load(f)

        try:
            result = convert_to_zettel(note, existing, dry_run=dry_run)
            if result:
                converted += 1
                existing.add(result)
                if not dry_run:
                    progress["converted"] += 1
            else:
                skipped += 1
        except Exception as e:
            errors += 1
            print(f"  오류: {note['title'][:30]} - {e}")
            progress["errors"].append(f"{note['title']}: {str(e)}")

    if not dry_run:
        save_progress(progress)

    print(f"\n결과: 변환 {converted}개, 건너뜀 {skipped}개, 오류 {errors}개")


def main():
    if "--count" in sys.argv:
        cmd_count()
    elif "--export" in sys.argv:
        cmd_export()
    elif "--convert" in sys.argv:
        dry_run = "--dry-run" in sys.argv
        batch_limit = 0
        if "--batch" in sys.argv:
            idx = sys.argv.index("--batch")
            if idx + 1 < len(sys.argv):
                batch_limit = int(sys.argv[idx + 1])
        cmd_convert(dry_run=dry_run, batch_limit=batch_limit)
    elif "--all" in sys.argv:
        cmd_export()
        print("\n" + "=" * 50 + "\n")
        cmd_convert()
    else:
        print("Apple Notes → 제텔카스텐 변환기")
        print()
        print("사용법:")
        print("  python3 apple_notes_to_zettel.py --count          # 현황 확인")
        print("  python3 apple_notes_to_zettel.py --export         # Notes 내보내기")
        print("  python3 apple_notes_to_zettel.py --convert        # 제텔카스텐 변환")
        print("  python3 apple_notes_to_zettel.py --convert --dry-run  # 미리보기")
        print("  python3 apple_notes_to_zettel.py --convert --batch 50 # 50개씩")
        print("  python3 apple_notes_to_zettel.py --all            # 전체 실행")


if __name__ == "__main__":
    main()
