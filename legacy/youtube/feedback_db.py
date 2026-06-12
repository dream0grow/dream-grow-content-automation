"""로컬 JSON 기반 피드백 DB (Honcho 대체).

Honcho는 '사용자 개인 문체'가 드러나는 채널(Dream_Grow)에만 사용.
YouTube 자동화는 완전 AI 생성이므로 독립된 로컬 DB로 학습 패턴을 관리한다.

저장 내용:
- 잘 된 영상의 패턴 (제목, 훅, 구조, CTR 상위)
- 안 된 영상의 패턴 (하위)
- 다음 생성 시 system prompt에 주입되는 "learned patterns"
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from . import config


def _load() -> dict[str, Any]:
    if not config.FEEDBACK_DB_PATH.exists():
        return {
            "version": 1,
            "updated_at": "",
            "top_performers": [],
            "bottom_performers": [],
            "learned_patterns": {
                "good_hooks": [],
                "good_title_patterns": [],
                "bad_patterns": [],
                "topic_performance": {},
            },
            "history": [],
        }
    return json.loads(config.FEEDBACK_DB_PATH.read_text(encoding="utf-8"))


def _save(db: dict[str, Any]) -> None:
    db["updated_at"] = datetime.now().isoformat()
    config.FEEDBACK_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.FEEDBACK_DB_PATH.write_text(
        json.dumps(db, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def record_upload(video_id: str, title: str, topic: str, script_path: str) -> None:
    """영상 업로드 시 기록."""
    db = _load()
    db["history"].append(
        {
            "video_id": video_id,
            "title": title,
            "topic": topic,
            "script_path": script_path,
            "uploaded_at": datetime.now().isoformat(),
        }
    )
    _save(db)


def update_metrics(video_id: str, metrics: dict[str, Any]) -> None:
    """영상 성과 메트릭을 기존 history 항목에 병합."""
    db = _load()
    for entry in db["history"]:
        if entry.get("video_id") == video_id:
            entry["metrics"] = metrics
            entry["metrics_updated_at"] = datetime.now().isoformat()
            break
    _save(db)


def update_learned_patterns(patterns: dict[str, Any]) -> None:
    """analytics가 분석한 패턴을 learned_patterns에 병합."""
    db = _load()
    lp = db["learned_patterns"]
    for key in ("good_hooks", "good_title_patterns", "bad_patterns"):
        new_items = patterns.get(key) or []
        if new_items:
            # 중복 제거하면서 최신 우선
            existing = lp.get(key, [])
            merged = new_items + [x for x in existing if x not in new_items]
            lp[key] = merged[:30]  # 최대 30개 유지
    if "topic_performance" in patterns:
        lp["topic_performance"].update(patterns["topic_performance"])
    _save(db)


def get_generation_context() -> str:
    """원고 생성 시 system prompt에 주입할 학습 컨텍스트 문자열.

    비어 있으면 빈 문자열 반환 (첫 실행 시).
    """
    db = _load()
    lp = db["learned_patterns"]

    parts: list[str] = []
    if lp.get("good_hooks"):
        parts.append(
            "[성과가 좋았던 훅 패턴]\n"
            + "\n".join(f"- {h}" for h in lp["good_hooks"][:5])
        )
    if lp.get("good_title_patterns"):
        parts.append(
            "[성과가 좋았던 제목 패턴]\n"
            + "\n".join(f"- {t}" for t in lp["good_title_patterns"][:5])
        )
    if lp.get("bad_patterns"):
        parts.append(
            "[피해야 할 패턴]\n"
            + "\n".join(f"- {b}" for b in lp["bad_patterns"][:5])
        )
    if lp.get("topic_performance"):
        top_topics = sorted(
            lp["topic_performance"].items(),
            key=lambda kv: kv[1].get("avg_ctr", 0),
            reverse=True,
        )[:5]
        if top_topics:
            parts.append(
                "[성과 좋은 주제 분야]\n"
                + "\n".join(f"- {k}: CTR {v.get('avg_ctr', 0):.1%}" for k, v in top_topics)
            )

    if not parts:
        return ""
    return "\n\n=== 이전 영상 학습 데이터 ===\n" + "\n\n".join(parts) + "\n==========================\n"


def get_top_videos(n: int = 3) -> list[dict[str, Any]]:
    db = _load()
    with_metrics = [e for e in db["history"] if e.get("metrics")]
    return sorted(
        with_metrics,
        key=lambda e: e.get("metrics", {}).get("ctr", 0),
        reverse=True,
    )[:n]


def get_bottom_videos(n: int = 3) -> list[dict[str, Any]]:
    db = _load()
    with_metrics = [e for e in db["history"] if e.get("metrics")]
    return sorted(
        with_metrics,
        key=lambda e: e.get("metrics", {}).get("ctr", 0),
    )[:n]
