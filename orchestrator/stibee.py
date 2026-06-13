"""스티비(Stibee) 뉴스레터 자동 발행 - Maily 대체

스티비 API v2는 이메일 생성·발송을 지원한다 (Maily는 조회만 가능).
Base URL: https://api.stibee.com/v2, 인증: AccessToken 헤더.
2025-01-21 이후 발급된 API 키만 사용 가능하다.

필요 Secret:
  STIBEE_API_KEY  - 워크스페이스 설정 → API 키에서 발급
  STIBEE_LIST_ID  - 주소록 ID (주소록 페이지 URL의 숫자)

주의: 이메일 생성 payload 필드명은 스티비 공식 문서
(https://stibeev2.apidocumentation.com/docs) 기준으로 작성했으나,
첫 실행에서 4xx 응답이 나면 응답 본문이 카드에 기록되므로 그걸 보고 조정한다.
실패해도 파이프라인은 멈추지 않고 수동 붙여넣기 안내로 폴백한다.
"""
import html
import os
import re

import requests

BASE_URL = "https://api.stibee.com/v2"
API_KEY = os.getenv("STIBEE_API_KEY", "")
LIST_ID = os.getenv("STIBEE_LIST_ID", "")
# 발신자: 스티비에 사전 인증된 발신 이메일이어야 한다 (워크스페이스 설정 → 발신자 관리)
# .strip(): Secret에 실수로 들어간 앞뒤 공백/개행 제거
SENDER_EMAIL = os.getenv("STIBEE_SENDER_EMAIL", "").strip()
SENDER_NAME = os.getenv("STIBEE_SENDER_NAME", "").strip() or "드림그로우"
# 안전장치: 기본은 스티비에 '초안만 생성'하고 발송은 사람이 확인 후. true일 때만 자동 발송.
AUTO_SEND = os.getenv("STIBEE_AUTO_SEND", "").lower() in ("1", "true", "yes", "on")


def available() -> bool:
    return bool(API_KEY and LIST_ID)


def _headers() -> dict:
    return {"AccessToken": API_KEY, "Content-Type": "application/json"}


def markdown_to_html(text: str) -> str:
    """초안 Markdown을 이메일용 단순 HTML로 변환한다."""
    blocks = []
    for para in text.strip().split("\n\n"):
        para = para.strip()
        if not para:
            continue
        if para.startswith("### "):
            blocks.append(f"<h3>{html.escape(para[4:])}</h3>")
        elif para.startswith("## "):
            blocks.append(f"<h2>{html.escape(para[3:])}</h2>")
        elif para.startswith("# "):
            blocks.append(f"<h1>{html.escape(para[2:])}</h1>")
        else:
            escaped = html.escape(para).replace("\n", "<br>")
            escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
            blocks.append(f'<p style="line-height:1.7">{escaped}</p>')
    return (
        '<div style="max-width:640px;margin:0 auto;font-size:16px;color:#222">'
        + "\n".join(blocks) + "</div>"
    )


def extract_subject(draft: str) -> str:
    """초안 첫 제목 줄을 메일 제목으로 쓴다."""
    for line in draft.strip().split("\n"):
        line = line.strip().lstrip("#").strip()
        if line:
            return line[:80]
    return "드림그로우 뉴스레터"


def create_and_send(draft: str, subject: str = "") -> dict:
    """뉴스레터 이메일을 생성하고 발송한다.

    Returns: {"email_id": ..., "sent": bool, "detail": str}
    Raises: RuntimeError (응답 본문 포함 - 카드에 기록되어 payload 조정에 사용)
    """
    subject = subject or extract_subject(draft)
    content_html = markdown_to_html(draft)
    list_value = int(LIST_ID) if LIST_ID.isdigit() else LIST_ID

    # 스티비 공식 예시 기준: listId(단수), senderEmail, senderName. content는 본문용 추가 시도.
    body = {
        "subject": subject,
        "senderEmail": SENDER_EMAIL,
        "senderName": SENDER_NAME,
        "listId": list_value,
        "content": content_html,
    }
    create_resp = requests.post(
        f"{BASE_URL}/emails", headers=_headers(), json=body, timeout=60,
    )
    if create_resp.status_code >= 400:
        raise RuntimeError(
            f"스티비 이메일 생성 실패 {create_resp.status_code}: {create_resp.text[:500]}"
        )
    created = create_resp.json()
    email_id = (
        created.get("id")
        or (created.get("value") or {}).get("id")
        or (created.get("data") or {}).get("id")
    )
    if not email_id:
        raise RuntimeError(f"스티비 응답에서 email id를 찾지 못함: {create_resp.text[:500]}")

    # 안전 모드: 자동 발송이 꺼져 있으면 초안만 생성하고 멈춘다
    if not AUTO_SEND:
        return {
            "email_id": email_id,
            "sent": False,
            "detail": (
                f"스티비에 초안 생성 완료 (id={email_id}). 자동 발송은 꺼져 있습니다.\n"
                "스티비 대시보드에서 내용을 확인하고 직접 발송하세요. "
                "검증이 끝나 자동 발송을 켜려면 Secrets에 STIBEE_AUTO_SEND=true를 추가하세요."
            ),
        }

    send_resp = requests.post(
        f"{BASE_URL}/emails/{email_id}/send",
        headers=_headers(),
        json={},
        timeout=60,
    )
    if send_resp.status_code >= 400:
        return {
            "email_id": email_id,
            "sent": False,
            "detail": (
                f"이메일 생성은 성공(id={email_id}), 발송 호출 실패 "
                f"{send_resp.status_code}: {send_resp.text[:300]} "
                "- 스티비 대시보드에서 해당 이메일을 열어 수동 발송하세요."
            ),
        }
    return {"email_id": email_id, "sent": True, "detail": f"발송 완료 (id={email_id})"}
