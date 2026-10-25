#!/usr/bin/env node
/*
 * statusline-setup.js — Claude Code statusline(ccstatusline + 위젯 2종)을 다른 설정 폴더에 같은 모양으로 세팅한다.
 *
 * 사용법 (Windows, Node.js 18 이상)
 *   node statusline-setup.js                         대상 = CLAUDE_CONFIG_DIR, 없으면 %USERPROFILE%\.claude
 *   node statusline-setup.js --claude-home <폴더>    대상 설정 폴더 지정 (예: 독립 환경 C:\lab\2nd_NGV\.claude-home)
 *   node statusline-setup.js ... --dry-run           변경 없이 계획만 출력
 *
 * 설치하는 것 (모두 <설정 폴더> 안 — 다른 설정 폴더와 섞이지 않는다)
 *   settings.json                        statusLine 등록. 다른 키는 그대로 두고, 기존 파일은 .bak.<시각> 으로 백업
 *   ccstatusline/settings.json           위젯 배치. statusLine 이 ccstatusline --config 로 이 파일을 읽는다
 *   ccstatusline/ccstatusline-ctx.ps1    컨텍스트 사용률 위젯 ("Ctx Used: N%")
 *   ccstatusline/ccstatusline-fable.ps1  Fable 주간 한도 위젯 ("Fable Wk: N%") — 이 설정 폴더의 로그인 정보를 읽는다
 *   npm 전역 ccstatusline@{버전}         없을 때만 설치. 버전이 다르면 WARN 만 낸다
 *
 * 되돌리기: <설정 폴더>\ccstatusline\ 을 지우고 settings.json.bak.<시각> 으로 settings.json 을 복원한다.
 * 종료 코드: 0 = 성공, 1 = 오류 (검사 단계 오류는 아무것도 바꾸지 않고 끝난다)
 */
'use strict';
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');

// --- 아래는 build.py 가 원본에서 생성한 내용 (2.2.19 기준) ---
const CCSTATUSLINE_VERSION = "2.2.19";
const STATUSLINE_BASE = {
  "type": "command",
  "command": "ccstatusline",
  "padding": 0,
  "refreshInterval": 10
};
const LAYOUT = {
  "version": 3,
  "lines": [
    [
      {
        "id": "1",
        "type": "current-working-dir",
        "color": "cyan"
      },
      {
        "id": "2",
        "type": "separator"
      },
      {
        "id": "3",
        "type": "model",
        "color": "brightCyan"
      },
      {
        "id": "4",
        "type": "separator"
      },
      {
        "id": "5",
        "type": "thinking-effort",
        "color": "yellow"
      },
      {
        "id": "6",
        "type": "separator"
      },
      {
        "id": "7",
        "type": "custom-command",
        "commandPath": "{{WIDGET:ccstatusline-ctx.ps1}}",
        "preserveColors": true,
        "timeout": 4000
      },
      {
        "id": "8",
        "type": "separator"
      },
      {
        "id": "9",
        "type": "session-usage",
        "color": "green"
      },
      {
        "id": "10",
        "type": "separator"
      },
      {
        "id": "11",
        "type": "weekly-usage",
        "color": "green"
      },
      {
        "id": "25",
        "type": "separator"
      },
      {
        "id": "26",
        "type": "custom-command",
        "commandPath": "{{WIDGET:ccstatusline-fable.ps1}}",
        "preserveColors": true,
        "timeout": 4000
      },
      {
        "id": "12",
        "type": "separator"
      },
      {
        "id": "13",
        "type": "session-cost",
        "color": "green"
      },
      {
        "id": "23",
        "type": "separator"
      },
      {
        "id": "24",
        "type": "tokens-total",
        "color": "green"
      }
    ],
    [
      {
        "id": "14",
        "type": "git-branch",
        "color": "magenta"
      },
      {
        "id": "15",
        "type": "separator"
      },
      {
        "id": "16",
        "type": "git-pr",
        "color": "yellow"
      },
      {
        "id": "17",
        "type": "separator"
      },
      {
        "id": "18",
        "type": "reset-timer",
        "color": "brightBlack"
      },
      {
        "id": "19",
        "type": "separator"
      },
      {
        "id": "20",
        "type": "weekly-reset-timer",
        "color": "brightBlack"
      },
      {
        "id": "21",
        "type": "separator"
      },
      {
        "id": "22",
        "type": "block-timer",
        "color": "brightBlack"
      }
    ],
    []
  ],
  "flexMode": "full-minus-40",
  "compactThreshold": 60,
  "colorLevel": 2,
  "inheritSeparatorColors": false,
  "globalBold": false,
  "gitCacheTtlSeconds": 5,
  "minimalistMode": false,
  "powerline": {
    "enabled": false,
    "separators": [
      ""
    ],
    "separatorInvertBackground": [
      false
    ],
    "startCaps": [],
    "endCaps": [],
    "autoAlign": false,
    "continueThemeAcrossLines": false
  }
};
const WIDGETS = {
  "ccstatusline-ctx.ps1": "# ccstatusline custom-command widget: threshold-colored \"Ctx Used: N%\"\n# stdin: Claude Code session JSON (ccstatusline pipes context.data here).\n# Thresholds: <30% green, <50% yellow, <70% red, >=70% bright red.\n# NOTE: $([char]27) for ESC — Windows PowerShell 5.1 has no `e escape.\ntry { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}\n\n$e = [char]27\n$raw = $null\ntry {\n    if (-not [Console]::IsInputRedirected) { exit 0 }\n    # Read stdin as UTF-8 bytes directly — [Console]::In decodes with the OEM\n    # codepage (cp949), mangling Korean payload strings (e.g. session_name)\n    # and breaking ConvertFrom-Json.\n    $reader = New-Object System.IO.StreamReader([Console]::OpenStandardInput(), [System.Text.Encoding]::UTF8)\n    $raw = $reader.ReadToEnd()\n} catch { exit 0 }\nif ([string]::IsNullOrWhiteSpace($raw)) { exit 0 }\n\n$data = $null\ntry { $data = $raw | ConvertFrom-Json } catch { exit 0 }\n\n# Prefer explicit used_percentage; fall back to token-count calculation.\n$usedPct = $null\ntry { $usedPct = [double]$data.context_window.used_percentage } catch {}\nif ($null -eq $usedPct) {\n    try {\n        $cu   = $data.context_window.current_usage\n        $size = [double]$data.context_window.context_window_size\n        if ($cu -and $size -gt 0) {\n            $used = [double]$cu.input_tokens `\n                  + [double]$cu.cache_creation_input_tokens `\n                  + [double]$cu.cache_read_input_tokens\n            $usedPct = [Math]::Round($used / $size * 100, 1)\n        }\n    } catch {}\n}\nif ($null -eq $usedPct) { exit 0 }\n\nif     ($usedPct -lt 30) { $col = \"$e[32m\" }   # green\nelseif ($usedPct -lt 50) { $col = \"$e[33m\" }   # yellow\nelseif ($usedPct -lt 70) { $col = \"$e[31m\" }   # red\nelse                     { $col = \"$e[91m\" }   # bright red\n\n$reset = \"$e[0m\"\n$txt   = \"{0:F1}\" -f $usedPct\nWrite-Output \"${col}Ctx Used: ${txt}%${reset}\"\n",
  "ccstatusline-fable.ps1": "# ccstatusline custom-command widget: Fable weekly rate-limit \"Fable Wk: N%\"\n# Data: OAuth usage API limits[] entry kind=weekly_scoped, scope model \"Fable\".\n# This bucket is NOT in the statusline payload's rate_limits (only five_hour /\n# seven_day come through), so it is fetched directly with a 300s file cache.\n# Thresholds match ccstatusline-ctx.ps1: <30% green, <50% yellow, <70% red, >=70% bright red.\n# NOTE: $([char]27) for ESC — Windows PowerShell 5.1 has no `e escape.\ntry { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}\n\n# Drain stdin (ccstatusline pipes the session JSON; unused here).\ntry { if ([Console]::IsInputRedirected) { [void][Console]::In.ReadToEnd() } } catch {}\n\n$e = [char]27\n$reset = \"$e[0m\"\n# Config dir = parent of this script's folder (<config dir>\\ccstatusline), so an isolated\n# CLAUDE_CONFIG_DIR environment reads its own login and cache instead of ~/.claude.\n$claudeDir = Split-Path $PSScriptRoot -Parent\n$cacheFile = Join-Path $claudeDir 'fable-usage-cache.json'\n$credsFile = Join-Path $claudeDir '.credentials.json'\n$maxAgeSec = 300\n$nowUtc = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()\n\n$usage = $null\ntry {\n    $cached = Get-Content $cacheFile -Raw -Encoding UTF8 -ErrorAction Stop | ConvertFrom-Json\n    if (($nowUtc - [int64]$cached.ts) -lt $maxAgeSec) { $usage = $cached.data }\n} catch {}\n\nif ($null -eq $usage) {\n    try {\n        $tok = (Get-Content $credsFile -Raw -Encoding UTF8 -ErrorAction Stop | ConvertFrom-Json).claudeAiOauth.accessToken\n        if (-not [string]::IsNullOrWhiteSpace($tok)) {\n            $usage = Invoke-RestMethod -Uri 'https://api.anthropic.com/api/oauth/usage' `\n                -Headers @{ Authorization = \"Bearer $tok\"; 'anthropic-beta' = 'oauth-2025-04-20' } `\n                -TimeoutSec 3 -ErrorAction Stop\n            @{ ts = $nowUtc; data = $usage } | ConvertTo-Json -Depth 12 -Compress |\n                Set-Content $cacheFile -Encoding UTF8\n        }\n    } catch {\n        # API/token failure: fall back to stale cache if present.\n        try { $usage = (Get-Content $cacheFile -Raw -Encoding UTF8 -ErrorAction Stop | ConvertFrom-Json).data } catch {}\n    }\n}\nif ($null -eq $usage) { exit 0 }\n\n$lim = $null\ntry {\n    $lim = @($usage.limits) | Where-Object {\n        $_.kind -eq 'weekly_scoped' -and \"$($_.scope.model.display_name)\" -like '*Fable*'\n    } | Select-Object -First 1\n} catch {}\nif ($null -eq $lim) { exit 0 }\n\n$pct = [int]$lim.percent\nif     ($pct -lt 30) { $col = \"$e[32m\" }   # green\nelseif ($pct -lt 50) { $col = \"$e[33m\" }   # yellow\nelseif ($pct -lt 70) { $col = \"$e[31m\" }   # red\nelse                 { $col = \"$e[91m\" }   # bright red\nWrite-Output \"${col}Fable Wk: ${pct}%${reset}\"\n"
};
// --- 생성 내용 끝 ---

const STAMP = (() => {
  const d = new Date();
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
})();
const BOM = '\ufeff'; // Windows PowerShell 5.1 은 BOM 없는 UTF-8 .ps1 을 ANSI 로 읽는다

function fail(msg) {
  console.error(`ERROR: ${msg}`);
  process.exit(1);
}

function parseArgs(argv) {
  const args = { home: null, dry: false };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--dry-run') args.dry = true;
    else if (a === '--claude-home') {
      args.home = argv[++i];
      if (!args.home || args.home.startsWith('--')) fail('--claude-home 뒤에 폴더 경로가 필요하다.');
    } else if (a === '-h' || a === '--help') {
      console.log('usage: node statusline-setup.js [--claude-home <폴더>] [--dry-run]');
      process.exit(0);
    } else fail(`알 수 없는 인자: ${a}`);
  }
  return args;
}

/** 대상 설정 폴더: --claude-home → CLAUDE_CONFIG_DIR → ~/.claude (Claude Code 와 같은 순서). */
function resolveHome(explicit) {
  const [raw, source] = explicit ? [explicit, '--claude-home']
    : process.env.CLAUDE_CONFIG_DIR ? [process.env.CLAUDE_CONFIG_DIR, 'CLAUDE_CONFIG_DIR']
    : [path.join(os.homedir(), '.claude'), '기본 ~/.claude'];
  const home = path.resolve(raw);
  if (!fs.existsSync(home) || !fs.statSync(home).isDirectory()) {
    fail(`${home} 폴더가 없다. 경로가 맞는지, 이 설정 폴더로 Claude Code 를 한 번 실행했는지 확인하라.`);
  }
  return { home, source };
}

function readSettings(file) {
  if (!fs.existsSync(file)) return { cur: {}, existed: false };
  const text = fs.readFileSync(file, 'utf8').replace(/^\ufeff/, '');
  let cur;
  try {
    cur = JSON.parse(text);
  } catch (e) {
    fail(`${file} 을 JSON 으로 읽지 못했다 (${e.message}). 파일을 고친 뒤 다시 실행하라.`);
  }
  if (cur === null || typeof cur !== 'object' || Array.isArray(cur)) fail(`${file} 의 최상위가 객체가 아니다.`);
  return { cur, existed: true };
}

function npm(args, opts = {}) {
  // 인자는 이 스크립트의 고정값뿐이라 한 문자열로 넘겨도 안전하다 (배열 + shell 은 Node 24 에서 DEP0190 경고).
  return spawnSync(`npm ${args.join(' ')}`, { encoding: 'utf8', shell: true, ...opts });
}

/** npm 전역 ccstatusline 버전. 설치돼 있지 않으면 null. */
function installedVersion() {
  const r = npm(['ls', '-g', 'ccstatusline', '--depth=0', '--json']);
  try {
    const deps = JSON.parse(r.stdout || '{}').dependencies || {};
    return deps.ccstatusline ? deps.ccstatusline.version : null;
  } catch {
    fail(`npm ls 출력을 읽지 못했다: ${String(r.stdout || r.stderr).slice(0, 200)}`);
  }
}

class Plan {
  constructor(home, dry) {
    this.home = home;
    this.dry = dry;
    this.log = [];
    this.backups = [];          // 이번 실행이 만든 .bak 파일 (되돌리기 안내는 실제로 만든 것만)
    this.settingsCreated = false;
  }

  record(action, target) {
    const rel = path.isAbsolute(target) ? path.relative(this.home, target).split(path.sep).join('/') : target;
    this.log.push([action, rel]);
  }

  /** 같으면 same, 다르면 .bak.<시각> 백업 후 교체, 없으면 생성. */
  writeFile(dst, content) {
    const data = Buffer.from(content, 'utf8');
    if (fs.existsSync(dst)) {
      if (fs.readFileSync(dst).equals(data)) return this.record('same', dst);
      const backup = `${dst}.bak.${STAMP}`;
      this.record(`update (backup: ${path.basename(backup)})`, dst);
      this.backups.push(backup);
      if (!this.dry) fs.copyFileSync(dst, backup);
    } else {
      this.record('create', dst);
    }
    if (!this.dry) {
      fs.mkdirSync(path.dirname(dst), { recursive: true });
      fs.writeFileSync(dst, data);
    }
  }

  /** settings.json 의 statusLine 만 바꾼다. 다른 키와 순서는 그대로 둔다. */
  setStatusLine(file, { cur, existed }, statusLine) {
    if (JSON.stringify(cur.statusLine) === JSON.stringify(statusLine)) return this.record('same', file);
    let action = 'create';
    if (existed) {
      const backup = `${file}.bak.${STAMP}`;
      action = `${cur.statusLine ? 'replace statusLine' : 'merge statusLine'} (backup: ${path.basename(backup)})`;
      this.backups.push(backup);
      if (!this.dry) fs.copyFileSync(file, backup);
    } else {
      this.settingsCreated = true;
    }
    this.record(action, file);
    if (cur.statusLine) this.record(`  ↳ 기존 statusLine: ${JSON.stringify(cur.statusLine)}`, '');
    if (!this.dry) {
      cur.statusLine = statusLine;
      fs.writeFileSync(file, JSON.stringify(cur, null, 2) + '\n', 'utf8');
    }
  }

  report() {
    // 대상이 없는 줄(안내 · WARN)은 열 너비 계산에서 빼고 그대로 찍는다
    const width = Math.max(...this.log.filter(([, rel]) => rel).map(([a]) => a.length)) + 2;
    for (const [action, rel] of this.log) console.log(rel ? `  ${action.padEnd(width)}${rel}` : `  ${action}`);
  }
}

function main() {
  if (process.platform !== 'win32') fail('Windows 전용이다 (위젯 2종이 PowerShell 스크립트다).');
  const args = parseArgs(process.argv.slice(2));
  const { home, source } = resolveHome(args.home);

  // --- 검사 단계: 여기서 실패하면 아무것도 바꾸지 않는다 ---
  const settingsFile = path.join(home, 'settings.json');
  const settings = readSettings(settingsFile);
  if (npm(['--version']).status !== 0) fail('npm 을 찾지 못했다. Node.js(npm 포함)를 설치한 뒤 다시 실행하라.');
  const version = installedVersion();

  const widgetDir = path.join(home, 'ccstatusline');
  const layoutFile = path.join(widgetDir, 'settings.json');
  const layout = JSON.parse(JSON.stringify(LAYOUT).replace(/\{\{WIDGET:([^}]+)\}\}/g, (_, name) =>
    JSON.stringify(`powershell -NoProfile -ExecutionPolicy Bypass -File "${path.join(widgetDir, name)}"`).slice(1, -1)));
  const statusLine = { ...STATUSLINE_BASE, command: `ccstatusline --config "${layoutFile.split(path.sep).join('/')}"` };

  console.log(`\n[statusline → ${home}]${args.dry ? ' (dry-run)' : ''}   대상 결정: ${source}`);
  const plan = new Plan(home, args.dry);

  if (version === null) {
    plan.record('npm install -g', `ccstatusline@${CCSTATUSLINE_VERSION}`);
    if (!args.dry) {
      console.log(`  npm install -g ccstatusline@${CCSTATUSLINE_VERSION} 실행 중...`);
      if (npm(['install', '-g', `ccstatusline@${CCSTATUSLINE_VERSION}`], { stdio: 'inherit' }).status !== 0) {
        fail('ccstatusline 설치에 실패했다. 파일은 바꾸지 않았다.');
      }
    }
  } else if (version !== CCSTATUSLINE_VERSION) {
    plan.record(`WARN: 전역 ccstatusline 이 ${version} 이다 (이 패키지는 ${CCSTATUSLINE_VERSION} 기준). ` +
      `맞추려면 npm install -g ccstatusline@${CCSTATUSLINE_VERSION}`, '');
  } else {
    plan.record('same', `ccstatusline@${version} (npm 전역)`);
  }

  for (const [name, text] of Object.entries(WIDGETS)) plan.writeFile(path.join(widgetDir, name), BOM + text);
  plan.writeFile(layoutFile, JSON.stringify(layout, null, 2) + '\n');
  plan.setStatusLine(settingsFile, settings, statusLine);
  plan.report();

  if (!args.dry) {
    console.log('\n다음 단계');
    console.log('  1. 이 설정 폴더로 Claude Code 를 새로 실행해 statusline 두 줄이 뜨는지 확인한다 (독립 환경이면 그 런처로 실행).');
    console.log('     Fable Wk 는 이 설정 폴더에 로그인(.credentials.json)이 있어야 표시된다.');
    console.log(`  2. 위젯 배치를 바꾸려면: ccstatusline --config "${layoutFile}"`);
    const undo = [`${widgetDir} 삭제`];
    if (plan.settingsCreated) undo.push(`${settingsFile} 삭제 (이번에 새로 만든 파일)`);
    for (const b of plan.backups) undo.push(`${path.basename(b)} → ${path.basename(b).replace(/\.bak\.\d+$/, '')} 로 복원`);
    console.log(`  되돌리기: ${undo.join(', ')}`);
  }
}

main();
