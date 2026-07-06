#!/usr/bin/env python3
"""기존 초생산 볼트 → 새 구조(vault/) 이관 스크립트 — 로컬 실행 전용

통합기획 v2.1 PART 4의 재구조화 확정안을 집행한다:
번호의 의미를 "보관 카테고리"에서 "생각이 자라는 단계"로 바꾼다.

사용 (반드시 dry-run 먼저):
    python3 tools/vault_migrate.py <기존 초생산 경로> vault/            # dry-run (기본)
    python3 tools/vault_migrate.py <기존 초생산 경로> vault/ --execute  # 실제 복사

원칙:
- 원본은 절대 건드리지 않는다 (복사만, 이동·삭제 없음)
- 대상에 같은 파일이 있으면 건너뛴다 (덮어쓰기 없음)
- `제텔카스텐/1. 개인/`은 이관하지 않는다 (개인 영역 — git 커밋 금지 대상)
- 이관 후 tools/vault_secret_scan.py 를 반드시 돌려 비밀값을 확인한다
"""
import argparse
import shutil
import sys
from pathlib import Path

# (원본 상대경로, 대상 상대경로) — 앞의 규칙이 우선 적용된다
MAPPING = [
    # 제텔카스텐 5단계 파이프라인 → 새 번호 체계
    ("제텔카스텐/5. 제텔카스텐/1단계 - 메모",      "제텔카스텐/1. 메모"),
    ("제텔카스텐/5. 제텔카스텐/2단계 - 키워드",    "제텔카스텐/2. 키워드"),
    ("제텔카스텐/5. 제텔카스텐/3단계 - 의견",      "제텔카스텐/3. 의견"),
    ("제텔카스텐/5. 제텔카스텐/4단계 - 주장",      "제텔카스텐/4. 주장"),
    ("제텔카스텐/5. 제텔카스텐/5단계 - 두번째 뇌", "제텔카스텐/5. 글감"),
    ("제텔카스텐/5. 제텔카스텐/_검토필요",         "제텔카스텐/_검토대기"),
    ("제텔카스텐/5. 제텔카스텐",                  "제텔카스텐/1. 메모"),  # 루트 잔여 파일
    ("제텔카스텐/0. 지식창고",                    "제텔카스텐/0. 시스템"),
    # 지식 원천·시스템 영역 (현행 유지)
    ("raw",                                      "raw"),
    ("wiki",                                     "wiki"),
    ("SNS 콘텐츠 제작 시스템",                     "SNS 콘텐츠 제작 시스템"),
    # 목표별 산출물 작업장
    ("책 프로젝트",                               "프로젝트/책_초등부모"),
    ("스토리 메이커_꿈들 홍보팀",                   "프로젝트/꿈들"),
    ("투자",                                     "프로젝트/투자"),
    # 죽은 것들의 무덤
    ("제텔카스텐/예시",                           "_archive/예시_제레미"),
    ("제텔카스텐/_정리작업",                       "_archive/_정리작업"),
    ("_복원중복",                                "_archive/_복원중복"),
    # 미분류 인박스 (Phase 1에서 삼분류 후 폐지 검토)
    ("인박스_메모",                               "제텔카스텐/_검토대기/인박스_메모"),
    ("제텔카스텐/2. 업무",                        "_archive/구_2.업무"),
    ("제텔카스텐/3. 자기계발",                     "_archive/구_3.자기계발"),
    ("제텔카스텐/4. 일간노트",                     "제텔카스텐/6. 사례은행/_inbox/구_일간노트"),
]

SKIP_PREFIXES = [
    "제텔카스텐/1. 개인",   # 개인 영역 — 이관·커밋 금지, 볼트 밖 보관 권장
    ".obsidian",
    ".git",
    ".trash",
]

SKIP_NAMES = {".DS_Store"}


def iter_files(src_root: Path):
    for p in sorted(src_root.rglob("*")):
        if not p.is_file() or p.name in SKIP_NAMES:
            continue
        rel = p.relative_to(src_root).as_posix()
        if any(rel.startswith(s) for s in SKIP_PREFIXES):
            continue
        yield p, rel


def target_for(rel: str) -> str | None:
    for src_prefix, dst_prefix in MAPPING:
        if rel == src_prefix or rel.startswith(src_prefix + "/"):
            # 5. 제텔카스텐 루트 잔여 파일 규칙: 하위 폴더는 위 매핑이 먼저 잡는다
            remainder = rel[len(src_prefix):].lstrip("/")
            return f"{dst_prefix}/{remainder}" if remainder else dst_prefix
    # 매핑에 없는 루트 파일·폴더는 _검토대기로 (사람이 분류)
    return f"제텔카스텐/_검토대기/미분류/{rel}"


def main() -> None:
    ap = argparse.ArgumentParser(description="초생산 볼트 재구조화 이관 (복사 전용)")
    ap.add_argument("src", help="기존 초생산 볼트 경로")
    ap.add_argument("dst", help="새 볼트 경로 (저장소의 vault/)")
    ap.add_argument("--execute", action="store_true",
                    help="실제 복사 실행 (기본은 dry-run)")
    args = ap.parse_args()

    src_root, dst_root = Path(args.src), Path(args.dst)
    if not src_root.is_dir():
        print(f"원본 경로 없음: {src_root}", file=sys.stderr)
        sys.exit(2)

    copied, skipped_exist, personal = 0, 0, 0
    plan: dict[str, int] = {}
    for p, rel in iter_files(src_root):
        dst_rel = target_for(rel)
        dst = dst_root / dst_rel
        top = dst_rel.split("/")[0] + "/" + (dst_rel.split("/")[1] if "/" in dst_rel else "")
        plan[top] = plan.get(top, 0) + 1
        if dst.exists():
            skipped_exist += 1
            continue
        if args.execute:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dst)
        copied += 1

    # 개인 영역 통계 (이관 제외 안내용)
    personal_dir = src_root / "제텔카스텐/1. 개인"
    if personal_dir.exists():
        personal = sum(1 for x in personal_dir.rglob("*") if x.is_file())

    mode = "실행" if args.execute else "dry-run"
    print(f"\n[{mode}] 대상 {copied}건 복사" + (f", 기존재 {skipped_exist}건 생략" if skipped_exist else ""))
    print("\n대상 폴더별 계획:")
    for k in sorted(plan):
        print(f"  {k:<40} {plan[k]:>5}건")
    if personal:
        print(f"\n주의: '제텔카스텐/1. 개인/' {personal}건은 이관하지 않았습니다."
              " 개인정보·비밀값은 패스워드 매니저 등 볼트 밖으로 옮기세요.")
    print("\n다음 단계: python3 tools/vault_secret_scan.py", dst_root)
    if not args.execute:
        print("실제 복사는 --execute 를 붙여 다시 실행하세요.")


if __name__ == "__main__":
    main()
