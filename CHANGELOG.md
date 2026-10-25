# CHANGELOG

## 2026-10-26 — step 0 우선순위 · scope_check 디렉토리 패턴

근거: PR Autofix 실습 1차 실측(test-harness phase `1-loop-nogate`) 하네스 마찰 · 실장 결정 §8 #6

| 영역 | 결함 | 수정 |
|---|---|---|
| `/harness` | 원칙 1(한 step 한 레이어)이 원칙 8(step 0 = 최소 e2e)과 부딪히면 step 0을 모듈 하나로 자를 수 있음 | 원칙 1에 「step 0은 원칙 8 우선」 명시 |
| scope_check | `/`로 끝나는 허용 패턴(`tests/fixtures/loop/`)이 fnmatch 완전 일치라 하위 파일이 모두 위반 | `/`로 끝나면 디렉토리 접두사로 판정 + 테스트 2개 |

## 2026-10-25 — 첫 정리본

기반: [jha0313/harness_framework](https://github.com/jha0313/harness_framework) + MVP-First Guard

### 구성
| 영역 | 내용 |
|---|---|
| 설치 | `install.py`: 기본 / 독립(`--isolated`) / 프로젝트만, `--dry-run`, `--uninstall`, 설치 기록(manifest) 기반 되돌리기 |
| 글로벌 | MVP-First Guard 규칙, 위험 명령 차단 hook, deny 규칙 |
| 프로젝트 | Scope Lock 규칙, `/harness` `/run-phase` `/review` `/harness-map`, Stop hook, execute.py, scope_check.py, harness_map.py |
| 글로벌 스킬 | `/handoff`: 대화를 다음 세션용 인수인계 문서로 정리 (`/handoff <다음 세션 목적>`, 사용자 호출 전용) |
| 선택 | `--statusline-from`(statusLine 가져오기), `--with-statusline`(ccstatusline 구성, Windows) |
| 검증 | 단위 테스트 131개 (대상/구분/오라클 주석), ruff 기본 규칙 0건 |

### 원본 대비 수정한 결함
| 영역 | 결함 | 수정 |
|---|---|---|
| hook | PreToolUse가 `$CLAUDE_TOOL_INPUT`을 읽고 `exit 1`로 끝나 실제로 차단하지 못함 | stdin JSON, `exit 2` |
| hook | Stop hook에 무한 반복 방지 없음, 실패해도 수정을 이어가지 않음 | `stop_hook_active`, `exit 2` |
| hook | jq가 없으면 차단 hook이 모두 통과시킴 (Windows) | jq 없으면 입력 전체 검사 |
| execute.py | 파일을 OS 기본 인코딩으로 읽음 (한국어 Windows에서 깨짐) | UTF-8 고정 |
| execute.py | `git add -A`가 상위 저장소 전체를 stage | `git add -A -- .` |
| execute.py | PROPOSALS.md(승인 전 제안)가 step 프롬프트에 주입됨 | 주입 제외, step별 `## 참조 문서` 선택 주입 |
| scope_check | 하위 폴더 프로젝트에서 경로 기준이 달라 전부 위반 판정 | `git diff --relative` |
| 설치 | `__pycache__` 등 미추적 캐시 때문에 모든 step이 범위 위반 | `.gitignore`, 설치 대상에서 캐시 제외 |
| 런처 | Windows `.cmd`가 인자 없이 실행하면 문법 오류, cmd 창에 환경변수 누수 | `goto` 분기, `setlocal`, `call` |
| 설치 | 재설치·추가 병합 시 백업이 덮어써지거나 최신 백업을 기준으로 써서 잘못 되돌림 | 같은 실행 내 재백업 금지, 가장 오래된 백업 기준, 중간 백업 보존 |
| 설치 | 독립 프로젝트 재설치 시 글로벌이 `~/.claude`로 바뀌어 기존 환경에 섞임 | 설치 기록의 글로벌 경로 사용, 독립 모드에서 `~/.claude` 거부 |

### 보류한 후보 (필요해지면 진행)
| 후보 | 다시 검토할 시점 |
|---|---|
| 업그레이드 때 직접 수정한 파일 보존 (파일별 해시 기록) | 재설치 때마다 VERIFY 등을 다시 적용하는 수고가 반복될 때 |
| VERIFY 기본값 미설정 + Health 경고, 또는 `--verify` 옵션 | 새 프로젝트마다 Stop hook에 막히는 일이 반복될 때 |
| `.gitattributes`로 `*.sh` LF 고정 | WSL·Linux·macOS에서 같은 저장소를 쓸 때 |
| 저장소 루트까지의 상위 `.claude/commands`·`skills` 중복 탐지 (Harness Map, install.py) | 저장소 안에 하네스 프로젝트를 여러 개 둘 때 |
| `cci` 같은 가까운 런처 자동 탐색 래퍼 | 독립 프로젝트가 두세 개로 늘 때 |
| Windows Terminal 프로필 (JSON fragment) | 위와 같음 |
| 약한 테스트 보강 (checkout 인자, step 재시도 루프, hook 스크립트) | 키트 코드를 다시 수정할 때 |
| docs 변경과 step 설계 시점 불일치 감지 | 첫 phase를 몇 번 실행해 본 뒤 |
| 하네스 Eval (루브릭 채점, 함정 과제) | 하네스 규칙 변경의 효과를 측정해야 할 때 |
