"""텔레그램 알림 — 서버 없이 GitHub Actions에서 sendMessage만 쏜다

봇 상시 프로세스(버튼 결재·음성 수신)는 Phase B(옛 노트북)에서. 여기서는
"확인할 것이 생겼다"는 사실을 폰으로 밀어주는 것까지만 한다 — 사용자 확정
요구 1순위(발행 직전 알림)의 서버리스 구현.

briefing()은 텔레그램 HTML 모드 메시지를 만든다 — 산출물 제목이
GitHub의 해당 노트 파일로 열리는 링크가 된다 (경로가 없으면 평문).
호출부는 send(msg, html=True)로 보내야 링크가 살아난다.

필요 환경변수: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (GitHub Secrets)
미설정이면 조용히 건너뛴다 (파이프라인을 죽이지 않는다).
"""
import html as _html
import os
from urllib.parse import quote

import requests


def send(text: str, html: bool = False) -> bool:
    """텔레그램으로 메시지 발송. 성공 여부 반환 (실패해도 예외 없음)."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return False
    if len(text) > 4000:
        # HTML 태그 중간이 잘리지 않도록 마지막 줄바꿈에서 자른다
        cut = text.rfind("\n", 0, 4000)
        text = text[:cut if cut > 0 else 4000]
    payload = {"chat_id": chat_id, "text": text,
               "disable_web_page_preview": True}
    if html:
        payload["parse_mode"] = "HTML"
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json=payload,
            timeout=15,
        )
        if html and not resp.ok:
            # HTML 파싱 오류 등으로 거절되면 평문으로 1회 재시도 (알림 유실 방지)
            payload.pop("parse_mode", None)
            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json=payload,
                timeout=15,
            )
        return resp.ok
    except requests.RequestException:
        return False


MAX_TITLES_PER_KIND = 5      # 녹음당 종류별 제목 표시 상한 (폰 화면 보호)


def note_url(relpath: str) -> str:
    """볼트 상대 경로 → GitHub에서 바로 읽히는 blob URL."""
    repo = os.getenv("GITHUB_REPOSITORY", "dream0grow/dream-grow-content-automation")
    branch = os.getenv("GITHUB_REF_NAME", "main")
    return (f"https://github.com/{repo}/blob/{quote(branch)}/vault/"
            + quote(relpath))


def _render(entry) -> str:
    """제목 1건을 HTML로. entry가 {'제목','경로'} dict면 링크, 문자열이면 평문."""
    if isinstance(entry, dict):
        title = _html.escape(str(entry.get("제목", "")))
        path = str(entry.get("경로", "")).strip()
        if path:
            return f'<a href="{note_url(path)}">{title}</a>'
        return title
    return _html.escape(str(entry))


def _detail_block(detail: dict) -> list[str]:
    """녹음 1건의 산출물 제목을 메시지 줄들로 만든다."""
    lines = [f"\n📼 {_html.escape(str(detail.get('녹음', '')))}"]
    for kind, icon in (("메모", "·"), ("키워드", "🔑"), ("의견", "💬")):
        entries = [e for e in detail.get(kind) or []
                   if (e.get("제목") if isinstance(e, dict) else e)]
        if not entries:
            continue
        if kind == "메모":          # 메모 제목이 곧 핵심 내용 — 줄 단위로
            lines += [f"  · {_render(e)}" for e in entries[:MAX_TITLES_PER_KIND]]
            if len(entries) > MAX_TITLES_PER_KIND:
                lines.append(f"  · … 외 {len(entries) - MAX_TITLES_PER_KIND}건")
        else:                       # 키워드/의견은 한 줄 요약
            shown = ", ".join(_render(e) for e in entries[:MAX_TITLES_PER_KIND])
            more = (f" 외 {len(entries) - MAX_TITLES_PER_KIND}건"
                    if len(entries) > MAX_TITLES_PER_KIND else "")
            lines.append(f"  {icon} {kind}: {shown}{more}")
    return lines


def briefing(drafts: list[str], yellows: int, cases: int, memos: int,
             failures: int, pending: int = 0,
             details: list[dict] | None = None) -> str:
    """파이프라인 실행 결과 요약 메시지(텔레그램 HTML)를 만든다."""
    lines = ["🌙 플라우드 파이프라인 결과"]
    if drafts:
        lines.append(f"\n✍️ 교사그룹 초안 {len(drafts)}건 — 리뷰대기"
                     " (vault/프로젝트/교육운동)")
        lines += [f"  · {_render(t)}" for t in drafts[:5]]
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
                 " → 발행은 대시보드/복붙"
                 "\n(링크는 볼트 push 완료 후 열립니다 — 발송 1분 안팎)")
    return "\n".join(lines)
