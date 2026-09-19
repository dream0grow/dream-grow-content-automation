#!/usr/bin/env python3
"""뷰트랩 로그인 쿠키를 이 Mac의 브라우저에서 읽어 GitHub 저장소에 올려 주는 동기화 스크립트 (launchd용).

GitHub Actions(viewtrap-keywords.yml)는 뷰트랩 세션 토큰(7일짜리)이 만료되면 검색을 못 한다.
이 스크립트는 Mac의 브라우저(Aside/Chrome/Whale 등) 쿠키 DB에서 뷰트랩 `token` 쿠키를 꺼내
`VIEWTRAP_COOKIE_KEY`로 암호화해 저장소 `data/viewtrap_session.enc`에 커밋한다. 파이프라인은
환경변수 쿠키와 이 파일 중 만료가 더 늦은 쪽을 자동으로 쓴다 (orchestrator/viewtrap_keywords.py).

시스템 python3(3.9)만으로 동작한다: 표준 라이브러리 + /usr/bin/security + /usr/bin/openssl.

설치(1회, 터미널에서):
    python3 tools/viewtrap_cookie_sync.py --check      # 쿠키를 읽을 수 있는지 확인 (키체인 허용 창 → "항상 허용")
    python3 tools/viewtrap_cookie_sync.py --install    # 매일 08:30 실행하는 launchd 작업 등록 + 1회 실행
    python3 tools/viewtrap_cookie_sync.py --run        # 지금 한 번 실행
    python3 tools/viewtrap_cookie_sync.py --uninstall  # 작업 해제

설정(저장소 루트 .env, git에 안 올라감):
    VIEWTRAP_COOKIE_KEY=...   GitHub Secret과 같은 값 (Actions가 복호화에 씀)
    GITHUB_TOKEN=...          repo 권한 토큰 (data/viewtrap_session.enc 커밋용)
    OPEN_BROWSER=             (선택) 실행 전에 뷰트랩 페이지를 여는 앱 이름. 예: Aside 또는 Google Chrome.
                              토큰이 만료됐을 때 웹앱이 서버 재발급을 받게 하는 용도. 비우면 열지 않음.
로그: ~/Library/Logs/viewtrap-cookie-sync.log
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import plistlib
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOME = Path.home()
SCRIPT = Path(__file__).resolve()
REPO_ROOT = SCRIPT.parent.parent
ENV_FILE = REPO_ROOT / ".env"
LABEL = "com.dreamgrow.viewtrap-cookie-sync"
PLIST = HOME / "Library" / "LaunchAgents" / (LABEL + ".plist")
LOG = HOME / "Library" / "Logs" / "viewtrap-cookie-sync.log"
STATE = HOME / ".viewtrap-cookie-sync.json"
GITHUB_REPO = "dream0grow/dream-grow-content-automation"
REPO_FILE = "data/viewtrap_session.enc"
KST = timezone(timedelta(hours=9))
APP_SUPPORT = HOME / "Library" / "Application Support"
# (표시 이름, Application Support 하위 경로, 키체인 Safe Storage 항목 후보)
BROWSERS = [
    ("Aside", "Aside", ["Aside Safe Storage", "Chromium Safe Storage"]),
    ("Chrome", "Google/Chrome", ["Chrome Safe Storage"]),
    ("Whale", "Naver/Whale", ["Whale Safe Storage"]),
    ("Chromium", "Chromium", ["Chromium Safe Storage"]),
    ("Brave", "BraveSoftware/Brave-Browser", ["Brave Safe Storage"]),
    ("Edge", "Microsoft Edge", ["Microsoft Edge Safe Storage"]),
    ("Arc", "Arc/User Data", ["Arc Safe Storage"]),
]
SKIP_DIRS = {"Cache", "Code Cache", "GPUCache", "Service Worker", "IndexedDB", "Local Storage", "Session Storage",
             "blob_storage", "File System", "Extensions", "DawnCache", "ShaderCache", "GrShaderCache", "optimization_guide_model_store"}


def log(msg: str) -> None:
    line = f"[{datetime.now(KST):%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------- 설정
def load_env() -> dict:
    env = {}
    if ENV_FILE.exists():
        for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
            s = raw.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    env.update({k: v for k, v in os.environ.items() if k in ("VIEWTRAP_COOKIE_KEY", "GITHUB_TOKEN", "OPEN_BROWSER")})
    return env


# ---------------------------------------------------------------- 브라우저 쿠키
def find_cookie_dbs() -> list:
    """[(browser, Path)] — Application Support 아래에서 Chromium 계열 Cookies DB를 찾는다."""
    found = []
    for name, rel, _ in BROWSERS:
        base = APP_SUPPORT / rel
        if not base.exists():
            continue
        for root, dirs, files in os.walk(base):
            depth = len(Path(root).relative_to(base).parts)
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and depth < 5]
            if "Cookies" in files:
                found.append((name, Path(root) / "Cookies"))
    return found


def safe_storage_password(services: list) -> tuple:
    """키체인의 '<앱> Safe Storage' 비밀번호. (service, password) 또는 (None, None)."""
    for svc in services:
        p = subprocess.run(["/usr/bin/security", "find-generic-password", "-w", "-s", svc],
                           capture_output=True, text=True)
        if p.returncode == 0 and p.stdout.strip():
            return svc, p.stdout.strip()
    return None, None


def derive_key(password: str) -> bytes:
    return hashlib.pbkdf2_hmac("sha1", password.encode("utf-8"), b"saltysalt", 1003, 16)


def aes_cbc_decrypt(key: bytes, data: bytes) -> bytes:
    p = subprocess.run(["/usr/bin/openssl", "enc", "-d", "-aes-128-cbc", "-K", key.hex(), "-iv", (b" " * 16).hex()],
                       input=data, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError("openssl 복호화 실패: " + p.stderr.decode(errors="replace")[:200])
    return p.stdout


def decrypt_cookie(enc: bytes, key: bytes, host_key: str) -> str:
    if enc[:3] != b"v10":
        raise RuntimeError(f"알 수 없는 암호화 버전 {enc[:3]!r}")
    plain = aes_cbc_decrypt(key, enc[3:])
    prefix = hashlib.sha256(host_key.encode()).digest()
    if plain[:32] == prefix:            # Chromium 130+ : 값 앞에 SHA256(host_key)가 붙는다
        plain = plain[32:]
    return plain.decode("utf-8", errors="replace")


def jwt_exp(token: str):
    try:
        payload = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))
        return datetime.fromtimestamp(int(payload["exp"]), KST)
    except Exception:
        return None


def read_viewtrap_tokens() -> list:
    """모든 브라우저에서 뷰트랩 token 쿠키를 읽는다. [(browser, host_key, token, exp)]"""
    out = []
    dbs = find_cookie_dbs()
    if not dbs:
        log("Chromium 계열 브라우저의 Cookies DB를 찾지 못함 (Application Support 아래)")
    for name, db in dbs:
        services = next(b[2] for b in BROWSERS if b[0] == name)
        svc, pw = safe_storage_password(services)
        if not pw:
            log(f"{name}: 키체인 항목 없음/거부 ({', '.join(services)}) — {db}")
            continue
        key = derive_key(pw)
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td) / "Cookies"
            shutil.copy2(db, tmp)
            for suffix in ("-wal", "-journal"):
                if (db.parent / (db.name + suffix)).exists():
                    shutil.copy2(db.parent / (db.name + suffix), Path(td) / ("Cookies" + suffix))
            con = sqlite3.connect(str(tmp))
            try:
                rows = con.execute("SELECT host_key, name, value, encrypted_value FROM cookies "
                                   "WHERE host_key LIKE '%viewtrap.com' AND name = 'token'").fetchall()
            finally:
                con.close()
        for host_key, _, value, enc in rows:
            try:
                tok = value if value else decrypt_cookie(enc, key, host_key)
            except Exception as e:
                log(f"{name}: 복호화 실패 ({host_key}): {e}")
                continue
            exp = jwt_exp(tok)
            log(f"{name} ({svc}) {host_key}: token 만료 {exp:%Y-%m-%d %H:%M} " if exp else f"{name}: token 형식 불명 (len {len(tok)})")
            if exp:
                out.append((name, host_key, tok, exp))
    return out


# ---------------------------------------------------------------- 암호화 (orchestrator/viewtrap_keywords.py와 동일 알고리즘)
def _keys(secret: str) -> tuple:
    raw = hashlib.sha256(secret.encode()).digest()
    return hmac.new(raw, b"enc", hashlib.sha256).digest(), hmac.new(raw, b"mac", hashlib.sha256).digest()


def encrypt_blob(plain: bytes, secret: str) -> bytes:
    kenc, kmac = _keys(secret)
    nonce = os.urandom(16)
    stream, ctr = b"", 0
    while len(stream) < len(plain):
        stream += hmac.new(kenc, nonce + ctr.to_bytes(4, "big"), hashlib.sha256).digest()
        ctr += 1
    ct = bytes(a ^ b for a, b in zip(plain, stream[:len(plain)]))
    tag = hmac.new(kmac, nonce + ct, hashlib.sha256).digest()
    return base64.b64encode(nonce + ct + tag)


# ---------------------------------------------------------------- GitHub
def github(method: str, path: str, token: str, payload=None) -> dict:
    req = urllib.request.Request(f"https://api.github.com{path}", method=method,
                                 data=json.dumps(payload).encode() if payload is not None else None,
                                 headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                                          "Content-Type": "application/json", "User-Agent": "viewtrap-cookie-sync"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {}
        raise RuntimeError(f"GitHub {method} {path}: HTTP {e.code} {e.read().decode(errors='replace')[:200]}")


def publish(cookie: str, exp: datetime, env: dict) -> None:
    key, token = env.get("VIEWTRAP_COOKIE_KEY", ""), env.get("GITHUB_TOKEN", "")
    if not key or not token:
        raise RuntimeError(".env에 VIEWTRAP_COOKIE_KEY / GITHUB_TOKEN 이 필요합니다")
    blob = encrypt_blob(cookie.encode(), key).decode()
    cur = github("GET", f"/repos/{GITHUB_REPO}/contents/{REPO_FILE}?ref=main", token)
    body = {"message": f"뷰트랩 쿠키 동기화 (Mac, 만료 {exp:%m/%d %H:%M})", "content": base64.b64encode(blob.encode()).decode(),
            "branch": "main"}
    if cur.get("sha"):
        body["sha"] = cur["sha"]
    res = github("PUT", f"/repos/{GITHUB_REPO}/contents/{REPO_FILE}", token, body)
    log(f"업로드 완료: {REPO_FILE} → {res.get('commit', {}).get('sha', '')[:8]}")
    if shutil.which("gh"):
        p = subprocess.run(["gh", "secret", "set", "VIEWTRAP_COOKIE", "-R", GITHUB_REPO], input=cookie, capture_output=True, text=True)
        log("gh secret set VIEWTRAP_COOKIE " + ("완료" if p.returncode == 0 else "실패(무시): " + p.stderr.strip()[:120]))


# ---------------------------------------------------------------- 실행
def run(force: bool = False, check_only: bool = False) -> int:
    env = load_env()
    app = env.get("OPEN_BROWSER", "").strip()
    if app and not check_only:
        subprocess.run(["/usr/bin/open", "-g", "-a", app, "https://app.viewtrap.com/video-search"], capture_output=True)
        log(f"{app}에서 뷰트랩 페이지 열어 토큰 갱신 유도, 25초 대기")
        time.sleep(25)
    tokens = read_viewtrap_tokens()
    if not tokens:
        log("뷰트랩 token 쿠키를 읽지 못했습니다. 브라우저에서 app.viewtrap.com 에 로그인돼 있는지, 키체인 허용을 눌렀는지 확인")
        return 2
    browser, host, tok, exp = max(tokens, key=lambda t: t[3])
    left = exp - datetime.now(KST)
    log(f"가장 최신 토큰: {browser} ({host}) 만료 {exp:%Y-%m-%d %H:%M} (남은 {left.days}일 {left.seconds // 3600}시간)")
    if left < timedelta(0):
        log("이미 만료된 토큰입니다. 브라우저에서 뷰트랩을 한 번 열어(재발급) 다시 실행하거나 OPEN_BROWSER를 설정하세요")
        return 3
    if check_only:
        return 0
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    if not force and state.get("exp") == exp.isoformat():
        log("이미 올린 토큰과 같음 → 건너뜀")
        return 0
    publish("token=" + tok, exp, env)
    STATE.write_text(json.dumps({"exp": exp.isoformat(), "browser": browser, "uploadedAt": datetime.now(KST).isoformat()}))
    return 0


def install() -> int:
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    plist = {
        "Label": LABEL,
        "ProgramArguments": ["/usr/bin/python3", str(SCRIPT), "--run"],
        "StartCalendarInterval": [{"Hour": 8, "Minute": 30}, {"Hour": 20, "Minute": 30}],
        "StandardOutPath": str(LOG), "StandardErrorPath": str(LOG),
        "EnvironmentVariables": {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:/usr/local/bin"},
        "RunAtLoad": False,
    }
    with open(PLIST, "wb") as f:
        plistlib.dump(plist, f)
    uid = os.getuid()
    subprocess.run(["launchctl", "bootout", f"gui/{uid}", str(PLIST)], capture_output=True)
    p = subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", str(PLIST)], capture_output=True, text=True)
    if p.returncode != 0:
        log("launchctl bootstrap 실패: " + p.stderr.strip()[:200])
        return 1
    log(f"launchd 등록 완료: {PLIST} (매일 08:30, 20:30). 지금 1회 실행합니다.")
    return run()


def uninstall() -> int:
    subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}", str(PLIST)], capture_output=True)
    if PLIST.exists():
        PLIST.unlink()
    log("launchd 작업 해제 완료")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true", help="쿠키 읽기/복호화만 확인 (업로드 없음)")
    g.add_argument("--run", action="store_true", help="쿠키를 읽어 새 토큰이면 GitHub에 업로드 (기본)")
    g.add_argument("--install", action="store_true", help="launchd 등록 (매일 08:30/20:30) + 1회 실행")
    g.add_argument("--uninstall", action="store_true")
    ap.add_argument("--force", action="store_true", help="같은 토큰이어도 다시 업로드")
    a = ap.parse_args()
    if sys.platform != "darwin":
        print("macOS 전용 스크립트입니다"); return 1
    if a.install:
        return install()
    if a.uninstall:
        return uninstall()
    return run(force=a.force, check_only=a.check)


if __name__ == "__main__":
    sys.exit(main())
