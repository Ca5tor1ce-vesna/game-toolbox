/** 角色顶分网页版（web_api.js）自检：镜像顺序、校验跳过、缓存、离线回退。用法：node tools/check_herta_web.mjs */
import { createRequire } from "node:module";
import { createHash } from "node:crypto";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
const require = createRequire(import.meta.url);
const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const { createApi, MIRRORS, avatarMap, lightconeMap } = require(join(ROOT, "modules", "herta", "features", "records", "web_api.js"));

const sample = { source: "s", collected_at: "c", selection_rule: "r", targets: [{ mode: "虚构叙事", season: "1", stage: "x", category: "满分", records: [{ lineup: [], ltd: 0, std: 0, date: "d" }] }] };
const body = Buffer.from(JSON.stringify(sample), "utf-8");
const sha = createHash("sha256").update(body).digest("hex");
const failures = [];
const check = (label, cond) => { if (!cond) failures.push(label); };

function fakeFetch(good, badSha = new Set()) {
  const calls = [];
  const f = async (url) => {
    calls.push(url);
    const m = MIRRORS.find((x) => url.startsWith(x.base));
    if (!good.has(m.name)) throw new Error("down");
    const data = url.endsWith(".sha256") ? Buffer.from((badSha.has(m.name) ? "0".repeat(64) : sha) + "  latest.json\n") : body;
    return { ok: true, status: 200, arrayBuffer: async () => data.buffer.slice(data.byteOffset, data.byteOffset + data.length) };
  };
  return { f, calls };
}

let mem = {};
const storage = { load: () => mem, save: (v) => (mem = v) };
let t = new Date("2026-10-15T04:00:00Z");
const now = () => t;

const a = fakeFetch(new Set(["jsDelivr", "ghfast.top"]), new Set(["jsDelivr"]));
const r1 = await createApi({ fetch: a.f, storage, now }).call("load", { refresh: true });
check("选中 ghfast.top", r1.mirror === "ghfast.top");
check("校验不一致被跳过", /校验不一致/.test(r1.attempts[1].error));
check("attempts 顺序", r1.attempts.map((x) => x.ok).join() === "false,false,false,false,true");
check("fetched_at UTC+8", r1.fetched_at === "2026-10-15 12:00");
check("sha", r1.sha256 === sha);

const down = fakeFetch(new Set());
const api2 = createApi({ fetch: down.f, storage, now });
const r2 = await api2.call("load", {});
check("新鲜缓存不联网", r2.from_cache && down.calls.length === 0);
t = new Date("2026-10-15T06:00:00Z");
const r3 = await api2.call("load", {});
check("过期后联网失败回退离线缓存", r3.offline && /离线/.test(r3.note) && r3.data.targets[0].mode === "虚构叙事");

let threw = false;
try { await createApi({ fetch: down.f }).call("load", { refresh: true }); } catch (e) { threw = /没有本地缓存/.test(e.message); }
check("无缓存全失败抛错", threw);
check("镜像数 6", MIRRORS.length === 6);

// 头像 / 光锥映射（与 tests 的 Python 断言同一份夹具）
import { readFileSync } from "node:fs";
const rd = (...p) => JSON.parse(readFileSync(join(ROOT, ...p), "utf-8"));
const chars = rd("modules", "honkai-star-rail", "data", "characters.json");
const lcs = rd("modules", "honkai-star-rail", "data", "lightcones.json");
const fx = rd("tests", "fixtures", "herta_lightcone_sample.json");
const names = fx.targets.flatMap((t) => t.records.flatMap((r) => r.lineup.map((c) => c.name)));
const am = avatarMap(chars, names);
check("三月七 (巡猎) 用 1224", am.avatars["三月七 (巡猎)"] === "/modules/herta/assets/1224.webp");
check("开拓者 (欢愉) = 8009", am.avatars["开拓者 (欢愉)"] === chars.find((c) => c.id === "8009").icon);
check("未映射角色", JSON.stringify(am.missing) === JSON.stringify(["不存在的角色"]));
const lm = lightconeMap(lcs, fx.targets.flatMap((t) => t.records.flatMap((r) => r.lineup.map((c) => c.lightcone))).filter(Boolean));
check("光锥宽松匹配", lm.icons["舞! 舞! 舞!"] && lm.icons["忍法帖·缭乱破魔"] && lm.icons["一场谎言的终幕"]);
check("未映射光锥", JSON.stringify(lm.missing) === JSON.stringify(["不存在的光锥"]));
const snap = rd("tests", "fixtures", "herta_latest_snapshot.json");
check("真实数据头像全覆盖", avatarMap(chars, snap.targets.flatMap((t) => t.records.flatMap((r) => r.lineup.map((c) => c.name)))).missing.length === 0);
const a2 = createApi({ fetch: fakeFetch(new Set(["GitHub Raw"])).f, characters: chars, lightcones: lcs });
const r9 = await a2.call("load", { refresh: true });
check("load 带 avatars/lightcone_icons", r9.avatars && r9.lightcone_icons && Array.isArray(r9.unmapped_lightcones));

if (failures.length) { console.log("❌ " + failures.join("；")); process.exit(1); }
console.log("✅ 角色顶分网页版自检全部通过（16 项）");
