"""표지 사진 심사 - 후보 사진이 표지로 쓸 만한지 '보고' 판단한다.

카드뉴스 표지는 스크롤을 멈추는 후킹이 생명이므로, 스톡에서 가져온 실물 사진이
(1) 후킹 (2) 타겟 학부모의 공감 (3) 내용과의 어울림 을 만족하는지 비전으로 심사한다.
통과하면 그 사진을 쓰고, 아니면 새로 생성한다(cardnews.resolve_cover_photo에서 사용).

비전 심사는 ANTHROPIC_API_KEY가 있을 때만 동작. 없으면 judge()가 None(판단 불가)을
반환하고, 호출부는 '확인 불가 → 표지는 생성' 정책으로 안전하게 간다.
"""
import base64
import json
import mimetypes
import os
import re
import urllib.request
from pathlib import Path

API_URL = "https://api.anthropic.com/v1/messages"
JUDGE_MODEL = os.getenv("DG_JUDGE_MODEL", "claude-sonnet-5")
# 세 기준 평균이 이 값 이상이면 통과
PASS_THRESHOLD = float(os.getenv("DG_PHOTO_PASS_THRESHOLD", "0.62"))


def available() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY", "").strip())


def judge(image_path: str, context: str) -> dict | None:
    """표지 후보 사진을 심사한다.

    반환: {"ok": bool, "hook": float, "empathy": float, "fit": float,
           "score": float, "reason": str}  또는 None(심사 불가).
    """
    if not available() or not image_path or not Path(image_path).exists():
        return None
    try:
        raw = Path(image_path).read_bytes()
        mime = mimetypes.guess_type(image_path)[0] or "image/jpeg"
        b64 = base64.b64encode(raw).decode()
        prompt = (
            "너는 초등 학부모 대상 카드뉴스의 아트디렉터다. 이 사진을 '표지'로 쓴다고 할 때 "
            "세 기준을 0~1로 냉정하게 채점해라.\n"
            f"- 내용 맥락: {context[:400]}\n"
            "기준:\n"
            "1) hook: 피드에서 스크롤을 멈추게 하는 힘\n"
            "2) empathy: 타겟 학부모가 '내 얘기다' 느낄 공감\n"
            "3) fit: 위 내용 맥락과의 어울림(한국인/상황 일치 포함)\n"
            "관대하게 주지 마라. 어색한 스톡 느낌·외국인·주제 불일치는 감점.\n"
            'JSON만 출력: {"hook":0~1,"empathy":0~1,"fit":0~1,"reason":"한 줄"}'
        )
        body = {
            "model": JUDGE_MODEL,
            "max_tokens": 400,
            "messages": [{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": mime, "data": b64}},
                {"type": "text", "text": prompt},
            ]}],
        }
        req = urllib.request.Request(
            API_URL, data=json.dumps(body).encode(),
            headers={"x-api-key": os.getenv("ANTHROPIC_API_KEY"),
                     "anthropic-version": "2023-06-01", "content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return None
        v = json.loads(m.group(0))
        hook, emp, fit = float(v.get("hook", 0)), float(v.get("empathy", 0)), float(v.get("fit", 0))
        score = round((hook + emp + fit) / 3, 3)
        return {"ok": score >= PASS_THRESHOLD, "hook": hook, "empathy": emp,
                "fit": fit, "score": score, "reason": v.get("reason", "")}
    except Exception as e:
        print(f"[photo_judge] 심사 실패: {type(e).__name__}: {e}", flush=True)
        return None
