"""텔레그램 알림 — 서버 없이 GitHub Actions에서 sendMessage만 쏜다

봇 상시 프로세스(버튼 결재·음성 수신)는 Phase B(옛 노트북)에서. 여기서는
"확인할 것이 생겼다"는 사실을 폰으로 밀어주는 것까지만 한다 — 사용자 확정
요구 1순위(발행 직전 알림)의 서버리스 구현.

필요 환경변수: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (GitHub Secrets)
미설정이면 조용히 건너뛴다 (파이프라인을 죽이지 않는다).
"""
import os

import requests


def send(text: str) -> bool:
    """텔레그램으로 메시지 발송. 성공 여부 반환 (실패해도 예외 없음)."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return False
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text[:4000],
                  "disable_web_page_preview": True},
            timeout=15,
        )
        return resp.ok
    except requests.RequestException:
        return False


MAX_TITLES_PER_KIND = 5      # 녹음당 종류별 제목 표시 상한 (폰 화면 보호)


def _detail_block(detail: dict) -> list[str]:
    """녹음 1건의 산출물 제목을 메시지 줄들로 만든다."""
    lines = [f"\n📼 {detail.get('녹음', '')}"]
    for kind, icon in (("메모", "·"), ("키워드", "🔑"), ("의견", "💬")):
        titles = [t for t in detail.get(kind) or [] if t]
        if not titles:
            continue
        if kind == "메모":          # 메모 제목이 곧 핵심 내용 — 줄 단위로
            lines += [f"  · {t}" for t in titles[:MAX_TITLES_PER_KIND]]
            if len(titles) > MAX_TITLES_PER_KIND:
                lines.append(f"  · … 외 {len(titles) - MAX_TITLES_PER_KIND}건")
        else:                       # 키워드/의견은 한 줄 요약
            shown = ", ".join(titles[:MAX_TITLES_PER_KIND])
            more = (f" 외 {len(titles) - MAX_TITLES_PER_KIND}건"
                    if len(titles) > MAX_TITLES_PER_KIND else "")
            lines.append(f"  {icon} {kind}: {shown}{more}")
    return lines


def briefing(drafts: list[str], yellows: int, cases: int, memos: int,
             failures: int, pending: int = 0,
             details: list[dict] | None = None) -> str:
    """파이프라인 실행 결과 요약 메시지를 만든다."""
    lines = ["🌙 플라우드 파이프라인 결과"]
    if drafts:
        lines.append(f"\n✍️ 교사그룹 초안 {len(drafts)}건 — 리뷰대기"
                     " (vault/프로젝트/교육운동)")
        lines += [f"  · {t}" for t in drafts[:5]]
    if yellows:
        lines.append(f"📋 사례 노랑 결재 대기 {yellows}건")
    if cases or memos:
        lines.append(f"🧠 자동 입고: 사례 {cases}건, 메모 {memos}건")
    for detail in details or []:
        lines += _detail_block(detail)
    if failures:
        lines.append(f"⚠️ 처리 실패 {failures}건 — Actions 로그 확인")
    if pending:
        lines.append(f"⏳ 전사 대기 {pending}건 — 플라우드 앱에서 전사를 돌리면 "
                     "다음 실행에 자동 처리")
    if len(lines) == 1:
        lines.append("새로 처리한 녹음 없음")
    lines.append("\n🗂 저장: 옵시디언 vault/제텔카스텐 (1.메모 · 2.키워드 · 3.의견)"
                 " → 발행은 대시보드/복붙")
    return "\n".join(lines)
