"""
Obsidian 초생산 <-> content-automation 양방향 동기화 스크립트

주의: 초생산(Obsidian)이 Single Source of Truth (SSOT)
- push: content-automation -> Obsidian (초안/아이디어만)
- pull: Obsidian -> content-automation (완성본 미러링)

사용법:
  python3 sync_wiki.py          # 양방향 동기화
  python3 sync_wiki.py --check  # wiki 변경사항만 확인
  python3 sync_wiki.py --push   # content-automation -> Obsidian 만
  python3 sync_wiki.py --pull   # Obsidian -> content-automation 만
"""
import os
import shutil
import sys
from datetime import datetime

# 경로 설정
CONTENT_AUTO = "/Users/lhg/Library/CloudStorage/Dropbox/1.한결/나/ㄱ.클로드코드_드림그로우/content-automation/SNS-시스템"
OBSIDIAN_SNS = "/Users/lhg/Documents/obsidian/초생산/SNS 콘텐츠 제작 시스템"
OBSIDIAN_WIKI = "/Users/lhg/Documents/obsidian/초생산/wiki"
OBSIDIAN_THREAD = os.path.join(OBSIDIAN_SNS, "07 스레드")

# 폴더 매핑: content-automation -> Obsidian
FOLDER_MAP = {
    "05-브랜딩-완성": OBSIDIAN_THREAD,
    "03-초안-작성": os.path.join(OBSIDIAN_THREAD, "초안"),
}


def get_md_files(directory):
    """디렉토리의 .md 파일 목록과 수정 시간 반환"""
    files = {}
    if not os.path.exists(directory):
        return files
    for fname in os.listdir(directory):
        if fname.endswith('.md'):
            filepath = os.path.join(directory, fname)
            mtime = os.path.getmtime(filepath)
            files[fname] = {'path': filepath, 'mtime': mtime}
    return files


def sync_push():
    """content-automation -> Obsidian 동기화"""
    pushed = 0
    for src_folder, dst_dir in FOLDER_MAP.items():
        src_dir = os.path.join(CONTENT_AUTO, src_folder)
        os.makedirs(dst_dir, exist_ok=True)

        src_files = get_md_files(src_dir)
        dst_files = get_md_files(dst_dir)

        for fname, src_info in src_files.items():
            dst_path = os.path.join(dst_dir, fname)
            if fname not in dst_files or src_info['mtime'] > dst_files[fname]['mtime']:
                shutil.copy2(src_info['path'], dst_path)
                pushed += 1
                print(f"  PUSH: {src_folder}/{fname} -> Obsidian")

    print(f"Push 완료: {pushed}개 파일")
    return pushed


def sync_pull():
    """Obsidian -> content-automation 동기화 (wiki 변경 감지)"""
    pulled = 0

    # Obsidian 07 스레드에서 새로운/수정된 파일 감지
    obsidian_files = get_md_files(OBSIDIAN_THREAD)
    auto_files = get_md_files(os.path.join(CONTENT_AUTO, "05-브랜딩-완성"))

    for fname, obs_info in obsidian_files.items():
        if not fname.startswith('T-'):
            continue
        auto_path = os.path.join(CONTENT_AUTO, "05-브랜딩-완성", fname)
        if fname not in auto_files or obs_info['mtime'] > auto_files[fname]['mtime']:
            shutil.copy2(obs_info['path'], auto_path)
            pulled += 1
            print(f"  PULL: Obsidian/{fname} -> 05-브랜딩-완성")

    print(f"Pull 완료: {pulled}개 파일")
    return pulled


def check_wiki():
    """wiki 디렉토리 변경사항 확인"""
    print("\n=== Wiki 현황 ===")
    for sub in ['sources', 'concepts', 'entities', 'analyses']:
        sub_path = os.path.join(OBSIDIAN_WIKI, sub)
        if os.path.exists(sub_path):
            files = [f for f in os.listdir(sub_path) if f.endswith('.md')]
            print(f"  {sub}: {len(files)}개")
            # 최근 수정된 파일 표시
            recent = sorted(files, key=lambda f: os.path.getmtime(os.path.join(sub_path, f)), reverse=True)
            for f in recent[:3]:
                mtime = datetime.fromtimestamp(os.path.getmtime(os.path.join(sub_path, f)))
                print(f"    - {f} ({mtime.strftime('%m-%d %H:%M')})")

    # 스레드 현황
    print(f"\n=== 스레드 현황 ===")
    thread_path = OBSIDIAN_THREAD
    if os.path.exists(thread_path):
        files = [f for f in os.listdir(thread_path) if f.endswith('.md')]
        print(f"  완성 글: {len(files)}개")

    draft_path = os.path.join(thread_path, "초안")
    if os.path.exists(draft_path):
        files = [f for f in os.listdir(draft_path) if f.endswith('.md')]
        print(f"  초안: {len(files)}개")

    # content-automation 현황
    print(f"\n=== Content-Automation 현황 ===")
    for folder in ['01-아이디어-수집', '03-초안-작성', '05-브랜딩-완성', '06-업로드-대기']:
        folder_path = os.path.join(CONTENT_AUTO, folder)
        if os.path.exists(folder_path):
            count = len([f for f in os.listdir(folder_path) if f.endswith('.md')])
            print(f"  {folder}: {count}개")


def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] SNS 시스템 동기화")
    print(f"  소스: {CONTENT_AUTO}")
    print(f"  대상: {OBSIDIAN_SNS}")
    print()

    mode = sys.argv[1] if len(sys.argv) > 1 else "--sync"

    if mode == "--check":
        check_wiki()
    elif mode == "--push":
        sync_push()
    elif mode == "--pull":
        sync_pull()
    else:
        # 양방향 동기화
        print("--- Push (content-automation -> Obsidian) ---")
        sync_push()
        print("\n--- Pull (Obsidian -> content-automation) ---")
        sync_pull()
        print("\n--- Wiki 현황 ---")
        check_wiki()


if __name__ == "__main__":
    main()
