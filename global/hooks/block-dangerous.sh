#!/usr/bin/env bash
# PreToolUse(Bash) guard. Hook input arrives as JSON on stdin; exit 2 blocks the call.
#
# 등록: ~/.claude/settings.json → hooks.PreToolUse[matcher=Bash]
# 입력: {"tool_name":"Bash","tool_input":{"command":"..."}, ...}  (stdin)
# 출력: 차단 시 stderr 메시지가 Claude에게 전달된다.
# 종료 코드: 0 = 허용, 2 = 차단 (1은 차단하지 않고 오류로만 표시되므로 쓰지 않는다)
# 의존: 없음 (jq가 있으면 command만 정확히 검사, 없으면 입력 JSON 전체를 검사)
#
# 차단 패턴
#   rm -rf / rm -fr 등 r과 f 플래그 조합
#   git push --force / -f
#   git reset --hard
#   DROP TABLE / DROP DATABASE / TRUNCATE TABLE (대소문자 무시)
input=$(cat)
if command -v jq >/dev/null 2>&1; then
  cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // ""')
else
  # jq가 없으면(Windows 기본 환경 등) 원본 JSON 전체를 검사한다.
  # 다른 필드의 문자열까지 매칭될 수 있어 더 보수적이지만, 검사를 건너뛰어 모두 통과시키는 것보다 안전하다.
  cmd=$input
fi

if echo "$cmd" | grep -qiE 'rm[[:space:]]+-[a-z]*r[a-z]*f|git[[:space:]]+push[[:space:]].*(--force|-f\b)|git[[:space:]]+reset[[:space:]]+--hard|DROP[[:space:]]+(TABLE|DATABASE)|TRUNCATE[[:space:]]+TABLE'; then
  echo "BLOCKED: dangerous command detected: $cmd" >&2
  exit 2
fi
exit 0
