/** 【阿哈时刻】配速 双内核对拍：Python（api.py）vs JS（web_api.js）。
 *
 * 用法：node tools/check_aha_port.mjs [pythonExecutable]
 *   不给 python 就试 `python`（PATH 里找得到的话）。
 *
 * 做法：把同一条 payload 列表交给两边各跑一遍，**逐字段比较**
 * （数字按 1e-9 容差，字符串/布尔精确）。这正是「网页版和工具箱算得一样吗」
 * 那个问题 —— speed-plan 有 check_web_port.mjs，这个模块同样要有。
 *
 * 退出码：0 = 全部一致；1 = 有差异（报告在 stdout）；2 = 环境问题（没有 python / 脚本报错）。
 */
import { execFileSync } from "node:child_process";
import { createRequire } from "node:module";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const { createApi } = require(join(ROOT, "modules", "honkai-star-rail", "features", "aha-speed", "web_api.js"));

/* ---------------- 用例（和界面预设同一批数字） ---------------- */

function unit(id, name, baseSpd, lcBaseSpd, traceSpd, permPct, permFlat, err, eidolon, initAdv, targetSlot, rotation, equipment) {
  return { id, name, baseSpd, lcBaseSpd, traceSpd, permPct, permFlat, err, eidolon, initAdv, targetSlot, rotation, equipment: equipment || {} };
}

const AHA_QUAD = {
  maxAV: 300, useAeonAha: true, useTech: true, trace3Advance: true,
  ultAdvanceAha: 20, e1Wishpower: 5, e6FirstUltMode: "extra40",
  ultSpdPct: 30, sanduTeamSpdPct: 15, aeonAhaBaseSpd: 94, aeonAhaLcBaseSpd: 12,
  ahaSpdPct: 0, ahaAdvancePct: 0,
  team: [
    unit("1511", "星神★阿哈", 94, 12, 5, 12, 35, 0, 0, 0, 1, "skill", { godJoy: true, hasSigLc: true }),
    unit("1513", "砂金•戏浪", 107, 0, 9, 6, 28, 19.4, 0, 0, 0, "skill", { hasSummerLc: true }),
    unit("1503", "真珠", 99, 0, 9, 12, 26, 24.4, 0, 0, 1, "auto", { vonwacq: true }),
    unit("1502", "爻光", 101, 0, 9, 18, 45, 24.4, 0, 0, 1, "skill", { vonwacq: true }),
  ],
};

const SANDU = {
  maxAV: 300, useAeonAha: true, useTech: true, trace3Advance: true,
  ultAdvanceAha: 20, e1Wishpower: 5, e6FirstUltMode: "extra40",
  ultSpdPct: 30, sanduTeamSpdPct: 15, aeonAhaBaseSpd: 94, aeonAhaLcBaseSpd: 12,
  team: [
    unit("1513", "砂金•戏浪", 107, 0, 9, 6, 30, 19.4, 1, 0, 0, "skill", { hasSummerLc: true }),
    unit("1511", "星神★阿哈", 94, 12, 5, 12, 35, 0, 1, 0, 0, "skill", { godJoy: true, hasSigLc: true }),
    unit("1313", "星期日", 96, 0, 0, 6, 33, 24.4, 0, 0, 0, "skill", { danceS5: true }),
    unit("1304", "砂金(存护)", 106, 0, 0, 6, 28, 19.4, 0, 0, 0, "skill", {}),
  ],
};

const E6_ADV100 = JSON.parse(JSON.stringify(AHA_QUAD));
E6_ADV100.e6FirstUltMode = "advance100";
E6_ADV100.team[0].eidolon = 6;
E6_ADV100.team[1].eidolon = 2;

const SOLO = {
  maxAV: 400, useAeonAha: false, useTech: false, trace3Advance: false,
  team: [unit("1513", "砂金•戏浪", 107, 0, 9, 6, 30, 19.4, 2, 0, 0, "skill", { hasSummerLc: true })],
};

const CUSTOM = {
  maxAV: 200, useAeonAha: true, useTech: false, trace3Advance: false,
  aeonAhaBaseSpd: 90, aeonAhaLcBaseSpd: 0,
  team: [
    unit("custom", "自定义", 120, 10, 3, 20, 12, 0, 0, 15, 0, "basic", { windSet4: true, danceS5: true }),
    unit("1503", "真珠", 99, 0, 9, 0, 25, 0, 0, 0, 0, "auto", {}),
  ],
};

const CASES = [
  { action: "catalog", payload: {} },
  { action: "threshold", payload: { targetAV: 150, actions: 2, advancePct: 0 } },
  { action: "threshold", payload: { targetAV: 150, actions: 2, advancePct: 40 } },
  { action: "threshold", payload: { t: 2, actions: 6, advancePct: 12 } },
  ...[0, 50, 100].map((advancePct) => ({ action: "threshold", payload: { targetAV: 150, actions: 2, advancePct } })),
  { action: "simulate", payload: AHA_QUAD },
  { action: "simulate", payload: SANDU },
  { action: "simulate", payload: E6_ADV100 },
  { action: "simulate", payload: SOLO },
  { action: "simulate", payload: CUSTOM },
  { action: "simulate", payload: {
    maxAV: 100, useTech: false, trace3Advance: false, e1Wishpower: 8,
    aeonAhaBaseSpd: 100,
    team: [{ id: "1511", eidolon: 1, baseSpd: 1, lcBaseSpd: 0, traceSpd: 0 }],
  } },
  { action: "simulate", payload: {
    maxAV: 1, useTech: false, trace3Advance: false, e1Wishpower: 8,
    team: [{ id: "1511", eidolon: 6 }],
  } },
  ...[0, 1, 2, 6].map((eidolon) => ({ action: "simulate", payload: {
    maxAV: 300, useTech: true,
    team: [
      { id: "1503", targetSlot: 1 },
      { id: "1505", eidolon, initialEnergy: 480 },
      { id: "1511", targetSlot: 1 },
      { id: "1502" },
    ],
  } })),
  ...[0, 2].map((eidolon) => ({ action: "simulate", payload: {
    maxAV: 300, useTech: true,
    team: [
      { id: "1505", initialEnergy: 480, eidolon: 2 },
      { id: "1511", eidolon, initialEnergy: 8 },
      { id: "1503", targetSlot: 0 },
      { id: "1502" },
    ],
  } })),
  ...[0, 240, 480].map((initialEnergy) => ({ action: "simulate", payload: {
    maxAV: 1000, useTech: false, useAeonAha: false,
    team: [{ id: "1505", initialEnergy, baseSpd: 100, traceSpd: 0 }],
  } })),
  { action: "simulate", expectError: true, payload: { team: [{ id: "1505", initialEnergy: -1 }] } },
  { action: "simulate", expectError: true, payload: { team: [{ id: "1505", initialEnergy: 481 }] } },
  { action: "simulate", expectError: true, payload: { team: [{ id: "1505", initialEnergy: "invalid" }] } },
  { action: "simulate", expectError: true, payload: { team: [{ id: "1511" }, { id: "1511" }] } },
  { action: "simulate", payload: {
    maxAV: 1, useTech: false,
    team: [{ id: "1505", err: 2400, initialEnergy: 0, initAdv: 100 }],
  } },
];

/* ---------------- Python 侧 ---------------- */

const PY_RUNNER = `"""对拍用：把用例交给仓库里的 aha-speed api.py 跑一遍，结果写 JSON。"""
import json, os, sys, tempfile, shutil
from pathlib import Path

ROOT = Path(sys.argv[1])
CASES = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
OUT = Path(sys.argv[3])

sys.path.insert(0, str(ROOT))
TMP = tempfile.mkdtemp(prefix="gt-aha-port-")
os.environ["GT_USERDATA"] = TMP

from core import feature_api, registry

errors = []
for module in registry.scan()[0]:
    for feature in module.features:
        api_path = feature.dir / feature.api_file
        if api_path.is_file():
            feature_api.load_feature_api(module.id, feature.id, api_path, module.dir, feature.dir, errors)

out = []
for case in CASES:
    try:
        res = feature_api.call("honkai-star-rail", "aha-speed", case["action"], case["payload"])
        out.append({"ok": True, "result": res})
    except Exception as exc:
        out.append({"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)})

OUT.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
shutil.rmtree(TMP, ignore_errors=True)
`;

function findPython() {
  const given = process.argv[2];
  const candidates = given ? [given] : ["python", "py", "python3"];
  for (const exe of candidates) {
    try {
      execFileSync(exe, ["-c", "print('ok')"], { stdio: "pipe" });
      return exe;
    } catch {
      /* 试下一个 */
    }
  }
  return null;
}

const python = findPython();
if (!python) {
  console.error("[X] 找不到 python（可以显式传：node tools/check_aha_port.mjs <python.exe>）");
  process.exit(2);
}

const tmp = mkdtempSync(join(tmpdir(), "gt-aha-port-"));
let pyOut;
try {
  const casesPath = join(tmp, "cases.json");
  const outPath = join(tmp, "py.json");
  const runnerPath = join(tmp, "runner.py");
  writeFileSync(casesPath, JSON.stringify(CASES.map((c) => ({ action: c.action, payload: c.payload }))), "utf-8");
  writeFileSync(runnerPath, PY_RUNNER, "utf-8");
  execFileSync(python, [runnerPath, ROOT, casesPath, outPath], { stdio: "pipe" });
  pyOut = JSON.parse(require("node:fs").readFileSync(outPath, "utf-8"));
} catch (err) {
  console.error("[X] Python 侧执行失败：", err && err.message);
  if (err && err.stdout) console.error(String(err.stdout).slice(-2000));
  if (err && err.stderr) console.error(String(err.stderr).slice(-2000));
  rmSync(tmp, { recursive: true, force: true });
  process.exit(2);
} finally {
  rmSync(tmp, { recursive: true, force: true });
}

/* ---------------- JS 侧 + 逐字段比较 ---------------- */

const client = createApi();
const jsOut = [];
for (const entry of CASES) {
  try {
    jsOut.push({ ok: true, result: client.call(entry.action, entry.payload) });
  } catch (err) {
    jsOut.push({ ok: false, error: `${err && err.name}: ${err && err.message}` });
  }
}

let checks = 0;
const failures = [];
const isNum = (v) => typeof v === "number" && Number.isFinite(v);

function cmp(path, a, b) {
  checks += 1;
  if (isNum(a) && isNum(b)) {
    const tol = Math.max(1e-9, Math.abs(a) * 1e-9);
    if (Math.abs(a - b) > tol) failures.push(`${path}: Python ${a} vs JS ${b}`);
    return;
  }
  if (a === null || b === null || typeof a !== "object" || typeof b !== "object") {
    if (a !== b) failures.push(`${path}: Python ${JSON.stringify(a)} vs JS ${JSON.stringify(b)}`);
    return;
  }
  if (Array.isArray(a) || Array.isArray(b)) {
    if (!Array.isArray(a) || !Array.isArray(b)) {
      failures.push(`${path}: 一边是数组一边不是`);
      return;
    }
    if (a.length !== b.length) {
      failures.push(`${path}: 数组长度 Python ${a.length} vs JS ${b.length}`);
      return;
    }
    a.forEach((item, index) => cmp(`${path}[${index}]`, item, b[index]));
    return;
  }
  const ka = Object.keys(a).sort();
  const kb = Object.keys(b).sort();
  if (ka.join(",") !== kb.join(",")) {
    failures.push(`${path}: 字段不一致 Python[${ka.join(",")}] vs JS[${kb.join(",")}]`);
    return;
  }
  ka.forEach((key) => cmp(`${path}.${key}`, a[key], b[key]));
}

CASES.forEach((entry, index) => {
  const label = `[${index}] ${entry.action}${entry.payload && entry.payload.team ? `(${entry.payload.team[0].name}…)` : ""}`;
  const py = pyOut[index];
  const js = jsOut[index];
  if (!py || !js) {
    failures.push(`${label}: 结果缺失`);
    return;
  }
  if (py.ok !== js.ok) {
    failures.push(`${label}: 成功状态不一致 Python=${py.ok} JS=${js.ok}`);
    return;
  }
  if (entry.expectError && py.ok) {
    failures.push(`${label}: 非法输入应报错，两端却都返回成功`);
    return;
  }
  if (!py.ok) {
    const message = (error) => error.replace(/^[A-Za-z]*Error: /, "");
    if (message(py.error) !== message(js.error)) failures.push(`${label}: 报错文案不一致\n    Python: ${py.error}\n    JS:     ${js.error}`);
    return;
  }
  cmp(label, py.result, js.result);
});

if (failures.length) {
  console.error(`[X] 双内核不一致：${failures.length} 处（共比较 ${checks} 项）`);
  for (const line of failures.slice(0, 30)) console.error("  " + line);
  process.exit(1);
}
console.log(`[OK] aha-speed 双内核一致：${checks} 项逐字段相同（${CASES.length} 条用例，含开局拉条、绯英星魂与非法输入）`);
