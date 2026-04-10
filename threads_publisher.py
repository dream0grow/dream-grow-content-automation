"""Threads 자동 발행기 - Meta Threads API 기반

사용법:
  python3 threads_publisher.py                    # 발행대기 파일 전체 발행
  python3 threads_publisher.py --dry-run          # 발행 없이 미리보기만
  python3 threads_publisher.py --file "파일명.md"  # 특정 파일만 발행

필수 설정 (.env):
  THREADS_ACCESS_TOKEN=your_token_here
  THREADS_USER_ID=your_user_id_here

Threads API 세팅 방법:
  1. https://developers.facebook.com/ 에서 앱 생성
  2. Threads API 제품 추가
  3. 테스트 사용자로 본인 계정 추가
  4. Access Token 발급 (threads_basic, threads_content_publish 권한)
  5. .env 파일에 토큰과 사용자 ID 저장
"""
import os
import re
import sys
import json
import time
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# 경로 설정
SNS_SYSTEM = "/Users/lhg/Documents/obsidian/초생산/SNS 콘텐츠 제작 시스템"
THREAD_DIR = os.path.join(SNS_SYSTEM, "07 스레드")
PUBLISH_LOG = os.path.join(SNS_SYSTEM, "06 운영/61 성과 기록")

THREADS_ACCESS_TOKEN = os.getenv("THREADS_ACCESS_TOKEN")
THREADS_USER_ID = os.getenv("THREADS_USER_ID")
THREADS_API_BASE = "https://graph.threads.net/v1.0"


def parse_thread_file(filepath: str) -> dict:
    """스레드 파일을 파싱하여 발행 가능한 형태로 변환합니다."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # frontmatter 파싱
    fm = {}
    match = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
    if match:
        for line in match.group(1).split('\n'):
            if ':' in line:
                key, val = line.split(':', 1)
                fm[key.strip()] = val.strip().strip('"').strip("'")
        body = content[match.end():].strip()
    else:
        body = content.strip()

    # 스레드를 개별 글로 분리 (--- 구분자 또는 [N/M] 패턴)
    posts = []
    if '---' in body:
        parts = re.split(r'\n---\n', body)
        for part in parts:
            text = re.sub(r'^\[?\d+/\d+\]?\s*', '', part.strip())
            if text:
                posts.append(text)
    else:
        # 줄바꿈 기반 분리 (각 문단이 하나의 글)
        posts = [body]

    return {
        'frontmatter': fm,
        'posts': posts,
        'filename': os.path.basename(filepath),
        'filepath': filepath,
    }


def publish_to_threads(posts: list, dry_run: bool = False) -> list:
    """Threads API로 발행합니다.

    API 흐름:
    1. 첫 번째 글: POST /me/threads → media_container_id
    2. 답글들: POST /me/threads (reply_to_id 포함)
    3. 각 글: POST /me/threads_publish → 발행
    """
    if not THREADS_ACCESS_TOKEN or not THREADS_USER_ID:
        print("\n[Threads API 설정 필요]")
        print("1. https://developers.facebook.com/ 에서 앱 생성")
        print("2. Threads API 제품 추가")
        print("3. .env에 THREADS_ACCESS_TOKEN, THREADS_USER_ID 설정")
        print("\n자세한 가이드: https://developers.facebook.com/docs/threads/")
        return []

    if dry_run:
        print("\n[DRY RUN - 실제 발행하지 않음]")
        for i, post in enumerate(posts, 1):
            print(f"\n--- [{i}/{len(posts)}] ---")
            print(post[:280])
            if len(post) > 280:
                print(f"  (280자 초과: {len(post)}자 - 잘림 주의)")
        return [{'id': f'dry-run-{i}', 'text': p[:100]} for i, p in enumerate(posts)]

    try:
        import requests
    except ImportError:
        print("requests 패키지가 필요합니다: pip3 install requests")
        return []

    published = []
    parent_id = None

    for i, post_text in enumerate(posts):
        # 1. 미디어 컨테이너 생성
        params = {
            'media_type': 'TEXT',
            'text': post_text[:500],  # Threads 글자 제한
            'access_token': THREADS_ACCESS_TOKEN,
        }
        if parent_id:
            params['reply_to_id'] = parent_id

        resp = requests.post(
            f"{THREADS_API_BASE}/{THREADS_USER_ID}/threads",
            params=params
        )

        if resp.status_code != 200:
            print(f"  [{i+1}] 컨테이너 생성 실패: {resp.text}")
            break

        container_id = resp.json().get('id')

        # 2. 발행
        pub_resp = requests.post(
            f"{THREADS_API_BASE}/{THREADS_USER_ID}/threads_publish",
            params={
                'creation_id': container_id,
                'access_token': THREADS_ACCESS_TOKEN,
            }
        )

        if pub_resp.status_code != 200:
            print(f"  [{i+1}] 발행 실패: {pub_resp.text}")
            break

        media_id = pub_resp.json().get('id')
        published.append({'id': media_id, 'text': post_text[:50]})
        print(f"  [{i+1}/{len(posts)}] 발행 완료 (ID: {media_id})")

        if i == 0:
            parent_id = media_id

        # API 레이트 리밋 준수
        if i < len(posts) - 1:
            time.sleep(2)

    return published


def update_frontmatter_status(filepath: str, status: str, thread_ids: list = None):
    """발행 후 frontmatter 상태를 업데이트합니다."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # 상태 업데이트
    if '상태:' in content:
        content = re.sub(r'상태:\s*\S+', f'상태: {status}', content)

    # 발행일 추가
    pub_date = datetime.now().strftime('%Y-%m-%d')
    if '발행일:' not in content:
        content = content.replace('---\n\n', f'발행일: {pub_date}\n---\n\n', 1)

    # Thread ID 추가
    if thread_ids:
        first_id = thread_ids[0].get('id', '')
        if 'thread_id:' not in content:
            content = content.replace('---\n\n', f'thread_id: {first_id}\n---\n\n', 1)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)


def save_publish_log(filename: str, posts_count: int, thread_ids: list):
    """발행 기록을 저장합니다."""
    os.makedirs(PUBLISH_LOG, exist_ok=True)
    log_file = os.path.join(PUBLISH_LOG, f"{datetime.now().strftime('%Y-%m')} 발행 기록.md")

    entry = (
        f"\n## {datetime.now().strftime('%Y-%m-%d %H:%M')} - {filename}\n"
        f"- 글 수: {posts_count}개\n"
        f"- 플랫폼: Threads\n"
    )
    if thread_ids:
        entry += f"- 첫 글 ID: {thread_ids[0].get('id', 'N/A')}\n"

    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(entry)


def find_publishable_files() -> list:
    """07 스레드/에서 '발행대기' 상태 파일을 찾습니다."""
    files = []
    for category in os.listdir(THREAD_DIR):
        cat_dir = os.path.join(THREAD_DIR, category)
        if not os.path.isdir(cat_dir) or category.startswith('.'):
            continue
        for fname in os.listdir(cat_dir):
            if not fname.endswith('.md'):
                continue
            filepath = os.path.join(cat_dir, fname)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            fm_match = re.search(r'상태:\s*발행대기', content)
            if fm_match:
                files.append(filepath)
    return files


def main():
    dry_run = '--dry-run' in sys.argv
    specific_file = None
    if '--file' in sys.argv:
        idx = sys.argv.index('--file')
        if idx + 1 < len(sys.argv):
            specific_file = sys.argv[idx + 1]

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Threads 발행기")
    if dry_run:
        print("  모드: DRY RUN (미리보기)")
    print()

    if specific_file:
        # 특정 파일 찾기
        found = None
        for cat in os.listdir(THREAD_DIR):
            candidate = os.path.join(THREAD_DIR, cat, specific_file)
            if os.path.exists(candidate):
                found = candidate
                break
        if not found:
            print(f"파일을 찾을 수 없습니다: {specific_file}")
            return
        files = [found]
    else:
        files = find_publishable_files()

    if not files:
        print("발행대기 파일이 없습니다.")
        print("팁: frontmatter에 '상태: 발행대기'를 추가하세요.")
        return

    print(f"발행 대상: {len(files)}개 파일\n")

    for filepath in files:
        parsed = parse_thread_file(filepath)
        print(f"--- {parsed['filename']} ({len(parsed['posts'])}개 글) ---")

        results = publish_to_threads(parsed['posts'], dry_run=dry_run)

        if results and not dry_run:
            update_frontmatter_status(filepath, '발행완료', results)
            save_publish_log(parsed['filename'], len(parsed['posts']), results)
            print(f"  상태 업데이트: 발행완료")

    print(f"\n완료: {len(files)}개 파일 처리")


if __name__ == "__main__":
    main()
