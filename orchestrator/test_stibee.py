"""스티비 발송 단독 테스트 - 샘플 뉴스레터를 STIBEE_LIST_ID 주소록에 생성+발송

전체 파이프라인 없이 스티비 API 연동만 검증한다.
test-stibee 워크플로우가 STIBEE_AUTO_SEND=true를 강제로 주입해 실제 발송까지 수행한다.
실패 시 스티비 응답 본문을 그대로 출력해 payload 조정에 사용한다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator import stibee

SAMPLE = """# 우리 집 스마트폰, 싸우지 않고 시작하는 법

안녕하세요, 드림그로우입니다.

"규칙을 정했는데 매일 전쟁이에요." 많은 부모님이 하시는 말씀입니다.

사실 규칙이 잘 안 지켜지는 건 아이의 의지 문제라기보다, 규칙을 만드는 '방식' 때문일 때가 많습니다.

## 오늘 저녁에 해볼 수 있는 한 가지

아이와 함께 종이에 딱 세 줄만 적어보세요.

- 언제 쓸까 (시간)
- 어디서 쓸까 (장소)
- 다 쓰면 어디에 둘까 (보관)

함께 정한 약속은 일방적으로 통보한 규칙보다 오래갑니다.

다음 편지에서는 '아이가 약속을 어겼을 때' 이야기를 나눌게요.

— 드림그로우 드림
"""


def main():
    print(f"스티비 설정됨: {stibee.available()}  /  자동발송(AUTO_SEND): {stibee.AUTO_SEND}")
    if not stibee.available():
        print("[중단] STIBEE_API_KEY 또는 STIBEE_LIST_ID Secret이 없습니다.")
        sys.exit(1)
    try:
        result = stibee.create_and_send(
            SAMPLE, subject="[테스트] 드림그로우 뉴스레터 발송 점검",
        )
        print("결과:", result)
        if result.get("sent"):
            print("✅ 발송 성공 — test 구독자 메일함을 확인하세요.")
        else:
            print("ℹ️ 발송은 안 됨(초안만 생성되었거나 발송 단계 실패). 위 detail 확인.")
    except Exception as e:
        print(f"❌ 스티비 호출 실패: {e}")
        print("→ 위 응답 본문을 보고 orchestrator/stibee.py의 API payload를 조정해야 합니다.")
        sys.exit(1)


if __name__ == "__main__":
    main()
