# 제텔카스텐 에이전트 OS 구축 가이드

> 확정 조건: 한글 파일 50~200개(텍스트 위주) / 완전 자동 24시간 운영
> 인프라: 상시 가동 데스크톱 + tmux + Tailscale + Claude Code(Max)
> 이 문서 자체를 Claude Code에 주고 "이 가이드대로 구축해줘"라고 지시해도 됩니다.

---

## 0. 전체 그림 (도서관 비유)

- **옵시디언 볼트** = 도서관 건물
- **마크다운 메모** = 책
- **frontmatter(메타데이터)** = 모든 책에 붙는 도서 카드 (출처 추적의 핵심)
- **에이전트 7명** = 사서 7명 (각자 담당 업무가 명확)
- **cron + tmux + Claude Code 헤드리스 모드** = 24시간 근무하는 도서관장

데이터 흐름은 한 방향 컨베이어 벨트입니다.

```
hwp 원본 → [변환] → 10_Sources → [구조화] → 20_Fleeting
→ [분류] → 30_Literature / 40_Permanent
→ [집필 L1→L2→L3] → 50_Projects → [검수] → 완성 원고
                ↑ [토론]과 [리서치]가 옆에서 계속 재료 공급
```

---

## 1일차: 볼트와 뼈대 만들기 (30분)

### 1-1. 폴더 생성

데스크톱 터미널에서 그대로 실행합니다. **반드시 구글 드라이브 밖 로컬 경로**에 만듭니다 (지난 780개 파일 충돌 교훈).

```bash
mkdir -p ~/vaults/zettelkasten/{00_Inbox,10_Sources,20_Fleeting,30_Literature,40_Permanent,60_MOC}
mkdir -p ~/vaults/zettelkasten/50_Projects/{책1_제목미정,논문1_제목미정}/{L1_뼈대,L2_초고,L3_완성}
mkdir -p ~/vaults/zettelkasten/_system/{logs,scripts,templates,dialogues}
mkdir -p ~/vaults/zettelkasten/.claude/agents
cd ~/vaults/zettelkasten && git init && echo "_system/logs/" > .gitignore
```

옵시디언 앱에서 "Open folder as vault"로 `~/vaults/zettelkasten`을 엽니다.
아이폰에서는 Tailscale로 접속하거나, 나중에 Obsidian Sync/Git 동기화를 붙입니다.

### 1-2. 도서 카드 템플릿

`_system/templates/note_template.md` 로 저장합니다.

```yaml
---
id: {{날짜시각 YYYYMMDD-HHMM}}
type: fleeting          # fleeting | literature | permanent
status: inbox           # inbox → classified → used
source_original: ""     # 원본 파일명 (예: 독서교육강연.hwp)
source_file: ""         # 볼트 내 원문 경로 (예: 10_Sources/2023_독서교육강연.md)
source_section: ""      # 원문 내 위치 (예: 3장 2절)
source_url: ""          # 외부 자료면 URL
created: {{날짜}}
links: []
tags: []
---
```

**규칙 하나만 기억하시면 됩니다.** "카드 없는 메모는 인용 금지." 집필 에이전트가 이 규칙을 강제합니다.

### 1-3. 가치 기준 파일

`_system/values.md`에 선생님이 중요하게 여기는 가치를 직접 적습니다. 검수 에이전트의 채점표가 됩니다. 예시:

```markdown
# 나의 글쓰기 가치 기준
1. 아이의 자기주도성: 단기 성적이 아니라 스스로 배우는 힘을 강조하는가
2. 현장성: 22년 교실 경험에서 나온 구체적 사례가 들어 있는가
3. 학부모 존중: 부모를 가르치려 들지 않고 동반자로 대하는가
4. 근거: 모든 주장에 출처([[메모ID]])가 붙어 있는가
5. 문체: ~입니다 체, 번역투 없음, 사례 중심
```

### 1-4. CLAUDE.md (도서관 헌법)

볼트 루트에 `CLAUDE.md`를 만듭니다. 모든 에이전트가 세션 시작 때 읽는 공통 규칙입니다.

```markdown
# 제텔카스텐 볼트 운영 규칙
- 모든 새 메모는 _system/templates/note_template.md 형식을 따른다
- 10_Sources의 원문은 절대 수정하지 않는다 (읽기 전용)
- 출처(source_*)가 비어 있는 메모는 집필에 인용할 수 없다
- 판단이 애매하면 _system/review_queue.md에 질문을 남기고 넘어간다
- 작업 후 _system/logs/에 무엇을 왜 했는지 한 줄씩 기록한다
- 실수에서 배운 것은 _system/lessons.md에 추가한다
- 글은 ~입니다 체, _system/values.md의 가치를 따른다
```

---

## 2일차: 한글 파일 변환 (반나절)

텍스트 위주 50~200개면 가장 쉬운 시나리오입니다. 두 갈래로 처리합니다.

- **.hwp (구형)**: `pyhwp` 패키지의 `hwp5txt` 명령으로 텍스트 추출
- **.hwpx (신형)**: 사실 ZIP으로 압축된 XML이라 파이썬으로 직접 파싱

### 2-1. 도구 설치

```bash
pip install pyhwp
```

### 2-2. 변환 스크립트

`_system/scripts/hwp2md.py` 로 저장합니다.

```python
#!/usr/bin/env python3
"""00_Inbox의 hwp/hwpx를 10_Sources의 md로 일괄 변환"""
import subprocess, zipfile, re, sys
from pathlib import Path
from datetime import datetime

VAULT = Path.home() / "vaults/zettelkasten"
INBOX, SOURCES = VAULT / "00_Inbox", VAULT / "10_Sources"

def hwp_to_text(p):   # 구형 .hwp
    r = subprocess.run(["hwp5txt", str(p)], capture_output=True, text=True)
    return r.stdout

def hwpx_to_text(p):  # 신형 .hwpx (ZIP+XML)
    out = []
    with zipfile.ZipFile(p) as z:
        for name in sorted(n for n in z.namelist()
                           if n.startswith("Contents/section")):
            xml = z.read(name).decode("utf-8", errors="ignore")
            # 문단 태그를 줄바꿈으로, 나머지 태그 제거
            xml = re.sub(r"</hp:p>", "\n", xml)
            out.append(re.sub(r"<[^>]+>", "", xml))
    return "\n".join(out)

def main():
    for f in sorted(list(INBOX.glob("*.hwp")) + list(INBOX.glob("*.hwpx"))):
        text = hwpx_to_text(f) if f.suffix == ".hwpx" else hwp_to_text(f)
        if not text.strip():
            print(f"[실패] {f.name} → review_queue에 기록")
            with open(VAULT/"_system/review_queue.md", "a") as q:
                q.write(f"- [ ] 변환 실패: {f.name}\n")
            continue
        dest = SOURCES / (f.stem + ".md")
        header = (f"---\nsource_original: \"{f.name}\"\n"
                  f"converted: {datetime.now():%Y-%m-%d}\n"
                  f"type: source\nstatus: raw\n---\n\n")
        dest.write_text(header + text, encoding="utf-8")
        f.rename(INBOX / "done" / f.name) if (INBOX/"done").exists() else None
        print(f"[완료] {f.name} → {dest.name}")

if __name__ == "__main__":
    (INBOX / "done").mkdir(exist_ok=True)
    main()
```

### 2-3. 테스트 절차

1. hwp 파일 **3개만** `00_Inbox/`에 넣고 `python3 _system/scripts/hwp2md.py` 실행
2. 결과 md를 열어 문단이 살아 있는지 확인
3. 깨진 부분은 이후 변환 에이전트가 다듬으므로 완벽하지 않아도 됩니다
4. 3개가 잘 되면 나머지 전체를 넣고 일괄 실행

---

## 3~4일차: 사서 7명 채용 (에이전트 정의)

Claude Code 서브에이전트는 `.claude/agents/이름.md` 파일 하나로 만들어집니다.
아래 7개 파일을 그대로 생성하시면 됩니다.

### ① converter.md — 파일 변환 에이전트

```markdown
---
name: converter
description: 10_Sources의 raw 상태 원문을 읽기 좋은 마크다운으로 정리
tools: Read, Write, Edit, Glob
---
당신은 원문 정리 사서입니다.
1. 10_Sources에서 status: raw인 파일을 찾는다
2. 깨진 줄바꿈을 고치고, 제목·소제목에 #, ## 마크다운 헤딩을 붙인다
3. 내용은 한 글자도 바꾸지 않는다 (서식만 정리)
4. 정리 후 status: clean으로 바꾼다
5. 원본 hwp 파일명(source_original)은 절대 지우지 않는다
```

### ② structurer.md — 메모 구조화 에이전트

```markdown
---
name: structurer
description: 긴 원문을 제텔카스텐 원자 메모로 분해
tools: Read, Write, Glob
---
당신은 메모 분해 사서입니다. 원칙: 메모 하나 = 아이디어 하나.
1. 10_Sources에서 status: clean이고 아직 분해되지 않은 원문을 찾는다
2. 아이디어 단위로 잘라 20_Fleeting에 개별 메모로 저장한다
3. 각 메모에 note_template의 도서 카드를 반드시 붙인다:
   - source_file: 원문 경로
   - source_original: 원본 hwp 이름 (원문 frontmatter에서 복사)
   - source_section: 원문 내 위치 (예: "3장 2절", "도입부")
4. 메모 제목은 내용을 한 문장으로 요약한 것으로 짓는다
5. 처리한 원문은 status: split으로 바꾼다
※ 출처 없는 메모를 만드는 것은 규칙 위반입니다.
```

### ③ classifier.md — 분류 에이전트

```markdown
---
name: classifier
description: Fleeting 메모를 문헌/영구 메모로 승격·분류
tools: Read, Write, Edit, Glob, Grep
---
당신은 분류 사서입니다.
1. 20_Fleeting에서 status: inbox인 메모를 읽는다
2. 판정 기준:
   - 원문 요약·인용 성격 → 30_Literature로 이동, type: literature
   - 저자의 독자적 통찰로 발전 가능 → 40_Permanent로 이동, type: permanent
   - 단순 할 일·잡생각 → 그대로 두고 태그만 정리
3. Grep으로 기존 메모를 검색해 관련 메모 2~5개를 links에 추가한다
4. status: classified로 바꾸고, 판단 근거를 로그에 한 줄 남긴다
5. 확신이 60% 미만이면 review_queue.md에 올리고 건드리지 않는다
```

### ④ writer.md — 집필 에이전트

```markdown
---
name: writer
description: 분류된 메모를 L1(뼈대)→L2(초고)→L3(완성)으로 점진 집필
tools: Read, Write, Edit, Glob, Grep
---
당신은 집필 사서입니다. 최종 목표는 책과 논문입니다.

절대 규칙: 모든 주장·사례·인용 옆에 근거 메모를 [[메모ID]]로 표기한다.
source_* 가 비어 있는 메모는 인용할 수 없다.
근거가 없으면 문장을 쓰지 말고 "[근거 필요]"라고 표시한다.

단계 정의:
- L1 (뼈대): 40_Permanent 메모들을 엮어 장·절 개요를 만든다.
  각 절 아래에 사용할 메모 ID 목록을 붙인다.
- L2 (초고): L1의 각 절을 문단으로 풀어쓴다. 모든 문단 끝에 [[ID]].
  ~입니다 체, 사례 중심.
- L3 (완성): L2를 문학적으로 다듬는다. 출처 표기는 유지하되
  논문이면 각주 형식, 책이면 미주 목록으로 정리한다.

한 번 실행에 한 단계만 진행한다 (L1→L2 또는 L2→L3).
진행 상황을 50_Projects/프로젝트명/progress.md에 기록한다.
```

### ⑤ socrates.md — 토론 에이전트

```markdown
---
name: socrates
description: 소크라테스 문답으로 메모와 원고에 질문을 던지는 대화 상대
tools: Read, Write, Glob, Grep
---
당신은 소크라테스입니다. 답을 주지 말고 질문으로 생각을 깊게 만드십시오.
1. 최근 7일간 만들어진 메모와 L1~L3 원고를 읽는다
2. _system/dialogues/YYYY-MM-DD.md 에 대화 노트를 작성한다:
   - 오늘의 핵심 질문 3가지 (전제를 흔드는 질문)
   - 서로 모순되는 메모 쌍 발견 시 지적
   - 연결하면 새로운 통찰이 나올 메모 조합 제안 ([[ID]]+[[ID]])
   - 반대 입장에서 본 가장 강한 반론 1가지
3. 저자가 대화 노트에 답을 적으면, 다음 실행 때 그 답을 읽고
   후속 질문을 이어간다 (대화가 누적되는 구조)
```

### ⑥ researcher.md — 리서치 에이전트

```markdown
---
name: researcher
description: 논문·서적·뉴스·유튜브에서 자료를 수집해 문헌 메모로 저장
tools: Read, Write, WebSearch, WebFetch, Glob
---
당신은 자료 수집 사서입니다.
1. 50_Projects의 progress.md와 "[근거 필요]" 표시를 읽고
   지금 필요한 자료가 무엇인지 파악한다
2. 웹에서 학술 논문, 서적 정보, 교육 뉴스를 검색한다
3. 찾은 자료마다 30_Literature에 문헌 메모를 만든다:
   - source_url: 원문 링크 (필수)
   - 핵심 내용 요약 + 우리 프로젝트와의 관련성 한 줄
   - 저자, 발행연도, 제목 (나중에 참고문헌 목록이 됨)
4. 검증 안 된 블로그보다 논문·공식 기관 자료를 우선한다
5. 회당 최대 5건만 수집한다 (양보다 질)
```

### ⑦ reviewer.md — 검수 에이전트

```markdown
---
name: reviewer
description: AI 문체 제거 + 가치 기준 평가 (최종 관문)
tools: Read, Write, Edit, Glob
---
당신은 최종 검수 사서입니다. 두 가지 검사를 합니다.

검사 1 — 문체 (humanize-korean 규칙):
번역투, "첫째·둘째·셋째" 기계적 병렬, "결론적으로/시사하는 바가 크다"
같은 AI 관용구, 피동태 남용, 문두 접속사 남발, 이모지·불릿 과다를
찾아 자연스러운 한국어로 고친다. 내용은 한 글자도 바꾸지 않는다.

검사 2 — 가치 (채점표: _system/values.md):
각 항목을 상/중/하로 평가하고, '하'가 있으면 구체적 수정 제안과 함께
review_queue.md에 올린다. 저자 승인 없이 L3 완성 판정을 내리지 않는다.

출처 검사: [[ID]] 링크가 실제 존재하는 메모인지, 그 메모의 source_*가
채워져 있는지 전수 확인한다. 끊어진 링크는 목록으로 보고한다.
```

> **팁**: 이미 갖고 계신 humanize-korean 스킬 파일을 볼트의 `.claude/skills/`에 복사해 두면 reviewer가 40여 개 패턴 규칙을 그대로 활용합니다.

---

## 5일차: 수동 리허설 (자동화 전 필수)

자동화하기 전에 반드시 손으로 한 바퀴 돌려서 각 사서가 일을 제대로 하는지 확인합니다. 볼트 폴더에서 Claude Code를 열고 순서대로 지시합니다.

```
1. "converter 에이전트로 10_Sources의 raw 파일 2개를 정리해줘"
2. "structurer 에이전트로 방금 정리한 원문 1개를 메모로 분해해줘"
   → 20_Fleeting 메모들의 도서 카드(출처)가 채워졌는지 직접 확인!
3. "classifier 에이전트로 Fleeting 메모를 분류해줘"
4. "socrates 에이전트로 오늘 대화 노트를 만들어줘"
5. "writer 에이전트로 책1 프로젝트의 L1 뼈대를 만들어줘"
6. "reviewer 에이전트로 L1을 검수해줘"
```

각 단계 결과가 마음에 안 들면 해당 에이전트 md 파일의 지시문을 수정합니다. **여기서 이틀을 쓰더라도 검증 후 자동화하는 것이 순서입니다.**

---

## 6~7일차: 24시간 자동화 (cron + 헤드리스 모드)

### 6-1. 파이프라인 스크립트

`_system/scripts/run.sh` 로 저장합니다. Claude Code를 `-p` 플래그(헤드리스 모드)로 호출해 사람 없이 실행합니다.

```bash
#!/bin/bash
# 사용법: run.sh <에이전트명> "<지시문>"
export PATH="$PATH:/usr/local/bin:$HOME/.local/bin"  # cron은 PATH가 좁으므로 명시
VAULT="$HOME/vaults/zettelkasten"
LOG="$VAULT/_system/logs/$(date +%F).log"
cd "$VAULT" || exit 1

echo "=== $(date '+%H:%M') $1 시작 ===" >> "$LOG"
claude -p "$1 에이전트를 사용해서: $2" \
  --allowedTools "Read,Write,Edit,Glob,Grep,WebSearch,WebFetch,Bash(python3 _system/scripts/*)" \
  --max-turns 30 \
  --output-format json >> "$LOG" 2>&1
echo "=== $(date '+%H:%M') $1 종료 ===" >> "$LOG"
```

`chmod +x _system/scripts/run.sh` 로 실행 권한을 줍니다.

### 6-2. 시간표 등록 (crontab -e)

```cron
# 매시간: 변환→구조화→분류 컨베이어 벨트
0 * * * *  ~/vaults/zettelkasten/_system/scripts/run.sh converter "10_Sources의 raw 파일을 정리하라. 없으면 아무것도 하지 마라"
10 * * * * ~/vaults/zettelkasten/_system/scripts/run.sh structurer "clean 상태 원문 1개를 메모로 분해하라. 없으면 종료하라"
20 * * * * ~/vaults/zettelkasten/_system/scripts/run.sh classifier "inbox 상태 메모를 분류하라. 없으면 종료하라"

# 매일 밤 10시: 집필 (하루 한 단계씩 전진)
0 22 * * * ~/vaults/zettelkasten/_system/scripts/run.sh writer "진행 중인 프로젝트를 한 단계 진전시켜라"

# 매일 밤 11시: 검수
0 23 * * * ~/vaults/zettelkasten/_system/scripts/run.sh reviewer "오늘 writer가 쓴 원고를 검수하라"

# 매일 새벽 5시: 소크라테스 대화 노트 (아침 커피와 함께 읽기)
0 5 * * * ~/vaults/zettelkasten/_system/scripts/run.sh socrates "오늘의 대화 노트를 작성하라"

# 매주 월요일 아침 6시: 리서치
0 6 * * 1 ~/vaults/zettelkasten/_system/scripts/run.sh researcher "프로젝트에 필요한 자료를 수집하라"

# 매일 밤 11시 50분: 안전벨트 (전체 Git 백업)
50 23 * * * cd ~/vaults/zettelkasten && git add -A && git commit -m "auto $(date +%F)" >/dev/null 2>&1

# hwp 신규 투입분 자동 변환 (매시간 5분)
5 * * * * python3 ~/vaults/zettelkasten/_system/scripts/hwp2md.py >> ~/vaults/zettelkasten/_system/logs/convert.log 2>&1
```

### 6-3. 주의사항 3가지

1. **사용량**: <cite index="6-1">자동 실행도 매번 완전한 Claude Code 세션을 시작하므로 구독 사용량 한도에 포함됩니다. Max 플랜은 여유가 있는 편이지만</cite> 처음엔 위 시간표대로(하루 약 27회 소량 실행) 시작하고, 로그의 사용량을 보며 조절합니다.
2. **안전장치**: `--allowedTools`로 도구를 제한하고 `--max-turns`로 폭주를 막습니다. 10_Sources는 에이전트 규칙상 읽기 전용입니다.
3. **cron 환경**: cron은 셸 설정을 안 읽으므로 PATH를 스크립트 안에 명시했습니다. `which claude`로 실제 경로를 확인해 필요하면 PATH에 추가하세요.

---

## 운영: 아침 10분 루틴

시스템이 돌기 시작하면 선생님의 하루 일과는 이것뿐입니다.

1. **커피 + 소크라테스** (5분): `_system/dialogues/오늘날짜.md`를 열어 질문 3개를 읽고, 떠오르는 답을 그 아래 적습니다. 이 답이 다음날 후속 질문의 재료가 됩니다.
2. **결재** (3분): `_system/review_queue.md`에서 에이전트들이 올린 질문에 체크 표시로 답합니다.
3. **씨앗 심기** (2분): 떠오른 생각을 20_Fleeting에 한 줄 메모로 던져 넣습니다. 밤사이 사서들이 알아서 분류하고 연결합니다.

2주간 매일 결과를 검토하면서 에이전트 지시문을 다듬고, 신뢰가 쌓이면 검토 주기를 주 2회로 줄입니다. 실수가 발견될 때마다 `lessons.md`에 한 줄 추가하면 (드림그로우 파이프라인과 동일한 방식) 시스템이 점점 똑똑해집니다.

---

## 체크리스트 요약

- [ ] 1일차: 폴더 구조 + 템플릿 + values.md + CLAUDE.md
- [ ] 2일차: pyhwp 설치 → 샘플 3개 변환 테스트 → 전체 변환
- [ ] 3~4일차: `.claude/agents/`에 사서 7명 파일 생성
- [ ] 5일차: 수동 리허설 (출처 카드 채워지는지 눈으로 확인)
- [ ] 6일차: run.sh 작성 + crontab 등록
- [ ] 7일차: 하루 돌려보고 로그 점검, git log로 백업 확인
- [ ] 2주차: 매일 아침 10분 루틴 + 에이전트 지시문 개선
