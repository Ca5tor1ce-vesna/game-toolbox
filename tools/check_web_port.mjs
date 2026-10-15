/**
 * 用 node 对拍网页版（JS）实现与 Python 实现。
 *
 * 用法：<node> tools/check_web_port.mjs
 *
 * 判据：tests/fixtures/web_oracle.json 里的每一条都由 Python 算出，
 * JS 实现必须给出同样的速度 / 拉条 / 需求速度 / 表格 / 推荐结果。
 */

import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const DATA = join(ROOT, "modules", "honkai-star-rail", "data");

const readJson = (name) => JSON.parse(readFileSync(join(DATA, name), "utf-8"));

let createApi;
try {
  ({ createApi } = require(join(ROOT, "modules", "honkai-star-rail", "features", "speed-plan", "web_api.js")));
} catch (error) {
  console.error("加载 web_api.js 失败：", error.message);
  process.exit(2);
}
if (typeof createApi !== "function") {
  console.error("web_api.js 必须导出 createApi(data, storage)");
  process.exit(2);
}

const data = {
  characters: readJson("characters.json"),
  lightcones: readJson("lightcones.json"),
  relic_sets: readJson("relic_sets.json"),
  modes: readJson("modes.json"),
  sources: readJson("sources.json"),
};

// 内存版存储（浏览器里换成 localStorage）
const memory = {};
const storage = {
  load: () => JSON.parse(JSON.stringify(memory)),
  save: (value) => Object.assign(memory, JSON.parse(JSON.stringify(value))),
};

const api = createApi(data, storage);
const oracle = JSON.parse(readFileSync(join(ROOT, "tests", "fixtures", "web_oracle.json"), "utf-8"));

const TOLERANCE = 1e-6;
let checks = 0;
const failures = [];

function compare(path, expected, actual) {
  checks += 1;
  if (typeof expected === "number") {
    if (typeof actual !== "number" || Math.abs(expected - actual) > TOLERANCE) {
      failures.push(`${path}：期望 ${expected}，实际 ${actual}`);
    }
    return;
  }
  if (Array.isArray(expected)) {
    if (!Array.isArray(actual) || actual.length !== expected.length) {
      failures.push(`${path}：数组长度不一致（期望 ${expected.length}，实际 ${actual?.length}）`);
      return;
    }
    expected.forEach((item, index) => compare(`${path}[${index}]`, item, actual[index]));
    return;
  }
  if (expected && typeof expected === "object") {
    if (!actual || typeof actual !== "object") {
      failures.push(`${path}：期望对象，实际 ${typeof actual}`);
      return;
    }
    for (const key of Object.keys(expected)) {
      compare(`${path}.${key}`, expected[key], actual[key]);
    }
    return;
  }
  checks += 0;
  if (expected !== actual) {
    failures.push(`${path}：期望 ${JSON.stringify(expected)}，实际 ${JSON.stringify(actual)}`);
  }
}

// ---------- 配速 ----------
for (const entry of oracle.plans) {
  let result;
  try {
    result = api.call("plan", entry.payload);
  } catch (error) {
    failures.push(`plan(${entry.label}) 抛异常：${error.message}`);
    continue;
  }
  compare(`${entry.label}.speed`, entry.speed, {
    base: result.speed.base,
    baseRaw: result.speed.baseRaw,
    traceSpeed: result.speed.traceSpeed,
    traceSpeedPct: result.speed.traceSpeedPct,
    pct: result.speed.pct,
    flat: result.speed.flat,
    final: result.speed.final,
  });
  compare(`${entry.label}.advance.total`, entry.advance.total, result.advance.total);
  compare(`${entry.label}.advance.items`, entry.advance.items, result.advance.items.map((i) => i.percent));
  compare(`${entry.label}.verdict`, entry.verdict, {
    t: result.verdict.t,
    actions: result.verdict.actions,
    totalAV: result.verdict.totalAV,
    requiredSpeed: result.verdict.requiredSpeed,
    currentSpeed: result.verdict.currentSpeed,
    gap: result.verdict.gap,
    achievableActions: result.verdict.achievableActions,
  });
  compare(`${entry.label}.relicSetCount`, entry.relicSetCount, (result.relicSets || []).length);
  compare(`${entry.label}.warningCount`, entry.warningCount, (result.warnings || []).length);
  if (entry.effects) {
    const actual = (result.effects?.speed || []).map((item) => ({
      id: item.id,
      kind: item.kind,
      value: item.value,
      apply: item.apply,
      trigger: item.trigger,
      defaultEnabled: item.defaultEnabled,
    }));
    compare(`${entry.label}.effects`, entry.effects, actual);
  }
  if (entry.tables) {
    for (const expectedTable of entry.tables) {
      const table = (result.tables || []).find((item) => item.id === expectedTable.id);
      if (!table) {
        failures.push(`${entry.label}.tables.${expectedTable.id}：缺少该模式的表格`);
        continue;
      }
      compare(`${entry.label}.tables.${expectedTable.id}.firstCycleAV`, expectedTable.firstCycleAV, table.firstCycleAV);
      compare(`${entry.label}.tables.${expectedTable.id}.cycleAV`, expectedTable.cycleAV, table.cycleAV);
      compare(`${entry.label}.tables.${expectedTable.id}.tValues`, expectedTable.tValues, table.tValues);
      expectedTable.cells.forEach((row, rowIndex) => {
        compare(
          `${entry.label}.tables.${expectedTable.id}.cells[${rowIndex}]`,
          row,
          table.rows[rowIndex].cells.map((cell) => cell.speed),
        );
      });
    }
  }
}

// ---------- 推荐 ----------
for (const entry of oracle.recommends) {
  let result;
  try {
    result = api.call("recommend", entry.payload);
  } catch (error) {
    failures.push(`recommend(${entry.label}) 抛异常：${error.message}`);
    continue;
  }
  compare(`${entry.label}.assumptions`, entry.assumptions, result.assumptions);
  compare(`${entry.label}.evaluated`, entry.evaluated, result.evaluated);
  entry.results.forEach((expectedItem, index) => {
    const item = (result.results || [])[index];
    if (!item) {
      failures.push(`${entry.label}.results[${index}]：缺少该条推荐`);
      return;
    }
    compare(`${entry.label}.results[${index}]`, expectedItem, {
      coneId: item.coneId,
      coneName: item.coneName,
      fourPieceId: item.fourPieceId,
      fourPieceName: item.fourPieceName,
      ornamentIds: item.ornamentIds,
      speed: item.speed,
      advance: item.advance,
      required: item.required,
      neededSubstatSpeed: item.neededSubstatSpeed,
      ok: item.ok,
    });
  });
}

// ---------- 结果 ----------
if (failures.length === 0) {
  console.log(`✅ 网页版实现与 Python 一致：${checks} 项检查全部通过（${oracle.plans.length} 条配速 + ${oracle.recommends.length} 条推荐）`);
  process.exit(0);
}
console.log(`❌ ${failures.length} 项不一致（共 ${checks} 项检查）：`);
for (const line of failures.slice(0, 40)) console.log("   " + line);
if (failures.length > 40) console.log(`   …还有 ${failures.length - 40} 项`);
process.exit(1);
