#!/usr/bin/env python3
"""
네이버 금융 시황정보 리포트 자동 수집 및 분석 스크립트
매일 당일 날짜의 리포트를 수집하고, PDF 텍스트를 추출하여 AI로 분석합니다.
"""

import os
import sys
import json
import time
import logging
import requests
import pdfplumber
from datetime import datetime, date
from pathlib import Path
from bs4 import BeautifulSoup
from openai import OpenAI

# ── 경로 설정 ──────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
REPORTS_DIR = BASE_DIR / "reports"
SUMMARIES_DIR = BASE_DIR / "summaries"
LOGS_DIR = BASE_DIR / "logs"

for d in [REPORTS_DIR, SUMMARIES_DIR, LOGS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── 로깅 설정 ──────────────────────────────────────────────
today_str = date.today().strftime("%Y%m%d")
log_file = LOGS_DIR / f"{today_str}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# ── OpenAI 클라이언트 ──────────────────────────────────────
client = OpenAI()
MODEL = "gpt-5-mini"

# ── 네이버 금융 설정 ───────────────────────────────────────
NAVER_BASE = "https://finance.naver.com/research"
LIST_URL = f"{NAVER_BASE}/market_info_list.naver"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://finance.naver.com/research/",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
}

MAX_PAGES = 3          # 수집할 최대 페이지 수
MAX_REPORTS = 30       # 분석할 최대 리포트 수
PDF_TIMEOUT = 30       # PDF 다운로드 타임아웃(초)
MAX_TEXT_PER_PDF = 4000  # PDF당 최대 추출 텍스트 길이


# ─────────────────────────────────────────────────────────────
# 1. 리포트 목록 수집
# ─────────────────────────────────────────────────────────────

def get_today_date_str():
    """네이버 금융 날짜 형식(YY.MM.DD)으로 오늘 날짜 반환"""
    return date.today().strftime("%y.%m.%d")


def fetch_report_list(target_date: str, max_pages: int = MAX_PAGES) -> list[dict]:
    """
    네이버 금융 시황정보 리포트 목록에서 target_date에 해당하는 리포트를 수집합니다.
    target_date 형식: 'YY.MM.DD' (예: '26.06.30')
    """
    reports = []
    seen_nids = set()

    for page in range(1, max_pages + 1):
        url = f"{LIST_URL}?page={page}"
        logger.info(f"페이지 {page} 수집 중: {url}")

        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"페이지 {page} 요청 실패: {e}")
            break

        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table", class_="type_1")
        if not table:
            logger.warning(f"페이지 {page}에서 테이블을 찾을 수 없음")
            break

        rows = table.find_all("tr")
        found_today = False
        found_older = False

        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 4:
                continue

            title_cell = cells[0]
            firm_cell = cells[1]
            attach_cell = cells[2]
            date_cell = cells[3]

            title_link = title_cell.find(
                "a", href=lambda h: h and "market_info_read" in h
            )
            if not title_link:
                continue

            row_date = date_cell.get_text(strip=True)

            # 오늘 날짜보다 이전이면 수집 중단
            if row_date < target_date:
                found_older = True
                break

            if row_date != target_date:
                continue

            found_today = True
            nid = ""
            href = title_link.get("href", "")
            if "nid=" in href:
                nid = href.split("nid=")[1].split("&")[0]

            if nid in seen_nids:
                continue
            seen_nids.add(nid)

            # PDF 링크 추출 (셀[2]에 위치)
            pdf_link = attach_cell.find(
                "a", href=lambda h: h and ".pdf" in h.lower()
            )
            pdf_url = pdf_link["href"] if pdf_link else None

            reports.append(
                {
                    "nid": nid,
                    "title": title_link.get_text(strip=True),
                    "firm": firm_cell.get_text(strip=True),
                    "date": row_date,
                    "pdf_url": pdf_url,
                    "detail_url": f"{NAVER_BASE}/{href}",
                }
            )

        if found_older:
            logger.info(f"페이지 {page}에서 이전 날짜 데이터 발견, 수집 종료")
            break

        if not found_today and page > 1:
            logger.info(f"페이지 {page}에서 오늘 날짜 데이터 없음")
            break

        time.sleep(0.5)

    logger.info(f"총 {len(reports)}개 리포트 목록 수집 완료 (날짜: {target_date})")
    return reports[:MAX_REPORTS]


# ─────────────────────────────────────────────────────────────
# 2. PDF 다운로드 및 텍스트 추출
# ─────────────────────────────────────────────────────────────

def download_and_extract_pdf(report: dict, save_dir: Path) -> str | None:
    """PDF를 다운로드하고 텍스트를 추출합니다."""
    pdf_url = report.get("pdf_url")
    if not pdf_url:
        return None

    nid = report["nid"]
    pdf_path = save_dir / f"{nid}.pdf"

    # 이미 다운로드된 경우 재사용
    if not pdf_path.exists():
        try:
            resp = requests.get(
                pdf_url, headers=HEADERS, timeout=PDF_TIMEOUT, stream=True
            )
            resp.raise_for_status()
            with open(pdf_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            logger.info(f"PDF 다운로드 완료: {pdf_path.name}")
        except Exception as e:
            logger.warning(f"PDF 다운로드 실패 ({report['title'][:30]}): {e}")
            return None

    # 텍스트 추출
    try:
        text_parts = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text.strip())

        full_text = "\n\n".join(text_parts)
        # Compliance Notice 이후 내용 제거 (법적 고지문)
        if "Compliance Notice" in full_text:
            full_text = full_text.split("Compliance Notice")[0].strip()
        if "본 조사분석자료는" in full_text:
            full_text = full_text.split("본 조사분석자료는")[0].strip()

        return full_text[:MAX_TEXT_PER_PDF] if full_text else None
    except Exception as e:
        logger.warning(f"PDF 텍스트 추출 실패 ({report['title'][:30]}): {e}")
        return None


# ─────────────────────────────────────────────────────────────
# 3. AI 분석
# ─────────────────────────────────────────────────────────────

def analyze_reports_with_ai(reports_with_text: list[dict], target_date: str) -> str:
    """
    수집된 리포트 텍스트를 AI로 분석하여 핵심 요약을 생성합니다.
    """
    if not reports_with_text:
        return "분석할 리포트가 없습니다."

    # 리포트 텍스트 조합
    report_blocks = []
    for i, r in enumerate(reports_with_text, 1):
        text = r.get("text", "")
        if not text:
            continue
        block = (
            f"[리포트 {i}]\n"
            f"제목: {r['title']}\n"
            f"증권사: {r['firm']}\n"
            f"내용:\n{text}\n"
        )
        report_blocks.append(block)

    if not report_blocks:
        return "PDF 텍스트를 추출할 수 있는 리포트가 없습니다."

    combined = "\n" + "=" * 60 + "\n"
    combined = combined.join(report_blocks)

    # 전체 텍스트가 너무 길면 잘라냄
    MAX_TOTAL = 80000
    if len(combined) > MAX_TOTAL:
        combined = combined[:MAX_TOTAL] + "\n...(이하 생략)"

    prompt = f"""당신은 국내 주식시장 전문 애널리스트입니다.
아래는 {target_date} 날짜의 주요 증권사 시황정보 리포트들입니다.

다음 두 가지 항목으로 분석해 주세요.

1. 공통 핵심 내용 (여러 리포트에서 공통으로 언급된 주제, 시장 전망, 주요 이슈)
   - 공통으로 언급된 거시경제 이슈
   - 공통으로 언급된 국내외 증시 흐름
   - 공통으로 언급된 주요 섹터 또는 종목 동향

2. 개별 리포트에서만 언급된 투자에 유용한 정보 (다른 리포트에는 없지만 알면 좋을 독자적 인사이트)
   - 특정 증권사만의 독자적 시각 또는 분석
   - 특정 섹터/테마에 대한 심층 분석
   - 주목할 만한 데이터 또는 통계

각 항목은 간결하고 명확하게 작성하되, 실제 투자 판단에 참고할 수 있도록 구체적으로 서술해 주세요.
한국어로 작성하고, 마크다운 형식을 사용하지 마세요. 굵게 표시도 사용하지 마세요.

리포트 내용:
{combined}
"""

    logger.info(f"AI 분석 시작 (모델: {MODEL}, 리포트 수: {len(report_blocks)})")
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=8000,
            temperature=0.3,
        )
        result = response.choices[0].message.content
        logger.info("AI 분석 완료")
        return result
    except Exception as e:
        logger.error(f"AI 분석 실패: {e}")
        return f"AI 분석 중 오류가 발생했습니다: {e}"


# ─────────────────────────────────────────────────────────────
# 4. 결과 저장
# ─────────────────────────────────────────────────────────────

def save_summary(
    target_date: str,
    reports: list[dict],
    analysis: str,
    save_dir: Path,
) -> Path:
    """분석 결과를 마크다운 파일로 저장합니다."""
    # 파일명용 날짜 (YYYYMMDD)
    date_for_file = "20" + target_date.replace(".", "")
    output_path = save_dir / f"{date_for_file}_market_report.md"

    # 리포트 목록 구성
    report_list_lines = []
    for i, r in enumerate(reports, 1):
        pdf_mark = "(PDF 있음)" if r.get("pdf_url") else "(PDF 없음)"
        report_list_lines.append(
            f"{i}. [{r['firm']}] {r['title']} {pdf_mark}"
        )
    report_list_str = "\n".join(report_list_lines)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    content = f"""날짜: {target_date}
생성 시각: {now_str}
수집 리포트 수: {len(reports)}개

수집된 리포트 목록
{report_list_str}

{'=' * 60}

분석 결과

{analysis}

{'=' * 60}
본 분석은 AI가 자동으로 생성한 참고 자료입니다.
투자 판단의 최종 책임은 투자자 본인에게 있습니다.
"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    logger.info(f"분석 결과 저장 완료: {output_path}")
    return output_path


def save_metadata(target_date: str, reports: list[dict], save_dir: Path):
    """수집된 리포트 메타데이터를 JSON으로 저장합니다."""
    date_for_file = "20" + target_date.replace(".", "")
    meta_path = save_dir / f"{date_for_file}_metadata.json"

    # text 필드는 JSON에 저장하지 않음 (용량 절약)
    meta = [
        {k: v for k, v in r.items() if k != "text"}
        for r in reports
    ]
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    logger.info(f"메타데이터 저장 완료: {meta_path}")


# ─────────────────────────────────────────────────────────────
# 5. 메인 실행
# ─────────────────────────────────────────────────────────────

def main(target_date: str | None = None):
    if target_date is None:
        target_date = get_today_date_str()

    logger.info(f"{'=' * 60}")
    logger.info(f"네이버 금융 시황정보 리포트 수집 시작")
    logger.info(f"대상 날짜: {target_date}")
    logger.info(f"{'=' * 60}")

    # 날짜별 PDF 저장 디렉토리
    date_for_dir = "20" + target_date.replace(".", "")
    pdf_dir = REPORTS_DIR / date_for_dir
    pdf_dir.mkdir(parents=True, exist_ok=True)

    # 1단계: 리포트 목록 수집
    reports = fetch_report_list(target_date)

    if not reports:
        logger.warning(f"{target_date} 날짜의 리포트를 찾을 수 없습니다.")
        # 빈 결과 저장
        save_summary(target_date, [], "해당 날짜의 리포트가 없습니다.", SUMMARIES_DIR)
        return

    # 2단계: PDF 다운로드 및 텍스트 추출
    logger.info(f"PDF 다운로드 및 텍스트 추출 시작 ({len(reports)}개)")
    reports_with_text = []
    pdf_count = 0

    for report in reports:
        text = download_and_extract_pdf(report, pdf_dir)
        report["text"] = text
        reports_with_text.append(report)
        if text:
            pdf_count += 1
        time.sleep(0.3)

    logger.info(f"텍스트 추출 완료: {pdf_count}/{len(reports)}개 PDF 처리")

    # 3단계: AI 분석
    # PDF가 없는 리포트도 제목+증권사 정보로 목록에 포함
    analysis = analyze_reports_with_ai(reports_with_text, target_date)

    # 4단계: 결과 저장
    output_path = save_summary(target_date, reports, analysis, SUMMARIES_DIR)
    save_metadata(target_date, reports, SUMMARIES_DIR)

    logger.info(f"{'=' * 60}")
    logger.info(f"모든 작업 완료. 결과 파일: {output_path}")
    logger.info(f"{'=' * 60}")

    return output_path


if __name__ == "__main__":
    # 커맨드라인 인수로 날짜 지정 가능 (예: python collect_and_analyze.py 26.06.30)
    target = sys.argv[1] if len(sys.argv) > 1 else None
    main(target)
