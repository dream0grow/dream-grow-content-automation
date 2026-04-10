"""콘텐츠 자동화 통합 메뉴"""
import sys


def show_menu():
    print()
    print("=" * 50)
    print("  🎯 콘텐츠 자동화 시스템")
    print("=" * 50)
    print()
    print("  1. 📝 스레드 글 생성")
    print("  2. 🎬 릴스 스크립트 생성")
    print("  3. 📺 유튜브 스크립트 생성")
    print("  4. 📅 오늘 할 일 정리 (Google Calendar)")
    print("  5. 🧠 메모리 설정 (Honcho)")
    print("  0. 종료")
    print()
    return input("선택하세요: ").strip()


def main():
    while True:
        choice = show_menu()

        if choice == "1":
            from thread_generator import main as thread_main
            thread_main()
        elif choice == "2":
            from reels_script import main as reels_main
            reels_main()
        elif choice == "3":
            from youtube_script import main as youtube_main
            youtube_main()
        elif choice == "4":
            from daily_planner import main as planner_main
            planner_main()
        elif choice == "5":
            from memory_manager import main as memory_main
            memory_main()
        elif choice == "0":
            print("종료합니다. 👋")
            sys.exit(0)
        else:
            print("잘못된 선택입니다. 다시 선택해주세요.")


if __name__ == "__main__":
    main()
