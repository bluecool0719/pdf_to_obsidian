"""
PDF → Obsidian 자동 동기화 스크립트
------------------------------------
PC 전체에서 볼트 과목 폴더명과 일치하는 폴더를 찾아
그 안의 PDF를 Obsidian 볼트로 복사합니다.

- 학기가 바뀌어도 설정 변경 없이 사용 가능
- 이미 복사된 파일은 건너뜀 (중복 방지)
- 과목 폴더 아래 '(과목명) 강의록' 폴더에 저장
- 매칭 후보가 여러 개면 직접 선택 가능
- 한 번 매칭된 폴더 쌍은 매칭파일에 저장되어 다음 실행 시 재사용

사용법:
    python pdf_to_obsidian.py

설정:
    아래 SEARCH_ROOTS와 VAULT_ROOT만 수정하세요.
"""

import json
import shutil
from pathlib import Path
from datetime import datetime

# ─────────────────────────────────────────────
# ★ 여기만 수정하세요 ★

SEARCH_ROOTS = [
    r"C:\Users\destr\Documents",
    r"C:\Users\destr\Desktop",
]

VAULT_ROOT = r"C:\Users\destr\Desktop\archive"

MAX_DEPTH = 4

# ─────────────────────────────────────────────

# 매칭 기록 저장 파일 (스크립트와 같은 폴더에 생성됨)
MATCH_CACHE_FILE = Path(__file__).parent / "pdf_obsidian_matches.json"


def load_match_cache() -> dict:
    """저장된 매칭 기록 불러오기. {볼트폴더명: [PC폴더경로, ...]}"""
    if MATCH_CACHE_FILE.exists():
        try:
            with open(MATCH_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_match_cache(cache: dict):
    """매칭 기록 저장"""
    with open(MATCH_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def get_vault_subjects(vault_root: Path) -> list:
    exclude = {"Templates", "images", ".obsidian", ".trash"}
    return [
        f for f in vault_root.iterdir()
        if f.is_dir() and f.name not in exclude and not f.name.startswith(".")
    ]


def search_matching_folders(subject_name: str, search_roots: list, max_depth: int) -> list:
    matches = []

    def _walk(folder: Path, depth: int):
        if depth > max_depth:
            return
        try:
            for sub in folder.iterdir():
                if not sub.is_dir():
                    continue
                name = sub.name
                if (name == subject_name
                        or subject_name in name
                        or name in subject_name):
                    matches.append(sub)
                else:
                    _walk(sub, depth + 1)
        except PermissionError:
            pass

    for root in search_roots:
        root_path = Path(root)
        if root_path.exists():
            _walk(root_path, 1)

    return matches


def ask_user_choice(label: str, candidates: list) -> list:
    """후보가 여러 개일 때 사용자에게 선택 요청"""
    print(f"\n  ⚠  '{label}' 에 매칭되는 폴더가 여러 개 발견됐습니다.")
    print("  번호를 입력하세요. (여러 개: '1,3' / 전체: 'a' / 건너뜀: 's')\n")
    for i, path in enumerate(candidates, 1):
        pdf_count = len(list(path.glob("*.pdf")))
        print(f"    [{i}] {path}  (PDF {pdf_count}개)")
    print()

    while True:
        raw = input("  선택 → ").strip().lower()
        if raw == "s":
            print("  → 건너뜁니다.")
            return []
        if raw == "a":
            return candidates
        try:
            indices = [int(x.strip()) for x in raw.split(",")]
            if all(1 <= idx <= len(candidates) for idx in indices):
                return [candidates[idx - 1] for idx in indices]
            else:
                print(f"  1~{len(candidates)} 사이 숫자를 입력하세요.")
        except ValueError:
            print("  숫자, 'a'(전체), 's'(건너뜀) 중 하나를 입력하세요.")


def copy_pdfs(source_folder: Path, target_folder: Path) -> list:
    """PDF를 '(과목명) 강의록' 폴더로 복사. 이미 있으면 건너뜀."""
    copied = []
    pdfs = list(source_folder.glob("*.pdf"))

    if not pdfs:
        return copied

    subfolder_name = f"{target_folder.name} 강의록"
    dest = target_folder / subfolder_name
    if not dest.exists():
        dest.mkdir(parents=True)
        print(f"  [폴더 생성] {subfolder_name}/")

    for pdf in pdfs:
        dest_file = dest / pdf.name
        if dest_file.exists():
            print(f"  [건너뜀] 이미 존재: {pdf.name}")
        else:
            shutil.copy2(pdf, dest_file)
            copied.append(pdf.name)
            print(f"  [복사됨] {pdf.name}")

    return copied


def resolve_sources(vault_folder: Path, cache: dict) -> list:
    """
    캐시에 저장된 매칭이 있으면 재사용.
    없으면 탐색 후 사용자 선택 → 캐시에 저장.
    캐시에 있어도 경로가 실제로 존재하지 않으면 재탐색.
    """
    key = vault_folder.name
    cached_paths = cache.get(key, [])

    # 캐시 경로 중 실제로 존재하는 것만 필터
    valid_cached = [Path(p) for p in cached_paths if Path(p).exists()]

    if valid_cached:
        print(f"  → [캐시] {', '.join(str(p) for p in valid_cached)}")
        return valid_cached

    # 캐시 없거나 경로가 사라진 경우 → 새로 탐색
    if cached_paths and not valid_cached:
        print(f"  → 저장된 경로가 더 이상 존재하지 않아 재탐색합니다.")

    matches = search_matching_folders(vault_folder.name, SEARCH_ROOTS, MAX_DEPTH)

    if not matches:
        return []

    if len(matches) == 1:
        selected = matches
        print(f"  → {matches[0]}")
    else:
        selected = ask_user_choice(vault_folder.name, matches)

    if selected:
        cache[key] = [str(p) for p in selected]
        save_match_cache(cache)
        print(f"  → 매칭 저장됨 ({MATCH_CACHE_FILE.name})")

    return selected


def main():
    vault_root = Path(VAULT_ROOT)

    if not vault_root.exists():
        print(f"[오류] VAULT_ROOT 경로를 찾을 수 없습니다:\n  {vault_root}")
        input("\nEnter를 누르면 창이 닫힙니다...")
        return

    print("=" * 55)
    print(f"PDF → Obsidian 동기화 시작  ({datetime.now().strftime('%Y-%m-%d %H:%M')})")
    print(f"  볼트: {vault_root}")
    print(f"  매칭 캐시: {MATCH_CACHE_FILE.name}")
    print("=" * 55)

    cache = load_match_cache()
    vault_subjects = get_vault_subjects(vault_root)

    if not vault_subjects:
        print("[알림] 볼트에 과목 폴더가 없습니다.")
        input("\nEnter를 누르면 창이 닫힙니다...")
        return

    total_copied = 0
    unmatched = []

    for vault_folder in vault_subjects:
        print(f"\n[{vault_folder.name}]")

        sources = resolve_sources(vault_folder, cache)

        if not sources:
            print(f"  [매칭 없음] PC에서 '{vault_folder.name}' 폴더를 찾지 못했습니다.")
            unmatched.append(vault_folder.name)
            continue

        for source_folder in sources:
            copied = copy_pdfs(source_folder, vault_folder)
            total_copied += len(copied)

    print("\n" + "=" * 55)
    print(f"완료: {total_copied}개 파일 복사됨")
    if unmatched:
        print(f"\nPC에서 찾지 못한 과목 ({len(unmatched)}개):")
        for name in unmatched:
            print(f"  - {name}")
        print("  → 폴더명이 볼트 과목명과 다르거나 SEARCH_ROOTS 범위 밖에 있을 수 있습니다.")
    print("=" * 55)
    input("\nEnter를 누르면 창이 닫힙니다...")


if __name__ == "__main__":
    main()
