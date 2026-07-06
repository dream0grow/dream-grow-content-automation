"""플라우드 녹음 조회 — 두 가지 소스를 지원한다

1) MCP 모드 (자동화): 공식 stdio MCP 서버(`npx -y @plaud-ai/mcp`)를 서브프로세스로
   띄우고 JSON-RPC로 도구를 호출한다. 인증은 로컬에서 1회 로그인해 만든
   `~/.plaud/tokens-mcp.json`을 GitHub Secret `PLAUD_TOKENS_JSON`으로 주입한다.
   (플라우드는 브라우저 OAuth라 CI에서 신규 로그인이 불가 — D-11 참고)

2) 인박스 모드 (무인증 폴백): `vault/수집함/plaud/*.md`에 넣어둔 전사 파일을 읽는다.
   대화형 세션(/plaud-zettel, claude.ai 커넥터)이나 사람이 직접 내보낸 전사를
   여기 두면 API 없이도 파이프라인 전체가 돈다. 처리 후 `처리됨/`으로 이동.

두 소스 모두 Recording(id, name, recorded, transcript)으로 정규화된다.
"""
import hashlib
import json
import os
import subprocess
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from vault_pipeline.vault_io import parse_frontmatter, now_kst, vault_root


def inbox_dir() -> Path:
    return vault_root() / "수집함" / "plaud"

MCP_COMMAND = os.getenv("PLAUD_MCP_COMMAND", "npx -y @plaud-ai/mcp@latest").split()
MCP_TIMEOUT = int(os.getenv("PLAUD_MCP_TIMEOUT", "120"))


class PlaudUnavailable(Exception):
    """플라우드 API를 쓸 수 없음 (미인증 등) — 인박스 모드만 동작."""


@dataclass
class Recording:
    id: str
    name: str
    recorded: str            # YYYY-MM-DD
    transcript: str
    source: str = "mcp"      # mcp | inbox
    inbox_path: Path | None = field(default=None, repr=False)


# ---------------------------------------------------------------- 인박스 모드

def fetch_inbox() -> list[Recording]:
    """수집함의 전사 md 파일을 읽는다. frontmatter의 plaud_id가 있으면 그것을,
    없으면 내용 해시를 id로 쓴다(같은 파일 재투입 시 중복 방지)."""
    if not inbox_dir().exists():
        return []
    recs = []
    for p in sorted(inbox_dir().glob("*.md")):
        text = p.read_text(encoding="utf-8", errors="ignore")
        meta, body = parse_frontmatter(text)
        if not body.strip():
            continue
        rec_id = str(meta.get("plaud_id", "")).strip()
        if not rec_id:
            rec_id = "inbox-" + hashlib.sha1(body.encode("utf-8")).hexdigest()[:12]
        recs.append(Recording(
            id=rec_id,
            name=str(meta.get("title", "") or p.stem),
            recorded=str(meta.get("recorded", "") or
                         datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d")),
            transcript=body.strip(),
            source="inbox",
            inbox_path=p,
        ))
    return recs


def archive_inbox_file(rec: Recording, dry_run: bool = False) -> None:
    if rec.inbox_path is None or dry_run:
        return
    done_dir = inbox_dir() / "처리됨"
    done_dir.mkdir(parents=True, exist_ok=True)
    rec.inbox_path.rename(done_dir / rec.inbox_path.name)


# ------------------------------------------------------------------ MCP 모드

def _bootstrap_tokens() -> bool:
    """Secret으로 받은 토큰을 MCP 서버가 읽는 위치에 놓는다. 성공 여부 반환."""
    token_path = Path.home() / ".plaud" / "tokens-mcp.json"
    if token_path.exists():
        return True
    raw = os.getenv("PLAUD_TOKENS_JSON", "").strip()
    if not raw:
        return False
    try:
        json.loads(raw)  # 형식 검증
    except json.JSONDecodeError:
        return False
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(raw, encoding="utf-8")
    token_path.chmod(0o600)
    return True


class _McpSession:
    """공식 플라우드 MCP 서버(stdio)와의 최소 JSON-RPC 세션."""

    def __init__(self):
        self.proc = subprocess.Popen(
            MCP_COMMAND, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
        )
        self._id = 0
        self._lock = threading.Lock()
        self._request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "dreamgrow-vault-pipeline", "version": "1.0"},
        })
        self._notify("notifications/initialized")

    def _send(self, payload: dict) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

    def _notify(self, method: str) -> None:
        self._send({"jsonrpc": "2.0", "method": method})

    def _request(self, method: str, params: dict) -> dict:
        with self._lock:
            self._id += 1
            req_id = self._id
            self._send({"jsonrpc": "2.0", "id": req_id, "method": method,
                        "params": params})
            result: dict = {}

            def read():
                assert self.proc.stdout is not None
                for line in self.proc.stdout:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if msg.get("id") == req_id:
                        result.update(msg)
                        return

            t = threading.Thread(target=read, daemon=True)
            t.start()
            t.join(MCP_TIMEOUT)
            if not result:
                raise PlaudUnavailable(f"MCP 응답 없음: {method} ({MCP_TIMEOUT}s)")
            if "error" in result:
                raise PlaudUnavailable(f"MCP 오류: {result['error'].get('message')}")
            return result.get("result", {})

    def call_tool(self, name: str, arguments: dict) -> str:
        res = self._request("tools/call", {"name": name, "arguments": arguments})
        parts = res.get("content", [])
        text = "\n".join(p.get("text", "") for p in parts if p.get("type") == "text")
        if res.get("isError"):
            raise PlaudUnavailable(f"플라우드 도구 오류({name}): {text[:200]}")
        return text

    def close(self) -> None:
        try:
            self.proc.terminate()
        except OSError:
            pass


def _extract_items(raw: str) -> list[dict]:
    """list_files 응답에서 녹음 목록을 관대하게 추출한다."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(data, list):
        return [d for d in data if isinstance(d, dict)]
    if isinstance(data, dict):
        for key in ("data", "files", "items", "recordings", "results"):
            v = data.get(key)
            if isinstance(v, list):
                return [d for d in v if isinstance(d, dict)]
            if isinstance(v, dict):
                inner = v.get("files") or v.get("items")
                if isinstance(inner, list):
                    return [d for d in inner if isinstance(d, dict)]
    return []


def _item_date(item: dict) -> str:
    for key in ("start_time", "created_at", "create_time", "date", "recorded"):
        v = item.get(key)
        if v is None:
            continue
        if isinstance(v, (int, float)):        # epoch ms 또는 s
            ts = v / 1000 if v > 1e12 else v
            try:
                return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
            except (OverflowError, OSError, ValueError):
                continue
        s = str(v)
        if len(s) >= 10 and s[4] in "-/" :
            return s[:10].replace("/", "-")
    return now_kst().strftime("%Y-%m-%d")


def fetch_mcp(since_days: int, limit: int, _retry: bool = True) -> list[Recording]:
    """최근 since_days일의 녹음과 전사를 가져온다. 미인증이면 PlaudUnavailable."""
    if not _bootstrap_tokens():
        raise PlaudUnavailable(
            "PLAUD_TOKENS_JSON 미설정 — 로컬에서 1회 로그인한 뒤 "
            "~/.plaud/tokens-mcp.json 내용을 Secret으로 등록하세요.")
    session = _McpSession()
    try:
        date_from = (now_kst() - timedelta(days=since_days)).strftime("%Y-%m-%d")
        raw = session.call_tool("list_files", {"date_from": date_from})
        if "Not authenticated" in raw or '"401"' in raw:
            # 캐시로 복원된 옛 토큰이 만료됐고 Secret은 갱신됐을 수 있다:
            # 토큰 파일을 지우고 Secret 시드로 딱 1회 재시도
            token_path = Path.home() / ".plaud" / "tokens-mcp.json"
            if _retry and os.getenv("PLAUD_TOKENS_JSON", "").strip():
                session.close()
                token_path.unlink(missing_ok=True)
                return fetch_mcp(since_days, limit, _retry=False)
            raise PlaudUnavailable(
                "플라우드 토큰 만료 — 로컬 재로그인 후 Secret을 갱신하세요.")
        recs = []
        for item in _extract_items(raw)[:limit]:
            file_id = str(item.get("id") or item.get("file_id") or "").strip()
            if not file_id:
                continue
            try:
                transcript = session.call_tool("get_transcript", {"file_id": file_id})
            except PlaudUnavailable:
                continue
            if not transcript.strip() or "Not authenticated" in transcript:
                continue
            recs.append(Recording(
                id=file_id,
                name=str(item.get("name") or item.get("title") or file_id),
                recorded=_item_date(item),
                transcript=transcript.strip(),
                source="mcp",
            ))
        return recs
    finally:
        session.close()


# ------------------------------------------------------------------- 통합 입구

def fetch_recordings(since_days: int, limit: int,
                     source: str = "auto") -> tuple[list[Recording], list[str]]:
    """(녹음 목록, 경고 메시지들). source: auto | inbox | mcp"""
    warnings: list[str] = []
    recs: list[Recording] = []
    if source in ("auto", "inbox"):
        recs.extend(fetch_inbox())
    if source in ("auto", "mcp"):
        try:
            recs.extend(fetch_mcp(since_days, limit))
        except PlaudUnavailable as e:
            msg = f"플라우드 API 생략: {e}"
            if source == "mcp":
                raise
            warnings.append(msg)
        except (OSError, FileNotFoundError) as e:
            warnings.append(f"플라우드 MCP 실행 실패(npx 필요): {e}")
    # 같은 id가 양쪽에서 오면 인박스 우선(사람이 손댄 판본)
    seen: set[str] = set()
    unique = []
    for r in recs:
        if r.id in seen:
            continue
        seen.add(r.id)
        unique.append(r)
    return unique[:limit], warnings
