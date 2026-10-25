#!/usr/bin/env python3
"""
Harness Kit 설치 스크립트 — 글로벌(~/.claude)과 프로젝트(repo)에 키트를 적용한다.

Usage (Windows는 python3 대신 py):
    python3 install.py --global                     # ~/.claude 에만 적용
    python3 install.py --project /path/to/repo      # 프로젝트에만 적용
    python3 install.py --global --project .         # 둘 다
    python3 install.py ... --dry-run                # 변경 없이 계획만 출력
    python3 install.py --global --project . --uninstall   # 제거 (--dry-run과 함께 미리보기 가능)

독립 환경 (기존 ~/.claude와 분리)
    python3 install.py --global --claude-home <글로벌 폴더> --project <프로젝트> --isolated
      - 글로벌 키트를 <글로벌 폴더>에 설치 (Claude Code는 CLAUDE_CONFIG_DIR로 이 폴더를 읽는다)
      - 프로젝트에 런처 생성: claude-isolated.cmd (Windows) / claude-isolated.sh
        CLAUDE_CONFIG_DIR을 설정하고 프로젝트 폴더에서 claude(또는 인자로 준 명령)를 실행
      - .claude/settings.local.json에 claudeMdExcludes 추가: 상위 폴더 CLAUDE.md 자동 로드 차단
    --claude-home 기본값은 CLAUDE_CONFIG_DIR 환경변수, 없으면 ~/.claude

파일 종류별 처리 규칙
    코드 (scripts/*.py, hooks/*.sh, commands/*.md)
        없으면 복사. 있고 내용이 다르면 <파일>.bak.<시각>으로 백업한 뒤 교체.
    사용자 문서 (CLAUDE.md, docs/*.md)
        없으면 복사. 있으면 절대 덮어쓰지 않고 템플릿을 .harness-kit/templates/ 에 둔다.
        (docs/ 아래에 두면 execute.py가 프롬프트에 주입하므로 일부러 피한다.)
    settings.json
        병합. permissions의 deny/ask/allow는 합집합, hooks는 같은 command가 없을 때만 추가.
    .gitignore
        없는 줄만 뒤에 추가.

설치 기록 (.harness-kit/manifest.json)
    created  설치가 새로 만든 파일
    appended 설치가 기존 파일에 추가한 줄 (.gitignore)
    --uninstall은 이 기록과 백업(.bak.*)으로 되돌린다. 설치 전부터 있던 파일은 내용이
    템플릿과 같더라도 지우지 않는다.

종료 코드: 0 = 성공, 1 = 대상 경로 오류
"""

import argparse
import filecmp
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

KIT = Path(__file__).resolve().parent
STAMP = datetime.now().strftime("%Y%m%d%H%M%S")

# 사용자가 내용을 채우는 문서. 이미 있으면 덮어쓰지 않는다.
USER_DOCS = {"CLAUDE.md", "docs/PRD.md", "docs/ADR.md", "docs/ARCHITECTURE.md",
             "docs/PROPOSALS.md", "docs/UI_GUIDE.md"}
# 병합 대상. 파일 단위로 복사하지 않는다.
MERGED = {"settings.json", ".claude/settings.json", ".gitignore"}
MANIFEST = Path(".harness-kit") / "manifest.json"
# 키트 폴더에서 테스트·린트를 돌리면 생기는 캐시. 설치·제거 대상에서 제외한다.
SKIP_DIRS = {"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"}


def _skip(rel: str) -> bool:
    """캐시 폴더 아래 파일과 백업 파일(.bak.*)은 키트 파일로 보지 않는다."""
    return ".bak." in rel or any(part in SKIP_DIRS for part in rel.split("/"))
# 글로벌 settings.json 템플릿의 hook 경로 자리표시자. 설치 위치의 절대 경로로 바뀐다.
HOME_TOKEN = "{CLAUDE_HOME}"
# 이전 버전 키트가 쓰던 hook command. 마이그레이션 때 제거하고, uninstall 때도 키트 소유로 본다.
LEGACY_COMMANDS = {"bash ~/.claude/hooks/block-dangerous.sh"}


def _read_json_file(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    except json.JSONDecodeError:
        return {}


class Installer:
    def __init__(self, dry_run: bool):
        self.dry = dry_run
        self.log: list[tuple[str, str]] = []  # (동작, 대상 루트 기준 경로)
        self.root = Path(".")
        self.created: list[str] = []              # 이번 설치가 만든 파일 (root 기준 경로)
        self.appended: dict[str, list[str]] = {}  # 이번 설치가 추가한 줄
        self.generated: dict[str, str] = {}       # 키트 원본 없이 생성한 파일 내용 (런처)
        self.generated_settings: dict[str, dict] = {}  # 생성해서 병합한 settings 데이터
        self.claude_home: Path | None = None      # HOME_TOKEN 치환 대상 (글로벌 레이어 처리 중일 때만)
        self.isolated_home: str | None = None     # 독립 설치한 글로벌 경로 (프로젝트 manifest에 기록)
        # 이번 실행에서 이미 쓴 settings 파일. 같은 실행 안에서 다시 병합할 때 백업을 새로 만들지 않는다
        # (두 번째 백업에는 키트 항목이 이미 들어 있어, uninstall이 그것을 "원래 있던 항목"으로 오인한다).
        self._run_touched: set[Path] = set()

    def _rel(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def _record(self, action: str, path: Path):
        try:
            shown = path.relative_to(self.root).as_posix()
        except ValueError:
            shown = str(path)
        self.log.append((action, shown))

    # --- 파일 단위 처리 ---

    def copy_code(self, src: Path, dst: Path):
        """코드 파일: 없으면 복사, 다르면 백업 후 교체, 같으면 건너뜀."""
        if dst.exists():
            if filecmp.cmp(src, dst, shallow=False):
                return self._record("same", dst)
            backup = dst.with_name(f"{dst.name}.bak.{STAMP}")
            self._record(f"update (backup: {backup.name})", dst)
            if not self.dry:
                shutil.copy2(dst, backup)
        else:
            self._record("create", dst)
            self.created.append(self._rel(dst))
        if not self.dry:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            if dst.suffix in (".sh", ".py"):
                dst.chmod(dst.stat().st_mode | 0o111)

    def copy_user_doc(self, src: Path, dst: Path, template_dir: Path):
        """사용자 문서: 없으면 복사. 있으면 보존하고 템플릿만 별도 위치에 둔다."""
        if not dst.exists():
            self._record("create", dst)
            self.created.append(self._rel(dst))
            if not self.dry:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            return
        if filecmp.cmp(src, dst, shallow=False):
            return self._record("same", dst)
        tpl = template_dir / src.name
        self._record(f"keep (template → {tpl.relative_to(self.root).as_posix()})", dst)
        if not self.dry:
            tpl.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, tpl)

    def _kit_settings(self, src: Path) -> dict:
        """키트 settings 템플릿을 읽고 HOME_TOKEN을 설치 위치 절대 경로(슬래시 형식)로 바꾼다."""
        text = src.read_text(encoding="utf-8")
        if self.claude_home is not None:
            text = text.replace(HOME_TOKEN, self.claude_home.resolve().as_posix())
        return json.loads(text)

    def merge_settings(self, src: Path, dst: Path):
        self.merge_settings_data(self._kit_settings(src), dst)

    def merge_settings_data(self, new: dict, dst: Path):
        """settings 병합: permissions와 최상위 리스트 키는 합집합, hooks는 command 기준으로 중복 없이 추가.

        이전 버전 키트의 hook(LEGACY_COMMANDS)은 먼저 제거한다 (경로 형식이 바뀌어 중복 등록되는 것 방지).
        """
        cur = json.loads(dst.read_text(encoding="utf-8")) if dst.exists() else {}
        before = json.dumps(cur, sort_keys=True)
        self._drop_hook_commands(cur, LEGACY_COMMANDS)

        for key, val in new.items():
            if isinstance(val, list):
                lst = cur.setdefault(key, [])
                lst.extend(i for i in val if i not in lst)
            elif key not in ("permissions", "hooks"):
                # 단일 값 키 (예: statusLine): 없을 때만 설정. 다른 값이 있으면 사용자 설정을 유지한다.
                if key not in cur:
                    cur[key] = val
                elif cur[key] != val:
                    print(f"WARN: {dst}에 이미 다른 {key} 설정이 있어 유지한다 (가져오지 않음).")

        perms = cur.setdefault("permissions", {}) if "permissions" in new else None
        for key, items in new.get("permissions", {}).items():
            merged = perms.setdefault(key, [])
            merged.extend(i for i in items if i not in merged)

        hooks = cur.setdefault("hooks", {}) if "hooks" in new else None
        for event, groups in new.get("hooks", {}).items():
            existing = hooks.setdefault(event, [])
            known = {h.get("command") for g in existing for h in g.get("hooks", [])}
            for g in groups:
                fresh = [h for h in g.get("hooks", []) if h.get("command") not in known]
                if fresh:
                    existing.append({**g, "hooks": fresh})

        if json.dumps(cur, sort_keys=True) == before:
            return self._record("same", dst)
        key = dst.resolve()
        if key in self._run_touched:
            self._record("merge", dst)  # 이번 실행에서 이미 백업했거나 새로 만든 파일
        elif dst.exists():
            backup = dst.with_name(f"{dst.name}.bak.{STAMP}")
            self._record(f"merge (backup: {backup.name})", dst)
            if not self.dry:
                shutil.copy2(dst, backup)
        else:
            self._record("create", dst)
            self.created.append(self._rel(dst))
        self._run_touched.add(key)
        if not self.dry:
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(json.dumps(cur, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def merge_lines(self, src: Path, dst: Path):
        """.gitignore 병합: 없는 줄만 뒤에 추가한다."""
        cur = dst.read_text(encoding="utf-8").splitlines() if dst.exists() else []
        add = [ln for ln in src.read_text(encoding="utf-8").splitlines() if ln.strip() and ln not in cur]
        if not add:
            return self._record("same", dst)
        self._record(f"append {len(add)} lines", dst)
        if not dst.exists():
            self.created.append(self._rel(dst))
        self.appended[self._rel(dst)] = add
        if not self.dry:
            with dst.open("a", encoding="utf-8") as f:
                if cur and cur[-1].strip():
                    f.write("\n")
                f.write("\n".join(add) + "\n")

    # --- 레이어 단위 처리 ---

    def install(self, src_root: Path, dst_root: Path):
        """src_root 아래 모든 파일을 종류별 규칙에 따라 dst_root에 적용한다."""
        self.root = dst_root
        self.created, self.appended = [], {}
        template_dir = dst_root / ".harness-kit" / "templates"
        for src in sorted(p for p in src_root.rglob("*") if p.is_file()):
            rel = src.relative_to(src_root).as_posix()
            if _skip(rel):
                continue
            dst = dst_root / rel
            if rel in MERGED:
                (self.merge_lines if rel == ".gitignore" else self.merge_settings)(src, dst)
            elif rel in USER_DOCS:
                self.copy_user_doc(src, dst, template_dir)
            else:
                self.copy_code(src, dst)
        if not self.dry and (self.created or self.appended):
            self._write_manifest(dst_root)

    def _write_manifest(self, dst_root: Path):
        """이번 설치 기록을 기존 manifest에 합친다 (재설치해도 최초 생성 기록이 유지되도록)."""
        path = dst_root / MANIFEST
        m = self._read_manifest(dst_root) or {"created": [], "appended": {}}
        m["created"] = sorted(set(m["created"]) | set(self.created))
        for rel, lines in self.appended.items():
            known = m["appended"].setdefault(rel, [])
            known.extend(ln for ln in lines if ln not in known)
        m.setdefault("generated", {}).update(self.generated)
        if self.isolated_home:
            m["claude_home"] = self.isolated_home
        for rel, data in self.generated_settings.items():
            cur = m.setdefault("generated_settings", {}).setdefault(rel, {})
            for key, val in data.items():
                cur[key] = sorted(set(cur.get(key, [])) | set(val)) if isinstance(val, list) else val
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(m, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def install_isolated(self, root: Path, claude_home: Path):
        """독립 환경용 런처와 상위 CLAUDE.md 제외 설정을 프로젝트에 만든다."""
        self.root = root
        self.created, self.appended, self.generated, self.generated_settings = [], {}, {}, {}
        home = str(claude_home.resolve())
        self.isolated_home = home
        if os.name == "nt":
            # 주의: cmd는 rem 줄에서도 %변수% 를 치환한다. 아래 rem 주석에는 % 를 쓰지 않는다.
            name, text = "claude-isolated.cmd", "\r\n".join([
                "@echo off",
                "rem Harness Kit isolated launcher: runs Claude Code with this project's own global config.",
                "rem Settings and hooks in the user profile .claude folder are NOT applied.",
                "rem   claude-isolated.cmd                              start Claude Code",
                "rem   claude-isolated.cmd py scripts\\execute.py 0-mvp   run a harness phase",
                "rem setlocal: CLAUDE_CONFIG_DIR and cd are undone when this script ends,",
                "rem so the calling cmd window does not stay in the isolated environment.",
                "setlocal",
                f'set "CLAUDE_CONFIG_DIR={home}"',
                'cd /d "%~dp0"',
                "rem Run the arguments via goto, not inside an if/else block: cmd expands the",
                "rem argument list before parsing, so empty or parenthesized arguments break it.",
                'if "%~1"=="" goto interactive',
                "call %*",
                "exit /b %ERRORLEVEL%",
                ":interactive",
                "call claude",
                "exit /b %ERRORLEVEL%",
                "",
            ])
        else:
            name, text = "claude-isolated.sh", "\n".join([
                "#!/usr/bin/env bash",
                "# Harness Kit isolated launcher: runs Claude Code with this project's own global config.",
                "#   ./claude-isolated.sh                               start Claude Code",
                "#   ./claude-isolated.sh python3 scripts/execute.py 0-mvp  run a harness phase",
                f'export CLAUDE_CONFIG_DIR="{home}"',
                'cd "$(dirname "$0")"',
                'if [ $# -eq 0 ]; then exec claude; else exec "$@"; fi',
                "",
            ])
        dst = root / name
        if dst.exists() and dst.read_bytes() == text.encode("utf-8"):
            self._record("same", dst)
        elif dst.exists():
            # 이전 버전 런처이거나 사용자가 고친 런처: 백업 후 교체
            backup = dst.with_name(f"{dst.name}.bak.{STAMP}")
            self._record(f"update (backup: {backup.name})", dst)
            if not self.dry:
                shutil.copy2(dst, backup)
                dst.write_bytes(text.encode("utf-8"))
        else:
            self._record("create", dst)
            self.created.append(name)
            if not self.dry:
                dst.write_bytes(text.encode("utf-8"))
                dst.chmod(dst.stat().st_mode | 0o111)
        self.generated[name] = text

        # Claude Code는 실행 폴더 위쪽의 CLAUDE.md를 모두 읽는다. 독립 환경을 위해 상위 폴더 것은 제외한다.
        # 패턴은 절대 경로 기준 glob. OS별 경로 표기 차이에 대비해 절대 경로형과 **/폴더명형을 함께 넣는다.
        patterns = []
        for anc in root.resolve().parents:
            for fname in ("CLAUDE.md", "CLAUDE.local.md"):
                patterns.append(f"{anc.as_posix().rstrip('/')}/{fname}")
                if anc.name:
                    patterns.append(f"**/{anc.name}/{fname}")
        data = {"claudeMdExcludes": patterns}
        local = root / ".claude" / "settings.local.json"
        self.merge_settings_data(data, local)
        self.generated_settings[".claude/settings.local.json"] = data
        if not self.dry:
            self._write_manifest(root)

    def install_statusline(self, src_settings: Path, claude_home: Path):
        """src_settings의 statusLine을 글로벌(claude_home) settings.json으로 가져온다.

        스크립트 파일은 복사하지 않고 원본 command를 그대로 쓴다 (원본을 고치면 양쪽에 반영).
        대상에 다른 statusLine이 있으면 유지한다. 가져온 값은 manifest에 남겨 uninstall 때 제거한다.
        """
        self.root = claude_home
        self.created, self.appended, self.generated, self.generated_settings = [], {}, {}, {}
        self.isolated_home = None
        dst = claude_home / "settings.json"
        if src_settings.resolve() == dst.resolve():
            print("statusline: 원본과 대상이 같은 파일이라 가져올 것이 없다.")
            return
        sl = _read_json_file(src_settings).get("statusLine")
        if not sl:
            print(f"WARN: {src_settings}에 statusLine이 없어 건너뛴다.")
            return
        data = {"statusLine": sl}
        had = "statusLine" in _read_json_file(dst)
        self.merge_settings_data(data, dst)
        if not had:  # 실제로 넣었을 때만 기록 (원래 있던 statusLine은 uninstall 대상이 아니다)
            self.generated_settings["settings.json"] = data
        if not self.dry:
            self._write_manifest(claude_home)

    def install_ccstatusline(self, claude_home: Path):
        """extras/statusline/statusline-setup.js로 ccstatusline 구성을 글로벌(claude_home)에 설치한다.

        JS 파일은 그대로 실행만 한다 (사용자 build.py 산출물이라 수정하지 않음).
        실행 전후를 비교해 새로 생긴 위젯 파일과 바뀐 statusLine을 manifest에 남기고, uninstall 때 되돌린다.
        npm 전역 ccstatusline과 위젯이 실행 중 만드는 캐시 파일은 되돌리기 대상이 아니다.
        """
        self.root = claude_home
        self.created, self.appended, self.generated, self.generated_settings = [], {}, {}, {}
        self.isolated_home = None
        js = KIT / "extras" / "statusline" / "statusline-setup.js"
        node = shutil.which("node")
        if not node:
            print("WARN: node를 찾지 못해 statusline 설치를 건너뛴다 (Node.js 18 이상 필요).")
            return
        widget_dir = claude_home / "ccstatusline"
        if self.dry and not claude_home.is_dir():
            # JS는 대상 폴더가 있어야 실행된다. 글로벌을 이번에 새로 만드는 dry-run에서는 계획만 표시.
            return self._record("statusline-setup.js 실행 예정 (글로벌 폴더 생성 후)", widget_dir)
        settings = claude_home / "settings.json"
        before_files = {p for p in widget_dir.rglob("*") if p.is_file()} if widget_dir.is_dir() else set()
        before_sl = _read_json_file(settings).get("statusLine")
        # JS도 <파일>.bak.<초 단위 시각>으로 백업한다. 이번 실행에서 키트가 만든 백업과 이름이 겹쳐
        # 원본 백업이 덮어써지지 않도록, 같은 초면 다음 초까지 기다린다.
        if any(claude_home.glob(f"*.bak.{STAMP}")):
            while datetime.now().strftime("%Y%m%d%H%M%S") == STAMP:
                time.sleep(0.1)
        print(f"\n[statusline] node {js.name} --claude-home {claude_home}{' --dry-run' if self.dry else ''}")
        cmd = [node, str(js), "--claude-home", str(claude_home)] + (["--dry-run"] if self.dry else [])
        if subprocess.run(cmd).returncode != 0:
            print("WARN: statusline 설치 실패. 위 메시지를 확인한다 (설치기는 검사 단계 실패 시 아무것도 바꾸지 않는다).")
            return
        if self.dry:
            return
        for f in sorted({p for p in widget_dir.rglob("*") if p.is_file()} - before_files):
            rel = f.relative_to(claude_home).as_posix()
            self.generated[rel] = f.read_bytes().decode("utf-8")
            self.created.append(rel)
            self._record("create (statusline)", f)
        after_sl = _read_json_file(settings).get("statusLine")
        if after_sl is not None and after_sl != before_sl:
            self.generated_settings["settings.json"] = {"statusLine": after_sl}
            self._record("set statusLine (statusline)", settings)
        self._write_manifest(claude_home)

    @staticmethod
    def _read_manifest(dst_root: Path):
        path = dst_root / MANIFEST
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    # --- 제거 (install의 역연산) ---

    @staticmethod
    def _backups(dst: Path) -> list:
        """설치 때 만든 <파일>.bak.<시각> 목록 (시각순)."""
        return sorted(dst.parent.glob(f"{dst.name}.bak.*"))

    def _original_backup(self, dst: Path):
        """가장 오래된 백업 = 키트를 처음 설치하기 전 상태. 없으면 None.

        재설치·추가 병합 때 생긴 나중 백업에는 이전 설치의 키트 항목이 들어 있으므로 기준으로 쓰지 않는다.
        사용한 파일은 uninstall 마지막에 백업을 한꺼번에 정리하도록 표시해 둔다.
        """
        backups = self._backups(dst)
        if backups:
            self._cleanup.add(dst)
        return backups[0] if backups else None

    def _remove(self, path: Path, action: str = "remove"):
        self._record(action, path)
        if not self.dry:
            shutil.rmtree(path) if path.is_dir() else path.unlink()

    @staticmethod
    def _drop_hook_commands(cfg: dict, commands: set):
        """cfg의 hooks에서 command가 commands에 속한 항목을 지우고, 빈 그룹/이벤트/키를 정리한다."""
        for event in list(cfg.get("hooks", {})):
            groups = []
            for g in cfg["hooks"][event]:
                hooks = [h for h in g.get("hooks", []) if h.get("command") not in commands]
                if hooks:
                    groups.append({**g, "hooks": hooks})
            if groups:
                cfg["hooks"][event] = groups
            else:
                del cfg["hooks"][event]
        if cfg.get("hooks") == {}:
            del cfg["hooks"]

    def unmerge_settings(self, src: Path, dst: Path, created: bool = False):
        self.unmerge_settings_data(self._kit_settings(src), dst, created)

    def unmerge_settings_data(self, kit: dict, dst: Path, created: bool = False):
        """settings.json에서 키트가 추가한 항목만 뺀다.

        설치 전 백업에 있던 항목은 남기고, 설치 후 사용자가 추가한 항목도 남긴다.
        제거 후 비어 있으면 파일을 지운다(설치가 새로 만든 경우).
        """
        if not dst.exists():
            return
        cur = json.loads(dst.read_text(encoding="utf-8"))
        backup = self._original_backup(dst)
        # 키트가 새로 만든 파일이면 설치 전 상태는 "없음". 이후 생긴 백업(예: statusline 설치기)은
        # 키트 항목이 들어간 중간 상태라 기준으로 쓰지 않는다.
        before = {} if created or not backup else json.loads(backup.read_text(encoding="utf-8"))
        before_cmds = {h.get("command") for gs in before.get("hooks", {}).values()
                       for g in gs for h in g.get("hooks", [])}
        orig = json.dumps(cur, sort_keys=True)

        for key, items in kit.get("permissions", {}).items():
            keep_before = before.get("permissions", {}).get(key, [])
            lst = cur.get("permissions", {}).get(key)
            if lst is not None:
                cur["permissions"][key] = [i for i in lst if i not in items or i in keep_before]
                if not cur["permissions"][key]:
                    del cur["permissions"][key]
        if cur.get("permissions") == {}:
            del cur["permissions"]

        for key, val in kit.items():
            if isinstance(val, list) and isinstance(cur.get(key), list):  # 리스트 키 (예: claudeMdExcludes)
                cur[key] = [i for i in cur[key] if i not in val or i in before.get(key, [])]
                if not cur[key]:
                    del cur[key]
            elif key not in ("permissions", "hooks") and not isinstance(val, list):
                # 단일 값 키 (예: statusLine): 키트가 넣은 값 그대로일 때만 되돌린다.
                # 설치 전 값이 있었으면 그 값으로 복원(설치기가 교체한 경우), 없었으면 제거.
                if cur.get(key) == val:
                    if key not in before:
                        del cur[key]
                    elif before[key] != val:
                        cur[key] = before[key]

        kit_cmds = ({h.get("command") for gs in kit.get("hooks", {}).values()
                     for g in gs for h in g.get("hooks", [])} | LEGACY_COMMANDS) - before_cmds
        self._drop_hook_commands(cur, kit_cmds)

        if json.dumps(cur, sort_keys=True) == orig:
            self._record("same", dst)
        elif not cur:
            self._remove(dst)
        else:
            self._record("unmerge", dst)
            if not self.dry:
                dst.write_text(json.dumps(cur, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def _uninstall_by_manifest(self, rel: str, dst: Path, same: bool, was_created: bool):
        """manifest 기준 제거: 만든 파일은 삭제, 교체한 파일은 백업 복원, 원래 있던 파일은 그대로."""
        edited = "keep (내용 작성됨)" if rel in USER_DOCS else "keep (설치 후 수정됨)"
        backup = self._original_backup(dst)
        if was_created:
            self._remove(dst) if same else self._record(edited, dst)
        elif backup:
            if not same:
                self._cleanup.discard(dst)  # 설치 후 수정됨: 사용자가 복원할 수 있도록 백업을 남긴다
                return self._record(edited, dst)
            self._record(f"restore ← {backup.name}", dst)
            if not self.dry:
                shutil.copy2(backup, dst)
        else:
            self._record("same", dst)  # 설치 전부터 있던 파일 — 건드리지 않음

    def unappend_lines(self, dst: Path, lines, was_created: bool):
        """manifest에 기록된 추가 줄만 제거한다. 기록이 없으면 보존하고 알린다."""
        if not dst.exists():
            return
        if lines is None:
            return self._record("keep (추가된 줄은 수동 정리)", dst)
        cur = dst.read_text(encoding="utf-8").splitlines()
        rest = [ln for ln in cur if ln not in lines]
        while rest and not rest[-1].strip():
            rest.pop()
        if was_created and not any(ln.strip() for ln in rest):
            return self._remove(dst)
        self._record(f"remove {len(cur) - len(rest)} lines", dst)
        if not self.dry:
            dst.write_text("\n".join(rest) + ("\n" if rest else ""), encoding="utf-8")

    def uninstall(self, src_root: Path, dst_root: Path):
        """src_root의 키트 파일을 기준으로 dst_root에서 키트를 제거한다.

        manifest 있음 (_uninstall_by_manifest)
            설치가 만든 파일   수정 안 됐으면 삭제, 수정됐으면 보존
            설치가 교체한 파일 수정 안 됐으면 백업 복원, 수정됐으면 보존
            원래 있던 파일     그대로
        manifest 없음 (이전 버전 설치): 키트 원본/템플릿과 같은지로 추정
        settings    unmerge_settings
        .gitignore  manifest에 기록된 추가 줄만 제거
        그 외       .harness-kit/, harness_map.html 삭제. phases/ 등 작업 결과는 건드리지 않는다.
        """
        self.root = dst_root
        self._cleanup: set[Path] = set()
        manifest = self._read_manifest(dst_root)
        created = set(manifest["created"]) if manifest else None
        if manifest is None:
            print(f"WARN: {dst_root / MANIFEST} 없음 (이전 버전 install.py로 설치됨). "
                  "파일 내용으로 판단하므로, 설치 전부터 있던 파일이 템플릿과 같으면 함께 제거될 수 있다.")
        touched_dirs = set()
        for src in sorted(p for p in src_root.rglob("*") if p.is_file()):
            rel = src.relative_to(src_root).as_posix()
            if _skip(rel):
                continue
            dst = dst_root / rel
            touched_dirs.update(p for p in dst.parents if dst_root in p.parents)
            if rel == ".gitignore":
                self.unappend_lines(dst, (manifest or {}).get("appended", {}).get(rel),
                                    created is not None and rel in created)
                continue
            if rel in MERGED:
                self.unmerge_settings(src, dst, created is not None and rel in created)
                continue
            if not dst.exists():
                continue
            same = filecmp.cmp(src, dst, shallow=False)
            if created is not None:
                self._uninstall_by_manifest(rel, dst, same, rel in created)
                continue
            # --- manifest 없음: 내용 비교로 추정 ---
            if rel in USER_DOCS:
                if same:
                    self._remove(dst, "remove (템플릿 그대로)")
                else:
                    self._record("keep (내용 작성됨)", dst)
                continue
            if not same:
                self._record("keep (설치 후 수정됨)", dst)
                continue
            backup = self._original_backup(dst)
            if backup:
                self._record(f"restore ← {backup.name}", dst)
                if not self.dry:
                    shutil.copy2(backup, dst)
            else:
                self._remove(dst)

        for rel, text in (manifest or {}).get("generated", {}).items():
            dst = dst_root / rel
            touched_dirs.update(p for p in dst.parents if dst_root in p.parents)
            if dst.exists():
                same = dst.read_bytes() == text.encode("utf-8")
                self._remove(dst) if same else self._record("keep (설치 후 수정됨)", dst)
        for rel, data in (manifest or {}).get("generated_settings", {}).items():
            self.unmerge_settings_data(data, dst_root / rel, created is not None and rel in created)

        extras = [dst_root / ".harness-kit"]
        # 실행 부산물(Map 출력, 바이트코드 캐시)은 키트가 scripts/를 설치한 레이어(프로젝트)에서만 정리한다.
        # 캐시는 scripts/에 키트 외 파일이 없을 때만 지운다 (사용자 스크립트의 캐시는 건드리지 않음).
        kit_scripts = src_root / "scripts"
        if kit_scripts.is_dir():
            extras.append(dst_root / "harness_map.html")
            scripts = dst_root / "scripts"
            others = [e for e in scripts.iterdir()
                      if e.name != "__pycache__" and not (kit_scripts / e.name).exists()] if scripts.is_dir() else []
            if not others:
                extras.append(scripts / "__pycache__")
        for extra in extras:
            if extra.exists():
                self._remove(extra)
        # 되돌리는 데 쓴 가장 오래된 백업만 마지막에 정리한다 (여러 단계가 같은 백업을 참조할 수 있어 끝까지 둔다).
        # 나중 백업(재설치 때 생긴 중간 버전)에는 사용자가 고친 내용이 있을 수 있어 지우지 않고 알린다.
        for dst in sorted(self._cleanup):
            backups = self._backups(dst)
            if backups:
                self._remove(backups[0], "remove backup")
            for b in backups[1:]:
                self._record("keep backup (중간 버전 — 확인 후 직접 삭제)", b)
        # 키트 때문에 생겼고 이제 비어 있는 디렉토리 정리 (깊은 곳부터)
        if not self.dry:
            for d in sorted(touched_dirs, key=lambda p: len(p.parts), reverse=True):
                if d.is_dir() and not any(d.iterdir()):
                    d.rmdir()
                    self._record("remove empty dir", d)

    def report(self, title: str):
        print(f"\n[{title}]{' (dry-run)' if self.dry else ''}")
        width = max((len(a) for a, _ in self.log), default=0) + 2
        for action, path in self.log:
            if action != "same":
                print(f"  {action:<{width}} {path}")
        same = sum(1 for a, _ in self.log if a == "same")
        if same:
            print(f"  (변경 없음 {same}개)")
        self.log.clear()


def resolve_claude_home(explicit, project, isolated) -> Path:
    """글로벌 경로를 정한다: --claude-home → 프로젝트 독립 설치 기록 → CLAUDE_CONFIG_DIR → ~/.claude.

    프로젝트 기록을 2순위로 두는 이유: 독립 설치한 프로젝트를 --claude-home 없이 재설치할 때
    런처와 글로벌이 기본 ~/.claude로 바뀌어 기존 환경에 섞이는 것을 막기 위해서다.
    """
    default = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    recorded = None
    if project is not None:
        m = Installer._read_manifest(project.resolve())
        recorded = Path(m["claude_home"]) if m and m.get("claude_home") else None
    if explicit is not None:
        if recorded and explicit.resolve() != recorded.resolve():
            print(f"WARN: 이 프로젝트는 {recorded} 를 글로벌로 설치했었다. {explicit} 로 바뀐다.")
        return explicit
    if recorded is not None:
        print(f"글로벌 경로: 프로젝트 설치 기록 사용 → {recorded}")
        return recorded
    if isolated and default.resolve() == (Path.home() / ".claude").resolve():
        raise ValueError("--isolated는 기존 ~/.claude와 분리된 글로벌이 필요하다. --claude-home <폴더>를 지정하세요.")
    return default


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Harness Kit installer")
    ap.add_argument("--global", dest="glob", action="store_true", help="글로벌 레이어 적용 (위치는 --claude-home 규칙으로 결정)")
    ap.add_argument("--project", type=Path, help="적용할 프로젝트 루트")
    ap.add_argument("--claude-home", type=Path,
                    help="글로벌 설정 위치. 생략 시: 프로젝트의 독립 설치 기록 → CLAUDE_CONFIG_DIR → ~/.claude")
    ap.add_argument("--isolated", action="store_true",
                    help="독립 환경: 런처(claude-isolated)와 상위 CLAUDE.md 제외 설정 생성. --project 필요")
    ap.add_argument("--statusline-from", type=Path, nargs="?", const=Path.home() / ".claude" / "settings.json",
                    help="이 settings.json의 statusLine을 글로벌로 가져옴 (값 생략 시 ~/.claude/settings.json). --global 필요")
    ap.add_argument("--with-statusline", action="store_true",
                    help="extras/statusline/statusline-setup.js로 ccstatusline 구성을 글로벌에 설치 (Windows, Node.js 필요). --global 필요")
    ap.add_argument("--dry-run", action="store_true", help="변경 없이 계획만 출력")
    ap.add_argument("--uninstall", action="store_true", help="설치한 키트를 제거 (설치 후 수정한 내용은 보존)")
    args = ap.parse_args(argv)

    if not args.glob and not args.project:
        ap.error("--global 또는 --project 중 하나 이상 지정하세요.")
    if args.isolated and not args.project:
        ap.error("--isolated는 --project와 함께 지정하세요.")
    if args.statusline_from and not args.glob:
        ap.error("--statusline-from은 --global과 함께 지정하세요 (글로벌 settings.json에 넣는다).")
    if args.with_statusline and not args.glob:
        ap.error("--with-statusline은 --global과 함께 지정하세요.")
    if args.with_statusline and args.statusline_from:
        ap.error("--with-statusline과 --statusline-from은 함께 쓸 수 없다 (둘 다 statusLine을 설정한다).")
    try:
        args.claude_home = resolve_claude_home(args.claude_home, args.project, args.isolated)
    except ValueError as e:
        ap.error(str(e))

    inst = Installer(args.dry_run)
    if args.uninstall:
        if args.glob:
            inst.claude_home = args.claude_home
            inst.uninstall(KIT / "global", args.claude_home)
            inst.claude_home = None
            inst.report(f"uninstall global ← {args.claude_home}")
        if args.project:
            root = args.project.resolve()
            if not root.is_dir():
                print(f"ERROR: {root} 디렉토리가 없습니다.")
                return 1
            inst.uninstall(KIT / "project", root)
            inst.report(f"uninstall project ← {root}")
            print("\n남겨 둔 것: phases/ (작업 기록), 'keep'으로 표시된 파일")
        return 0

    if args.glob:
        inst.claude_home = args.claude_home
        inst.install(KIT / "global", args.claude_home)
        inst.claude_home = None
        if args.statusline_from:
            inst.install_statusline(args.statusline_from, args.claude_home)
        if args.with_statusline:
            inst.report(f"global → {args.claude_home}")  # 키트 결과를 먼저 보여주고 JS 출력을 이어서 표시
            inst.install_ccstatusline(args.claude_home)
            inst.report("statusline")
        else:
            inst.report(f"global → {args.claude_home}")
    if args.project:
        root = args.project.resolve()
        if not root.is_dir():
            print(f"ERROR: {root} 디렉토리가 없습니다.")
            return 1
        # 프로젝트가 상위 저장소의 하위 폴더일 수 있으므로 위쪽 폴더까지 .git을 찾는다.
        if not any((d / ".git").exists() for d in (root, *root.parents)):
            print(f"WARN: {root}는 git 저장소가 아닙니다. execute.py와 scope_check.py는 git이 필요합니다.")
        inst.install(KIT / "project", root)
        if args.isolated:
            inst.install_isolated(root, args.claude_home)
        inst.report(f"project → {root}")

    if not args.dry_run and args.project:
        py = "py" if os.name == "nt" else "python3"  # Windows는 py 런처 사용
        print("\n다음 단계 (프로젝트 루트에서)")
        print(f"  1. {py} -m pytest -q scripts/            # 키트 테스트 통과 확인")
        print(f"  2. {py} scripts/harness_map.py --with-global  # Health에서 기존 설정 충돌 확인")
        print("  3. .harness-kit/templates/ 의 템플릿을 기존 문서에 수동 병합")
        if args.isolated:
            launcher = "claude-isolated.cmd" if os.name == "nt" else "./claude-isolated.sh"
            print(f"  4. Claude Code는 {launcher} 로 실행 (CLAUDE_CONFIG_DIR={args.claude_home})")
            print("     첫 실행 시 이 설정 폴더용 로그인이 필요할 수 있다. /memory 로 상위 CLAUDE.md 제외 확인")
    return 0


if __name__ == "__main__":
    sys.exit(main())
