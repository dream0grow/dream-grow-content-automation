"""Dream_Grow 콘텐츠 파이프라인 오케스트레이터

전체 자동화 흐름:

  [1] AI 초안 생성 → 08 리뷰/에 저장 + .ai_drafts/에 원본 백업
      $ python3 pipeline.py generate --topic "주제" --channel thread

  [2] 사용자가 Obsidian에서 수정 후 frontmatter 상태를 '리뷰완료'로 변경

  [3] Diff 학습 + 이동
      $ python3 pipeline.py learn
      → AI원본 vs 수정본 비교 → 패턴을 Honcho에 저장
      → 07 스레드/[카테고리]/로 이동

  [4] Threads 발행
      $ python3 pipeline.py publish [--dry-run]
      → '발행대기' 상태 파일을 Threads API로 발행

  [5] 릴스 자동 생성 (리드마그넷 CTA 포함)
      $ python3 pipeline.py reels [--batch]
      → 발행된 스레드 → 릴스 스크립트 + B-roll + 리드마그넷 CTA

  [6] 리드마그넷 생성
      $ python3 pipeline.py leadmagnet --topic "주제" --category "카테고리"
      $ python3 pipeline.py leadmagnet --from-reels "릴스파일.md"
      $ python3 pipeline.py leadmagnet --batch
      → 릴스 주제 기반 리드마그넷 자동 생성 → 09 리드마그넷/에 저장

  [7] 사용자가 리드마그넷 확인 후 상태를 '확정'으로 변경

  전체 자동 실행:
      $ python3 pipeline.py auto
      → [3] learn → [4] publish → [5] reels → [6] leadmagnet 순차 실행
"""
import sys
from datetime import datetime


def cmd_generate():
    """AI 초안을 생성하여 08 리뷰/에 저장합니다."""
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--topic', required=True, help='콘텐츠 주제')
    parser.add_argument('--channel', default='thread',
                       choices=['thread', 'reels', 'youtube', 'blog'])
    parser.add_argument('--category', default='', help='카테고리 (훈육/수학/독서/...)')
    args, _ = parser.parse_known_args(sys.argv[2:])

    if args.channel == 'thread':
        from thread_generator import generate_thread
        from diff_learner import save_ai_draft
        import os

        print(f"스레드 생성 중: {args.topic}")
        content = generate_thread(args.topic, category=args.category)

        # 08 리뷰/에 저장
        review_dir = "/Users/lhg/Documents/obsidian/초생산/SNS 콘텐츠 제작 시스템/08 리뷰"
        os.makedirs(review_dir, exist_ok=True)

        safe_topic = args.topic.replace(' ', '_')[:30]
        filename = f"{safe_topic}.md"
        filepath = os.path.join(review_dir, filename)

        cat = args.category or '학습'
        fm = (
            f"---\n"
            f"type: thread\n"
            f"상태: 리뷰대기\n"
            f"생성일: {datetime.now().strftime('%Y-%m-%d')}\n"
            f"채널: Threads\n"
            f"카테고리: {cat}\n"
            f"주제: {args.topic}\n"
            f"출처: AI생성_Dream_Grow스타일\n"
            f"---\n\n"
        )

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(fm + content)

        # AI 원본 백업
        save_ai_draft(filepath)

        print(f"\n저장 완료: {filepath}")
        print(f"AI 원본 백업: .ai_drafts/{filename}")
        print(f"\n다음 단계: Obsidian에서 수정 후 상태를 '리뷰완료'로 변경하세요.")

    elif args.channel == 'reels':
        print("릴스 직접 생성은 auto_reels_from_thread.py를 사용하세요.")
    elif args.channel == 'youtube':
        print("유튜브 스크립트 생성은 youtube_script.py를 사용하세요.")


def cmd_learn():
    """리뷰완료 파일의 diff를 분석하고 Honcho에 학습합니다."""
    from diff_learner import process_reviewed_files
    results = process_reviewed_files()
    return results


def cmd_publish():
    """발행대기 파일을 Threads에 발행합니다."""
    from threads_publisher import main as publish_main
    publish_main()


def cmd_reels():
    """발행된 스레드를 릴스로 변환합니다 (리드마그넷 CTA 포함)."""
    from auto_reels_from_thread import batch_process
    batch_process()


def cmd_leadmagnet():
    """리드마그넷을 생성합니다."""
    if '--batch' in sys.argv:
        from lead_magnet_generator import batch_generate
        batch_generate()
    elif '--from-reels' in sys.argv:
        from lead_magnet_generator import generate_from_reels
        idx = sys.argv.index('--from-reels')
        if idx + 1 < len(sys.argv):
            generate_from_reels(sys.argv[idx + 1])
    elif '--status' in sys.argv:
        from lead_magnet_generator import list_status
        list_status()
    else:
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument('--topic', required=True, help='리드마그넷 주제')
        parser.add_argument('--category', default='학습')
        parser.add_argument('--type', default='')
        args, _ = parser.parse_known_args(sys.argv[2:])

        from lead_magnet_generator import generate_lead_magnet, save_lead_magnet, choose_magnet_type
        magnet_type = args.type or choose_magnet_type(args.category, args.topic)
        print(f"리드마그넷 생성: {args.topic} ({magnet_type})")
        content = generate_lead_magnet(args.topic, args.category, magnet_type)
        save_lead_magnet(content, args.topic, args.category, magnet_type)
        print(f"\n다음 단계: Obsidian에서 확인 후 상태를 '확정'으로 변경하세요.")


def cmd_auto():
    """전체 파이프라인을 순차 실행합니다."""
    print(f"{'='*60}")
    print(f"Dream_Grow 콘텐츠 파이프라인 자동 실행")
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    # Step 1: Diff 학습
    print(f"\n[Step 1/4] Diff 학습")
    print("-" * 40)
    results = cmd_learn()

    # Step 2: Threads 발행
    print(f"\n[Step 2/4] Threads 발행")
    print("-" * 40)
    cmd_publish()

    # Step 3: 릴스 생성 (리드마그넷 CTA 포함)
    print(f"\n[Step 3/4] 릴스 자동 생성 + 리드마그넷 CTA")
    print("-" * 40)
    cmd_reels()

    # Step 4: 리드마그넷 생성
    print(f"\n[Step 4/4] 리드마그넷 자동 생성")
    print("-" * 40)
    cmd_leadmagnet()

    print(f"\n{'='*60}")
    print("파이프라인 완료")
    print("리드마그넷은 09 리드마그넷/에서 확인 후 '확정'으로 변경하세요.")


def cmd_status():
    """현재 파이프라인 상태를 보여줍니다."""
    import os

    base = "/Users/lhg/Documents/obsidian/초생산/SNS 콘텐츠 제작 시스템"

    # 08 리뷰 현황
    review_dir = os.path.join(base, "08 리뷰")
    review_files = [f for f in os.listdir(review_dir)
                    if f.endswith('.md') and f != 'README.md'] if os.path.exists(review_dir) else []

    waiting = 0
    completed = 0
    for f in review_files:
        with open(os.path.join(review_dir, f), 'r') as fh:
            content = fh.read()
        if '상태: 리뷰대기' in content:
            waiting += 1
        elif '상태: 리뷰완료' in content:
            completed += 1

    print(f"\n--- 파이프라인 현황 ---")
    print(f"08 리뷰/  리뷰대기: {waiting}개  리뷰완료: {completed}개")

    # 07 스레드 카테고리별 현황
    thread_dir = os.path.join(base, "07 스레드")
    print(f"\n07 스레드/ 카테고리별:")
    total = 0
    for cat in sorted(os.listdir(thread_dir)):
        cat_dir = os.path.join(thread_dir, cat)
        if os.path.isdir(cat_dir) and not cat.startswith('.'):
            count = len([f for f in os.listdir(cat_dir) if f.endswith('.md')])
            total += count
            print(f"  {cat}: {count}개")
    print(f"  합계: {total}개")

    # 09 리드마그넷 현황
    magnet_dir = os.path.join(base, "09 리드마그넷")
    if os.path.exists(magnet_dir):
        magnet_files = [f for f in os.listdir(magnet_dir) if f.endswith('.md')]
        m_review = sum(1 for f in magnet_files
                       if '상태: 리뷰대기' in open(os.path.join(magnet_dir, f)).read())
        m_confirmed = sum(1 for f in magnet_files
                          if '상태: 확정' in open(os.path.join(magnet_dir, f)).read())
        print(f"\n09 리드마그넷/  리뷰대기: {m_review}개  확정: {m_confirmed}개")

    # Honcho 학습 현황
    from memory_manager import get_honcho_client
    client = get_honcho_client()
    if client:
        from diff_learner import get_correction_context
        ctx = get_correction_context(client, 'thread')
        if ctx:
            print(f"\nHoncho 수정 학습: 있음 ({len(ctx)}자)")
        else:
            print(f"\nHoncho 수정 학습: 없음 (아직 학습 데이터 없음)")


def main():
    commands = {
        'generate': cmd_generate,
        'learn': cmd_learn,
        'publish': cmd_publish,
        'reels': cmd_reels,
        'leadmagnet': cmd_leadmagnet,
        'auto': cmd_auto,
        'status': cmd_status,
    }

    if len(sys.argv) < 2 or sys.argv[1] not in commands:
        print("Dream_Grow 콘텐츠 파이프라인")
        print()
        print("사용법:")
        print("  python3 pipeline.py generate --topic '주제' --channel thread  # AI 초안 생성")
        print("  python3 pipeline.py learn                                     # Diff 학습")
        print("  python3 pipeline.py publish [--dry-run]                       # Threads 발행")
        print("  python3 pipeline.py reels [--batch]                           # 릴스 변환")
        print("  python3 pipeline.py leadmagnet --topic '주제' --category 수학  # 리드마그넷 생성")
        print("  python3 pipeline.py leadmagnet --from-reels '릴스파일.md'      # 릴스 연동 생성")
        print("  python3 pipeline.py leadmagnet --batch                        # 일괄 생성")
        print("  python3 pipeline.py leadmagnet --status                       # 현황 확인")
        print("  python3 pipeline.py auto                                      # 전체 자동 실행")
        print("  python3 pipeline.py status                                    # 현황 확인")
        print()
        print("워크플로우:")
        print("  generate → (Obsidian에서 수정) → learn → publish → reels → leadmagnet")
        print("  리드마그넷은 09 리드마그넷/에서 확인 후 '확정'으로 변경")
        return

    commands[sys.argv[1]]()


if __name__ == "__main__":
    main()
