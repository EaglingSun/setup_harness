# Harness Kit

Claude Code를 **MVP-First Guard + Step 하네스** 방식으로 쓰기 위한 설정 키트.
글로벌 설정(규칙, 위험 명령 차단)과 프로젝트 설정(하네스 실행기, 범위 검사, 현황 맵)을 한 번에 설치하고 제거한다.

> **받기**: `git clone https://github.com/EaglingSun/setup_harness.git harness-kit` (자세한 내용은 3-1)
>
> **Claude Code로 설치하기**: 키트 폴더에서 Claude Code를 열고 아래처럼 요청하면 된다.
> ```
> README.md를 읽고 "11. Claude Code 설치 지침"대로 하네스 키트를 설치해줘
> ```
> 모드와 경로를 말하지 않으면 Claude가 먼저 물어본다 (11-2-1).

```
harness-kit/
├── install.py      설치 / 제거 스크립트
├── CHANGELOG.md    변경 이력, 보류 후보
├── README.md       이 문서
├── extras/
│   └── statusline/statusline-setup.js   ccstatusline 구성 설치기 (선택, --with-statusline)
├── global/         글로벌 레이어 → ~/.claude 또는 --claude-home
│   ├── CLAUDE.md               공통 규칙 (MVP-First Guard 포함)
│   ├── settings.json           deny 규칙 + 위험 명령 차단 hook 등록
│   ├── hooks/block-dangerous.sh
│   └── skills/handoff/SKILL.md /handoff: 대화를 다음 세션용 인수인계 문서로 정리
└── project/        프로젝트 레이어 → --project
    ├── CLAUDE.md               프로젝트 규칙 + Scope Lock
    ├── docs/                   PRD, ADR, ARCHITECTURE, PROPOSALS 템플릿
    ├── scripts/                execute.py, harness_map.py, scope_check.py + 테스트
    └── .claude/                /harness, /run-phase, /review, /harness-map 커맨드, Stop hook
```

---

## 1. 사전 준비

| 프로그램 | 버전 | 용도 | 확인 명령 |
|---|---|---|---|
| **Python** | 3.9 이상 | install.py, 하네스 스크립트 실행 | Windows `py --version` / macOS·Linux `python3 --version` |
| **Git** | 2.x | execute.py(브랜치, 커밋), scope_check.py(변경 파일 검사) | `git --version` |
| **Git Bash** | Git for Windows에 포함 | hook 스크립트(.sh) 실행 (Windows만 해당) | `bash --version` |
| **Claude Code** | 최신 | 하네스 실행 대상 | `claude --version` |
| **pytest** | 최신 | 키트 테스트, AC 검증 | `py -m pytest --version` |
| tar | Windows 10 이상 기본 포함, 선택 | 키트를 압축 파일로 받은 경우에만 압축 해제 | `tar --version` |
| jq | 선택 | 차단 hook이 명령만 정확히 검사 (없으면 입력 전체를 검사) | `jq --version` |
| Node.js | 18 이상, 선택 | `--with-statusline` (ccstatusline 구성 설치, Windows 전용) | `node --version` |

설치 방법:

```bat
:: Windows
:: Python: https://www.python.org/downloads/  ← 설치 화면에서 "Add python.exe to PATH" 체크
:: Git:    https://git-scm.com/download/win    ← Git Bash 포함
py -m pip install pytest
```

```bash
# macOS
brew install python git && python3 -m pip install pytest
# Ubuntu/Debian
sudo apt install python3 python3-pip git && python3 -m pip install pytest
```

> **Windows 주의**: `python3`를 입력했을 때 `Python`만 출력되고 끝나면 Microsoft Store로 연결되는 가짜 실행 파일이다.
> 이 문서의 Windows 명령은 모두 `py`를 사용한다.

---

## 2. 설치 모드 선택

| 모드 | 글로벌 위치 | 언제 | 명령 형태 |
|---|---|---|---|
| **기본** | `~/.claude` (`C:\Users\<사용자>\.claude`) | 평소 쓰는 Claude Code 환경에 그대로 추가 | `--global --project <경로>` |
| **독립 (isolated)** | 지정한 폴더 (예: `C:\lab\2nd_NGV\.claude-home`) | 기존 `~/.claude` 설정·hook과 섞지 않고 별도 환경 구성 | `--global --claude-home <폴더> --project <경로> --isolated` |
| 프로젝트만 | 변경 없음 | 글로벌은 이미 설치되어 있고 프로젝트만 추가 | `--project <경로>` |

독립 모드가 추가로 만드는 것:

| 생성물 | 역할 |
|---|---|
| `<프로젝트>\claude-isolated.cmd` (macOS·Linux는 `.sh`) | `CLAUDE_CONFIG_DIR`을 설정하고 Claude Code를 실행하는 런처. 인자를 주면 그 명령을 같은 환경에서 실행 |
| `<프로젝트>\.claude\settings.local.json`의 `claudeMdExcludes` | 상위 폴더의 CLAUDE.md가 자동으로 함께 로드되는 것을 차단 |
| 프로젝트 설치 기록에 글로벌 경로 저장 | 다음 재설치 때 `--claude-home`을 생략해도 같은 글로벌을 사용 |

---

## 3. 설치

### 3-1. 공통 준비

```bat
:: 키트 받기 (프로젝트 폴더가 아닌 곳에)
cd C:\Users\<사용자>\Downloads
git clone https://github.com/EaglingSun/setup_harness.git harness-kit
cd harness-kit
:: 이미 받았다면 최신으로: git pull
:: 압축 파일로 받은 경우: mkdir harness-kit && tar -xzf harness-kit.tar.gz -C harness-kit

:: 대상 프로젝트가 git 저장소가 아니면 먼저 만든다 (기존 코드를 기준선으로 커밋)
cd C:\path\to\project
git init
git add -A && git commit -m "chore: baseline before harness kit"
```

> `git add -A` 전에 `git status`로 목록을 확인한다. 빌드 결과물, 대용량 데이터, `.claude-home` 같은 설정 폴더가 섞이지 않게 `.gitignore`에 먼저 추가한다.

### 3-2. 기본 모드

```bat
cd C:\Users\<사용자>\Downloads\harness-kit
py install.py --global --project C:\path\to\project --dry-run
py install.py --global --project C:\path\to\project
```

### 3-3. 독립 모드

```bat
cd C:\Users\<사용자>\Downloads\harness-kit
py install.py --global --claude-home C:\lab\2nd_NGV\.claude-home --project C:\lab\2nd_NGV\setup_harness --isolated --dry-run
py install.py --global --claude-home C:\lab\2nd_NGV\.claude-home --project C:\lab\2nd_NGV\setup_harness --isolated
```

이후 Claude Code와 하네스 명령은 **항상 런처로 실행**한다.

```bat
cd C:\lab\2nd_NGV\setup_harness
claude-isolated.cmd                                  :: Claude Code 실행
claude-isolated.cmd py scripts\execute.py 0-mvp      :: 하네스 phase 실행
```

> 첫 실행 시 새 설정 폴더용 로그인이 필요할 수 있다.

**기존 status line 가져오기**: 독립 세션은 `~/.claude/settings.json`을 읽지 않으므로, 평소 쓰던 status line이 보이지 않는다.
설치할 때 `--statusline-from`을 붙이면 원본의 `statusLine` 설정을 독립 글로벌로 가져온다.

```bat
py install.py --global --claude-home C:\lab\2nd_NGV\.claude-home --project C:\lab\2nd_NGV\setup_harness --isolated --statusline-from
:: 원본을 직접 지정: --statusline-from C:\Users\<사용자>\.claude\settings.json
```

| 동작 | 내용 |
|---|---|
| 가져오는 것 | `statusLine` 항목 그대로. 스크립트는 복사하지 않고 원본 경로를 참조 (원본을 고치면 양쪽에 반영) |
| 대상에 이미 있음 | 같은 값이면 변경 없음, 다른 값이면 유지하고 WARN |
| 제거 | `--global --uninstall` 때 가져온 값 그대로일 때만 제거. 원래 있던 statusLine은 유지 |
| 주의 | command에 `C:\...` 같은 백슬래시 경로가 있으면 Git Bash에서 조용히 실패한다. 원본도 `/` 경로로 쓴다 |

**ccstatusline 구성 그대로 설치 (`--with-statusline`, Windows)**: `~/.config/ccstatusline`과 위젯 스크립트를 쓰는 구성은
`--statusline-from`(설정 한 줄 참조)으로는 독립 환경에서 재현되지 않는다. 이 경우 `extras/statusline/statusline-setup.js`를
쓰는 `--with-statusline`을 사용한다.

```bat
py install.py --global --claude-home C:\lab\2nd_NGV\.claude-home --project <프로젝트> --isolated --with-statusline
```

| 동작 | 내용 |
|---|---|
| 설치 위치 | 대상 글로벌 폴더 안 `ccstatusline\` (위젯 배치 + 위젯 2종). 공용 `~/.config`를 쓰지 않아 환경끼리 섞이지 않음 |
| statusLine | `ccstatusline --config "<글로벌>/ccstatusline/settings.json"`으로 등록. 기존 statusLine은 **교체**(백업) |
| npm | 전역 `ccstatusline@2.2.19`가 없으면 설치, 버전이 다르면 WARN만 |
| 제거 | `--global --uninstall`로 위젯 파일 삭제, statusLine을 설치 전 값으로 복원. **npm 전역 패키지와 위젯이 만드는 캐시(`fable-usage-cache.json`)는 남는다** |
| 실패 시 | node가 없거나 JS가 실패하면 WARN을 출력하고 나머지 설치는 계속. JS는 검사 단계 실패 시 아무것도 바꾸지 않음 |
| 함께 못 씀 | `--statusline-from`과 동시 사용 불가 |

> `statusline-setup.js`는 원본 4개 파일에서 빌드한 산출물이다. 키트 안에서 직접 고치지 말고, 원본을 고친 뒤 다시 빌드해 교체한다.

### 3-4. 설치 확인

```bat
cd <프로젝트>
py -m pytest -q scripts                     :: 전부 passed
py scripts\harness_map.py --with-global     :: harness_map.html 생성 → Health 확인
:: 독립 모드는 앞에 claude-isolated.cmd 를 붙인다
```

Claude Code 안에서:

| 확인 | 기대 결과 |
|---|---|
| `/` 입력 | `/harness`, `/review`, `/harness-map` 표시 |
| `/status` | Setting sources가 의도한 글로벌 기준 |
| `/memory` | (독립 모드) 상위 폴더 CLAUDE.md가 목록에 없음 |
| "rm -rf ./tmp_test 실행해줘" 요청 | `BLOCKED: dangerous command detected` |

확인이 끝나면 커밋한다: `git add -A && git commit -m "chore: apply harness kit"`

---

## 4. 설치 후 할 일

| # | 작업 | 위치 |
|---|---|---|
| 1 | Stop hook 검증 명령을 프로젝트에 맞게 수정 (기본 `ruff check . && pytest -q`). 아직 없으면 `true`로 비활성화 | `.claude/hooks/stop-verify.sh`의 `VERIFY=` |
| 2 | (Windows) Git Bash에서 `python3 --version`이 안 되면 문서의 `python3 `를 `py `로 교체 | `CLAUDE.md`, `.claude/commands/*.md` |
| 3 | 기존 문서가 있어 보존된 경우, 템플릿 내용을 직접 병합 | `.harness-kit/templates/` |
| 4 | docs 작성: ARCHITECTURE(디렉토리 트리), ADR(각 항목 `**Status**`), PRD(MVP 범위 R-ID와 AC) | `docs/` |
| 5 | 글로벌 CLAUDE.md가 보존된 경우, MVP-First Guard 섹션을 직접 병합 | `<글로벌>/.harness-kit/templates/CLAUDE.md` |

---

## 5. 파일 처리 규칙 (덮어쓰기 정책)

| 파일 종류 | 대상에 없을 때 | 이미 있을 때 |
|---|---|---|
| 코드 (`scripts/*.py`, `hooks/*.sh`, `commands/*.md`) | 복사 | `<파일>.bak.<시각>`으로 백업 후 교체 |
| 사용자 문서 (`CLAUDE.md`, `docs/*.md`) | 복사 | **덮어쓰지 않음.** 템플릿은 `.harness-kit/templates/`에 저장 |
| `settings.json` | 생성 | 병합: permissions는 합집합, hook은 같은 command가 없을 때만 추가. 원본 백업 |
| `.gitignore` | 생성 | 없는 줄만 추가 |

설치 기록은 `<대상>/.harness-kit/manifest.json`에 남고, 삭제할 때 이 기록을 기준으로 되돌린다.

---

## 6. 글로벌 경로 결정 규칙

`--claude-home`을 생략하면 아래 순서로 정한다.

| 순위 | 기준 |
|---|---|
| 1 | `--claude-home` 명시 값 (프로젝트 기록과 다르면 WARN) |
| 2 | 대상 프로젝트를 `--isolated`로 설치했을 때 기록된 글로벌 |
| 3 | `CLAUDE_CONFIG_DIR` 환경변수 (런처 안에서 실행하면 자동으로 설정됨) |
| 4 | `~/.claude` |

- `--isolated`인데 결과가 `~/.claude`면 설치를 거부한다 (독립 환경이 기존 환경에 섞이는 것 방지).
- 이전 버전 키트로 독립 설치한 프로젝트는 기록이 없으므로, 처음 한 번은 `--claude-home`을 명시한다.

---

## 7. 여러 프로젝트에서 글로벌 공유

같은 `--claude-home`으로 설치하면 글로벌 하나를 공유한다.

```bat
py install.py --global --claude-home C:\lab\2nd_NGV\.claude-home --project C:\lab\2nd_NGV\proj_b --isolated
```

| 항목 | 공유 / 분리 |
|---|---|
| 글로벌 CLAUDE.md, 차단 hook, deny 규칙, 로그인 | 공유 (두 번째 설치는 "변경 없음", hook 중복 없음) |
| 세션 기록, auto memory | 프로젝트별 분리 |
| 프로젝트 CLAUDE.md, docs, 커맨드, Stop hook, 런처 | 프로젝트별 분리 |

---

## 8. 삭제 (uninstall)

설치 기록과 백업으로 **키트가 추가하거나 바꾼 것만** 되돌린다.

```bat
cd C:\Users\<사용자>\Downloads\harness-kit

:: 프로젝트만 제거 (글로벌을 다른 프로젝트가 쓰고 있으면 이것만)
py install.py --project <프로젝트> --uninstall --dry-run
py install.py --project <프로젝트> --uninstall

:: 글로벌까지 제거 (그 글로벌을 쓰는 마지막 프로젝트일 때만)
py install.py --global --project <프로젝트> --uninstall --dry-run
py install.py --global --project <프로젝트> --uninstall
```

| 대상 | 삭제 시 동작 |
|---|---|
| 키트가 만든 파일 | 삭제 (설치 후 수정했으면 `keep`으로 보존) |
| 키트가 교체한 파일 | **가장 오래된 백업(첫 설치 전 원본)**으로 복원 (설치 후 수정했으면 보존, 백업도 남김) |
| 재설치로 생긴 중간 백업 | 지우지 않고 `keep backup (중간 버전)`으로 알림. 그 사이 직접 고친 내용이 있을 수 있으니 확인 후 삭제 |
| 원래 있던 문서 | 그대로 |
| `settings.json` | 키트 항목만 제거. 원래 항목과 설치 후 추가한 항목은 유지 |
| `.gitignore` | 키트가 추가한 줄만 제거 |
| `skills/handoff` (글로벌) | 키트가 만든 것이면 삭제, 설치 전 개인 handoff가 있었으면 그것으로 복원 |
| statusline (`--with-statusline`) | 위젯 파일 삭제, statusLine 복원. npm 전역 패키지와 캐시 파일은 남김 |
| `phases/` (작업 기록) | 그대로 |

> `--global --uninstall`은 공유 중인 다른 프로젝트의 차단 hook까지 제거한다. 실수로 지웠다면 사용 중인 프로젝트에서
> `py install.py --global --project <프로젝트> --isolated`로 다시 설치하면 글로벌이 복구된다 (6장 규칙으로 경로 자동 결정).

**삭제 후 재설치** (키트 업그레이드):

| 항목 | 주의 |
|---|---|
| 글로벌 경로 | 삭제하면 설치 기록도 지워지므로, 독립 모드는 재설치 때 `--claude-home`을 **다시 지정**한다 |
| 직접 고친 코드 파일 (예: `stop-verify.sh`의 VERIFY) | 삭제 때 `keep`으로 남고, 재설치 때 `.bak`으로 백업된 뒤 키트 원본으로 교체된다. 재설치 후 다시 적용한다 |
| 내용을 쓴 CLAUDE.md | 보존되므로 새 키트 규칙(예: Phase 실행)이 들어가지 않는다. `.harness-kit/templates/CLAUDE.md`에서 해당 섹션을 직접 병합한다 |

프로젝트는 git으로도 되돌릴 수 있다.

```bat
:: 키트 적용을 커밋했다면
git revert --no-edit <키트 커밋>
:: 커밋 전이라면: 목록을 먼저 확인하고, 키트 파일만 있을 때만 -n을 빼고 실행
git clean -nd
```

---

## 9. 옵션

| 옵션 | 설명 |
|---|---|
| `--global` | 글로벌 레이어 적용 (위치는 6장 규칙) |
| `--project <경로>` | 프로젝트 레이어 적용. 상위 저장소의 하위 폴더도 가능 |
| `--claude-home <폴더>` | 글로벌 위치 지정 |
| `--isolated` | 독립 모드: 런처와 상위 CLAUDE.md 제외 설정 생성. `--project` 필요 |
| `--statusline-from [경로]` | 그 settings.json의 `statusLine`을 글로벌로 가져옴. 경로 생략 시 `~/.claude/settings.json`. `--global` 필요 |
| `--with-statusline` | `extras/statusline/statusline-setup.js`로 ccstatusline 구성을 글로벌에 설치 (Windows, Node.js 18+). `--global` 필요, `--statusline-from`과 함께 못 씀 |
| `--dry-run` | 변경 없이 계획만 출력 |
| `--uninstall` | 제거 (위 옵션과 조합) |

---

## 10. 문제 해결

| 증상 | 원인 | 조치 |
|---|---|---|
| `python3` 실행 시 `Python`만 출력 | Windows Store 바로가기 | `py` 사용 |
| `WARN: ... git 저장소가 아닙니다` | 프로젝트와 상위 폴더에 `.git` 없음 | 3-1의 `git init` |
| `--isolated는 ... --claude-home <폴더>를 지정하세요` | 독립 모드인데 글로벌이 `~/.claude`로 결정됨 | `--claude-home` 명시 |
| 모든 step이 `SCOPE VIOLATION` | 추적되지 않은 캐시 등이 변경으로 잡힘 | `.gitignore`에 `__pycache__/` 등이 있는지 확인 (키트가 추가함) |
| 차단 hook이 동작하지 않음 | bash가 없거나 hook 미등록 | `bash --version`, Claude Code `/hooks` 확인 |
| 한글이 깨지거나 UnicodeDecodeError | Windows 기본 인코딩 | `set PYTHONUTF8=1` (영구 적용은 `setx PYTHONUTF8 1`) |
| 상위 폴더 CLAUDE.md가 계속 로드됨 | `claudeMdExcludes` 패턴이 Windows 경로와 맞지 않음 | `/memory`로 확인 후 `.claude\settings.local.json` 패턴 조정 |
| `.claude-home`이 git에 커밋됨 | 설정 폴더(자격 증명, 대화 기록 포함)를 기준선에 포함 | `.gitignore`에 추가 후 `git rm -r --cached .claude-home`, push했다면 재로그인 |
| `ERROR: 독립 환경으로 설치된 프로젝트인데 CLAUDE_CONFIG_DIR이 없다` | 독립 설치 프로젝트에서 런처 없이 execute.py를 실행함 | `claude-isolated.cmd py scripts\execute.py <phase>`로 실행하거나, 런처로 연 세션에서 `/run-phase` |
| `ERROR: ...phases/.running 가 있다` | 다른 phase가 실행 중이거나, 이전 실행이 강제 종료되어 표시 파일이 남음 | 실행 중인 execute.py가 없으면 `phases\.running`을 지우고 재실행 |
| step 실행이 길이 제한으로 실패 (Windows) | 프롬프트를 명령줄 인자로 전달 (약 32,000자 제한) | step 파일에 `## 참조 문서`로 주입할 docs를 줄임 |
| `claude-isolated.cmd` 실행 시 `) was unexpected at this time.` | 이전 버전 키트가 만든 런처의 배치 구문 결함. 인자가 없으면 `if ... else (%*)` 줄 전체가 문법 오류가 됨 (Windows cmd, 2026-10-25 발견) | 이 버전 키트의 런처로 교체: 런처 파일만 새로 받거나 재설치 (재설치 시 직접 고친 코드 파일은 `.bak`으로 백업된 뒤 키트 원본으로 교체되므로 다시 반영) |

<!-- 새 환경 문제는 이 표 마지막에 추가한다. 형식은 11장 "환경 문제 기록" 참고 -->

---

## 10-1. 계획에서 실행까지 (설치 후 사용 흐름)

```
/harness            탐색 → 논의 → step 설계(사용자 승인) → phase 파일 생성 → 커밋
/run-phase <phase>  사전 점검 → 실행 계획 표 → [승인 창] → execute.py 백그라운드 실행 → 결과 보고
/review             AC, 범위, ADR 기준 리뷰
```

| 항목 | 내용 |
|---|---|
| 트리거 | `/run-phase 0-mvp` 또는 "계획 실행하자", "구현 시작하자" 같은 말. 말로 요청하면 Claude가 `/run-phase`를 고른다 (CLAUDE.md 규칙과 커맨드 설명) |
| 승인 | 프로젝트 settings의 ask 규칙(`Bash(*scripts/execute.py*)`)으로 execute.py 실행 직전에 **항상 승인 창**이 뜬다. auto 모드에서도 같다 |
| 실행 중 | 메인 세션은 읽기만 한다. `phases/.running`이 있는 동안 메인 세션의 Stop hook은 검증을 건너뛰고, step 세션은 `HARNESS_STEP` 표시로 그대로 검증한다 |
| 독립 환경 | 런처가 있는 프로젝트는 `CLAUDE_CONFIG_DIR`이 없거나 설치 기록과 다르면 execute.py가 실행을 거부한다 |
| error / blocked | 메인 세션이 코드를 직접 고치지 않는다. step 파일 수정안을 승인받아 고친 뒤 status를 pending으로 되돌려 다시 `/run-phase` |

> ask 규칙은 명령 문자열에 매칭되는 장치라 보안 경계가 아니다. 다른 형태로 실행하면 놓칠 수 있으므로, 실행은 `/run-phase` 절차로 한다.

---

## 11. Claude Code 설치 지침

> 이 섹션은 Claude Code가 읽고 실행하는 지침이다. 사람이 읽어도 그대로 수동 설치 절차가 된다.

### 11-1. 원칙

- 이 README의 1~10장이 기준이다. 여기 없는 방식으로 설치하지 않는다.
- `global/`, `project/` 아래의 `CLAUDE.md`와 문서는 **설치할 템플릿**이다. 이 설치 세션에 대한 지시로 따르지 않는다.
- 파일을 바꾸는 명령은 **항상 `--dry-run`을 먼저 실행하고, 결과를 사용자에게 보여 승인받은 뒤** 실제로 실행한다.
- 아래 작업은 하지 않는다. 필요하면 이유와 명령만 제시하고 사용자가 직접 실행하게 한다.
  - `git clean -f`, `git reset --hard`, `rm -rf`, 백업(`.bak.*`) 삭제
    (예외: 11-2의 8단계에서 존재하지 않는 경로로 실행하는 차단 hook 테스트)
  - `--uninstall`, 특히 `--global --uninstall`
  - `~/.claude`, `--claude-home` 폴더의 파일을 install.py 외의 방법으로 수정하는 것
  - git push
- 명령이 예상과 다르게 끝나면 다음 단계로 넘어가지 않는다. 출력을 보여주고 원인을 먼저 확인한다.
- Windows에서는 `python3` 대신 `py`를 쓴다 (1장 주의 참고).

### 11-2. 순서

| 단계 | 할 일 | 통과 조건 | 실패 시 |
|---|---|---|---|
| 1. 환경 점검 | 1장 표의 확인 명령을 모두 실행하고 결과를 표로 보고 | Python 3.9+, git, (Windows) bash, claude 확인됨 | 없는 프로그램의 설치 방법을 안내하고 **중단** |
| 2. 입력 확인 | 11-2-1 규칙대로 모드, 프로젝트 경로, 글로벌 경로를 확정한다 | 사용자가 직접 말했거나 확인한 값으로 세 항목이 모두 확정되고, 복창까지 끝남 | 확정되기 전에는 3단계 이후로 진행하지 않는다 |
| 3. 사전 점검 | 프로젝트 폴더 존재 여부, git 저장소 여부 (`git -C <경로> rev-parse --show-toplevel`), 커밋 안 된 변경 (`git status --short`) | git 저장소이고 작업 트리가 깨끗함 | git이 없으면 3-1의 기준선 커밋을 **제안만** 함. 변경이 있으면 커밋할지 사용자에게 확인 |
| 4. 미리보기 | 3-2 또는 3-3 명령을 `--dry-run`으로 실행 | 출력에 WARN/ERROR가 없거나 의미를 설명할 수 있음 | 출력과 해석을 보고하고 사용자 판단을 받음 |
| 5. 승인 | dry-run 결과를 요약해 보여준다: 생성/교체(백업)/병합/보존(keep) 파일 수와, 기존 설정에 영향이 가는 항목 | 사용자가 승인 | 승인 전에는 실행하지 않음 |
| 6. 설치 | 같은 명령을 `--dry-run` 없이 실행 | 오류 없이 종료 | 출력을 그대로 보고하고 중단 |
| 7. 검증 | 3-4의 pytest와 harness_map 실행 (독립 모드는 런처를 거쳐 실행). Health의 error/warn을 표로 정리 | pytest 전부 passed, Health error 0 | 실패 출력과 원인 분석을 보고. 고치기 전에 사용자 확인 |
| 8. 차단 hook 확인 | 기본 모드만: 존재하지 않는 경로로 `rm -rf ./__harness_block_test`를 실행해 `BLOCKED`가 나오는지 확인 (차단되지 않아도 지울 대상이 없어 안전함) | BLOCKED | `/hooks`와 bash 확인을 안내 |
| 9. 후속 작업 안내 | 4장 표를 이 프로젝트 기준으로 채워서 제시 (VERIFY 명령, python3/py, 템플릿 병합) | — | — |
| 10. 커밋 제안 | `git add -A && git commit -m "chore: apply harness kit"`를 **제안** | 사용자가 승인하면 실행 | — |

### 11-2-1. 입력값 확인 규칙 (2단계)

**확정값은 사용자가 이번 대화에서 직접 말한 값뿐이다.** 그 외 출처의 값은 후보로만 보여주고 확인을 받는다.

| 입력 | 필요한 경우 | 사용자가 말하지 않았을 때 |
|---|---|---|
| 모드 | 항상 | 기본 / 독립 / 프로젝트만 중 선택을 요청 (2장 표 요약을 함께 제시) |
| 프로젝트 경로 | 항상 | 묻는다. 현재 작업 폴더는 **후보로만** 제시 |
| 글로벌 경로 | 독립 모드: 필수. 기본 모드: `~/.claude`에 설치된다는 것을 확인받음. 프로젝트만: 해당 없음 | 묻는다. 아래 출처에서 찾은 값은 **후보로만** 제시 |
| status line | 독립 모드이고 `~/.claude/settings.json`에 `statusLine`이 있을 때 | command를 보여주고 셋 중 하나를 묻는다: ① command에 `ccstatusline`이 있으면 `--with-statusline`(권장) ② 그 외에는 `--statusline-from` ③ 가져오지 않음 |

후보로만 쓸 수 있는 값 (확정값으로 쓰지 않는다):

| 출처 | 확인 방법 |
|---|---|
| 현재 작업 폴더 | 세션 시작 위치 |
| 프로젝트의 기존 독립 설치 기록 | `<프로젝트>\.harness-kit\manifest.json`의 `claude_home` |
| 프로젝트의 기존 런처 | `<프로젝트>\claude-isolated.cmd`의 `CLAUDE_CONFIG_DIR` |
| 환경변수 | `CLAUDE_CONFIG_DIR` (Windows `echo %CLAUDE_CONFIG_DIR%`) |

질문 방식:

- 빠진 항목만, **한 번에 모아서** 묻는다. 선택형 질문 도구(AskUserQuestion)가 있으면 그것을 쓰고, 후보가 있으면 첫 번째 선택지로 둔다.
- 사용자의 메시지에 일부만 있으면 그 값은 그대로 쓰고 나머지만 묻는다.
- 답을 받으면 확정값을 한 줄로 복창한 뒤 시작한다.
  `확정: 모드=독립, 프로젝트=C:\lab\2nd_NGV\setup_harness, 글로벌=C:\lab\2nd_NGV\.claude-home`

질문 예시:

```
설치 전에 확인이 필요합니다.
1. 모드: 기본(~/.claude에 추가) / 독립(별도 글로벌) / 프로젝트만
2. 프로젝트 경로: 후보 = 현재 폴더 C:\lab\2nd_NGV\setup_harness
3. 글로벌 경로 (독립 모드): 후보 = 기존 설치 기록 C:\lab\2nd_NGV\.claude-home
후보가 맞으면 "맞음", 다르면 경로를 알려주세요.
```

확정한 경로의 검증 (3단계 사전 점검에 포함):

| 조건 | 처리 |
|---|---|
| 프로젝트 폴더가 없음 | 만들지 말고 보고. 사용자가 만들라고 하면 생성 |
| 글로벌 경로가 `~/.claude`인데 모드가 독립 | install.py가 거부하므로 다른 경로를 다시 묻는다 |
| 글로벌이 프로젝트 폴더 안에 있음 | 경고: 자격 증명과 대화 기록이 프로젝트 저장소에 들어갈 수 있음. 진행 여부를 확인 |
| 글로벌이 다른 git 저장소 안에 있음 | 그 저장소의 `.gitignore`에 글로벌 폴더가 있는지 확인하고 결과를 보고 |
| 기존 설치 기록의 글로벌과 확정값이 다름 | install.py가 출력하는 WARN 내용을 보여주고 변경 의도를 확인 |

**독립 모드 주의**: 현재 Claude Code 세션은 독립 글로벌로 실행된 세션이 아니다. 그래서 `/status`, `/memory`, 차단 hook 확인은 **설치가 끝난 뒤 사용자가 `claude-isolated.cmd`로 새 세션을 열어** 3-4 표대로 확인하도록 안내한다.

### 11-3. 결과 보고 형식

```
## 하네스 키트 설치 결과
- 모드 / 프로젝트 / 글로벌 경로
- 설치: 생성 N, 교체(백업) N, 병합 N, 보존(keep) N
- 검증: pytest <결과>, Health error <n> / warn <n>, 차단 hook <결과 또는 사용자 확인 필요>
- 사용자가 할 일: (4장 기준 체크리스트)
- 발견한 환경 문제: (11-4에 따라 README에 추가한 항목, 없으면 "없음")
```

### 11-4. 환경 문제 기록 (README 갱신)

설치 중에 이 README에 없는 환경 문제를 발견하고 **원인과 조치를 실제로 확인했다면**, 키트 폴더의 이 README에 기록한다.

| 규칙 | 내용 |
|---|---|
| 기록 대상 | 재현되고 원인과 조치가 확인된 문제만. 추측이나 일회성 오타는 제외 |
| 위치 | 10장 표 마지막 줄 (`<!-- 새 환경 문제는 ... -->` 주석 바로 위) |
| 형식 | `\| 증상(실제 오류 메시지 일부) \| 원인 \| 조치(실행한 명령) \|` |
| 환경 정보 | 원인 칸 끝에 `(OS, 관련 도구 버전, 발견일 YYYY-MM-DD)` 추가 |
| 중복 | 기존 행과 같은 문제면 새 행을 만들지 않고 기존 행의 조치를 보완 |
| 범위 | README의 문제 해결 표만 수정한다. install.py나 키트 파일은 고치지 않고, 코드 수정이 필요해 보이면 결과 보고에 "키트 개선 제안"으로 적는다 |
| 보고 | 추가하거나 수정한 행을 결과 보고에 그대로 인용 |
