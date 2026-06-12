"""리드마그넷 MD → PDF 변환 + Google Drive 전송

09 리드마그넷/ 에서 '확정' 상태 파일을:
1. Markdown → PDF 변환 (A4, 한글 폰트)
2. Google Drive 전송 폴더에 복사
3. frontmatter에 PDF 경로 기록

사용법:
  python3 lead_magnet_pdf.py                # 확정된 것만 변환+전송
  python3 lead_magnet_pdf.py --dry-run      # 미리보기
  python3 lead_magnet_pdf.py --list         # 현황
  python3 lead_magnet_pdf.py --file "파일"   # 단일 파일
"""
import os
import re
import sys
import shutil
from datetime import datetime
from fpdf import FPDF

SNS_SYSTEM = "/Users/lhg/Documents/obsidian/초생산/SNS 콘텐츠 제작 시스템"
MAGNET_DIR = os.path.join(SNS_SYSTEM, "09 리드마그넷")
PDF_OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "pdf_output"
)
GDRIVE_DIR = "/Users/lhg/Library/CloudStorage/GoogleDrive-leehg0211@gmail.com/내 드라이브/파일전송"

FONT_PATH = "/Users/lhg/Library/Fonts/NanumGothic.ttf"
FONT_BOLD_PATH = "/Users/lhg/Library/Fonts/NanumGothicBold.ttf"


class KoreanPDF(FPDF):
    def __init__(self):
        super().__init__()
        self.add_font("Korean", "", FONT_PATH)
        self.add_font("Korean", "B", FONT_BOLD_PATH)
        self.set_auto_page_break(auto=True, margin=20)

    def header(self):
        self.set_font("Korean", "B", 9)
        self.set_text_color(150, 150, 150)
        self.cell(0, 8, "Dream_Grow  |  아이와 부모의 꿈을 키웁니다", align="R")
        self.ln(12)

    def footer(self):
        self.set_y(-15)
        self.set_font("Korean", "", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"@dream_grow_lee  |  {self.page_no()}", align="C")


def parse_frontmatter(filepath: str) -> dict:
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    fm = {}
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if match:
        for line in match.group(1).split("\n"):
            if ":" in line:
                key, val = line.split(":", 1)
                fm[key.strip()] = val.strip().strip("\"'")
    fm["_content"] = content
    fm["_filepath"] = filepath
    fm["_filename"] = os.path.basename(filepath)
    return fm


def get_body(content: str) -> str:
    match = re.match(r"^---\n.*?\n---\n?", content, re.DOTALL)
    if match:
        return content[match.end():].strip()
    return content.strip()


def md_to_pdf(filepath: str, output_path: str) -> str:
    fm = parse_frontmatter(filepath)
    body = get_body(fm["_content"])
    title = fm.get("주제", fm["_filename"].replace(".md", ""))
    magnet_type = fm.get("유형", fm.get("type", ""))
    category = fm.get("카테고리", "")

    pdf = KoreanPDF()
    pdf.add_page()

    pdf.set_font("Korean", "B", 22)
    pdf.set_text_color(40, 40, 40)
    pdf.multi_cell(0, 12, title, align="C")
    pdf.ln(3)

    if category or magnet_type:
        pdf.set_font("Korean", "", 11)
        pdf.set_text_color(100, 100, 100)
        subtitle = " | ".join(filter(None, [category, magnet_type]))
        pdf.cell(0, 8, subtitle, align="C")
        pdf.ln(10)

    pdf.set_draw_color(200, 200, 200)
    pdf.line(20, pdf.get_y(), 190, pdf.get_y())
    pdf.ln(8)

    for line in body.split("\n"):
        line = line.rstrip()
        pdf.set_x(pdf.l_margin)  # X 좌표 리셋

        if line.startswith("### "):
            pdf.ln(4)
            pdf.set_font("Korean", "B", 13)
            pdf.set_text_color(60, 60, 60)
            pdf.multi_cell(0, 8, line[4:])
            pdf.ln(2)
        elif line.startswith("## "):
            pdf.ln(6)
            pdf.set_font("Korean", "B", 15)
            pdf.set_text_color(40, 40, 40)
            pdf.multi_cell(0, 9, line[3:])
            pdf.ln(3)
        elif line.startswith("# "):
            pdf.ln(6)
            pdf.set_font("Korean", "B", 18)
            pdf.set_text_color(30, 30, 30)
            pdf.multi_cell(0, 10, line[2:])
            pdf.ln(4)
        elif line.startswith("- ") or line.startswith("* "):
            pdf.set_font("Korean", "", 11)
            pdf.set_text_color(50, 50, 50)
            pdf.multi_cell(0, 7, "    " + line[2:])
        elif re.match(r"^\d+\.", line):
            pdf.set_font("Korean", "", 11)
            pdf.set_text_color(50, 50, 50)
            pdf.multi_cell(0, 7, line)
        elif line.startswith("---"):
            pdf.ln(3)
            pdf.set_draw_color(220, 220, 220)
            pdf.line(30, pdf.get_y(), 180, pdf.get_y())
            pdf.ln(5)
        elif line.strip() == "":
            pdf.ln(4)
        else:
            pdf.set_font("Korean", "", 11)
            pdf.set_text_color(50, 50, 50)
            pdf.multi_cell(0, 7, line)

    pdf.ln(10)
    pdf.set_draw_color(200, 200, 200)
    pdf.line(20, pdf.get_y(), 190, pdf.get_y())
    pdf.ln(5)
    pdf.set_font("Korean", "B", 10)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 8, "Dream_Grow  @dream_grow_lee", align="C")
    pdf.ln(5)
    pdf.set_font("Korean", "", 9)
    pdf.cell(0, 6, "아이와 부모의 꿈을 키웁니다.", align="C")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    pdf.output(output_path)
    return output_path


def update_frontmatter_pdf(filepath: str, pdf_path: str, drive_path: str = ""):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    if "pdf경로:" not in content:
        content = content.replace("---\n\n", f"pdf경로: {pdf_path}\n---\n\n", 1)
    if drive_path and "drive경로:" not in content:
        content = content.replace("pdf경로:", f"drive경로: {drive_path}\npdf경로:", 1)
    if "상태:" in content:
        content = re.sub(r"상태:\s*확정", "상태: PDF완료", content)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)


def find_confirmed_magnets() -> list:
    if not os.path.isdir(MAGNET_DIR):
        return []
    magnets = []
    for fname in os.listdir(MAGNET_DIR):
        if not fname.endswith(".md"):
            continue
        filepath = os.path.join(MAGNET_DIR, fname)
        fm = parse_frontmatter(filepath)
        if fm.get("상태") == "확정":
            magnets.append(fm)
    return magnets


def process_magnet(fm: dict, dry_run: bool = False) -> bool:
    filepath = fm["_filepath"]
    filename = fm["_filename"]
    pdf_name = filename.replace(".md", ".pdf")

    print(f"  변환: {filename}")

    if dry_run:
        print(f"    [DRY] PDF: {pdf_name}")
        print(f"    [DRY] Drive: {GDRIVE_DIR}/{pdf_name}")
        return True

    pdf_path = os.path.join(PDF_OUTPUT_DIR, pdf_name)
    md_to_pdf(filepath, pdf_path)
    print(f"    PDF 생성: {pdf_path}")

    drive_path = ""
    if os.path.isdir(os.path.dirname(GDRIVE_DIR)):
        os.makedirs(GDRIVE_DIR, exist_ok=True)
        drive_dest = os.path.join(GDRIVE_DIR, pdf_name)
        shutil.copy2(pdf_path, drive_dest)
        drive_path = drive_dest
        print(f"    Drive 전송: {drive_dest}")
    else:
        print(f"    Drive 폴더 미연결 (수동 업로드 필요)")

    update_frontmatter_pdf(filepath, pdf_path, drive_path)
    return True


def list_status():
    if not os.path.isdir(MAGNET_DIR):
        print("09 리드마그넷/ 폴더가 없습니다.")
        return

    files = [f for f in os.listdir(MAGNET_DIR) if f.endswith(".md")]
    statuses = {}
    for fname in files:
        fm = parse_frontmatter(os.path.join(MAGNET_DIR, fname))
        status = fm.get("상태", "미지정")
        statuses.setdefault(status, []).append(fname)

    print(f"\n--- 리드마그넷 현황 ({len(files)}개) ---\n")
    for status, fnames in sorted(statuses.items()):
        print(f"  {status}: {len(fnames)}개")
        for fn in fnames[:3]:
            print(f"    - {fn}")
        if len(fnames) > 3:
            print(f"    ... 외 {len(fnames) - 3}개")


def main():
    if "--list" in sys.argv:
        list_status()
        return

    dry_run = "--dry-run" in sys.argv

    if "--file" in sys.argv:
        idx = sys.argv.index("--file")
        if idx + 1 < len(sys.argv):
            filepath = sys.argv[idx + 1]
            if not os.path.exists(filepath):
                filepath = os.path.join(MAGNET_DIR, filepath)
            if os.path.exists(filepath):
                fm = parse_frontmatter(filepath)
                process_magnet(fm, dry_run=dry_run)
            else:
                print(f"파일 없음: {sys.argv[idx + 1]}")
        return

    magnets = find_confirmed_magnets()
    print(f"[{datetime.now().strftime('%H:%M')}] 리드마그넷 PDF 변환")
    if not magnets:
        print("  확정 상태 리드마그넷이 없습니다.")
        print("  팁: 09 리드마그넷/ 파일의 frontmatter에서 '상태: 확정'으로 변경하세요.")
        return

    print(f"  대상: {len(magnets)}개\n")
    success = 0
    for fm in magnets:
        if process_magnet(fm, dry_run=dry_run):
            success += 1

    print(f"\n완료: {success}/{len(magnets)}개 변환")


if __name__ == "__main__":
    main()
