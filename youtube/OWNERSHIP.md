# youtube/ 모듈 소유권

이 디렉토리(`content-automation/youtube/`)는 **10x인생 유튜브 자동화 프로젝트**가 소유한다.

## 규칙

- **Dream_Grow 세션은 이 폴더의 파일을 수정하지 않는다** (config.py, researcher.py 등 포함)
- DEFAULT_CHANNEL = "10x_life"이며 변경 금지
- Dream_Grow 세션이 YouTube 기능을 사용해야 할 경우, channel 파라미터를 명시적으로 전달
- 공유 데이터(제텔카스텐, 03 라이브러리)에는 양쪽 모두 쓰기 가능

## 데이터 흐름

```
10x인생 (youtube/)
  ├── 리서치 결과 → 제텔카스텐/1단계 - 메모/ (YT_TX_* 파일)
  ├── 원고 → 06 제작/52 원고/TX/
  └── 논문 JSON → 초생산/raw/papers/

Dream_Grow (content-automation/ 루트)
  ├── 제텔카스텐/1단계 참조 (읽기) → 스레드/뉴스레터 소재
  └── 03 라이브러리/38 주제별 참조 (읽기)
```
