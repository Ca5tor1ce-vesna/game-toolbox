/* 低配通关记录 —— 浏览器端实现（api.py 的移植）。经典脚本：浏览器挂 window.GT_HERTA_API，node 走 module.exports。
 *
 *   const api = GT_HERTA_API.createApi({fetch, storage, now});
 *   await api.call("load", {refresh: true});   // 返回 Promise（网络请求是异步的）
 *
 * fetch   = 全局 fetch（node 18+ / 浏览器）或测试替身；storage = {load(), save(obj)}（浏览器注入 localStorage 包装）。
 * 镜像列表、校验、缓存规则与 api.py 完全一致；SHA-256 用 crypto.subtle。
 */
(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (root) root.GT_HERTA_API = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";
  const REPO = "Ca5tor1ce-vesna/herta-data";
  const RAW = `https://raw.githubusercontent.com/${REPO}/main/data/`;
  const MIRRORS = [
    { name: "GitHub Raw", base: RAW },
    { name: "jsDelivr", base: `https://cdn.jsdelivr.net/gh/${REPO}@main/data/` },
    { name: "jsDelivr Fastly", base: `https://fastly.jsdelivr.net/gh/${REPO}@main/data/` },
    { name: "jsDelivr Gcore", base: `https://gcore.jsdelivr.net/gh/${REPO}@main/data/` },
    { name: "ghfast.top", base: "https://ghfast.top/" + RAW },
    { name: "gh-proxy.com", base: "https://gh-proxy.com/" + RAW },
  ];
  const TIMEOUT = 4.0;
  const CACHE_FRESH_SECONDS = 3600;
  const MODES = ["混沌回忆", "虚构叙事", "末日幻影", "异相仲裁"];

  function validate(data) {
    if (!data || typeof data !== "object" || !Array.isArray(data.targets) || !data.targets.length)
      throw new Error("数据结构不对：缺少 targets");
    for (const t of data.targets) {
      if (!t || !MODES.includes(t.mode) || !Array.isArray(t.records)) throw new Error("数据结构不对：target 异常");
      for (const r of t.records) if (!r || !Array.isArray(r.lineup)) throw new Error("数据结构不对：record 异常");
    }
  }

  async function sha256Hex(bytes) {
    const subtle = (globalThis.crypto && globalThis.crypto.subtle) || require("node:crypto").webcrypto.subtle;
    const buf = await subtle.digest("SHA-256", bytes);
    return Array.from(new Uint8Array(buf), (b) => b.toString(16).padStart(2, "0")).join("");
  }

  function nowStr(d) {
    const t = new Date(d.getTime() + 8 * 3600e3); // UTC+8
    const p = (n) => String(n).padStart(2, "0");
    return `${t.getUTCFullYear()}-${p(t.getUTCMonth() + 1)}-${p(t.getUTCDate())} ${p(t.getUTCHours())}:${p(t.getUTCMinutes())}`;
  }

  function createApi(opts = {}) {
    const fetchImpl = opts.fetch || globalThis.fetch.bind(globalThis);
    let memory = {};
    const storage = opts.storage || { load: () => memory, save: (v) => (memory = v) };
    const now = opts.now || (() => new Date());
    const timeout = opts.timeout || TIMEOUT;

    async function get(url) {
      const ctl = typeof AbortController !== "undefined" ? new AbortController() : null;
      const timer = setTimeout(() => ctl && ctl.abort(), timeout * 1000);
      try {
        const resp = await fetchImpl(url, { signal: ctl ? ctl.signal : undefined, cache: "no-store" });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        return new Uint8Array(await resp.arrayBuffer());
      } catch (e) {
        if (e && e.name === "AbortError") throw new Error("超时");
        throw e;
      } finally {
        clearTimeout(timer);
      }
    }

    async function fetchMirror(base) {
      const shaText = new TextDecoder().decode(await get(base + "latest.sha256")).trim();
      const expected = (shaText.split(/\s+/)[0] || "").toLowerCase();
      if (expected.length !== 64) throw new Error("sha256 文件格式不对");
      const body = await get(base + "latest.json");
      const actual = await sha256Hex(body);
      if (actual !== expected) throw new Error("校验不一致（镜像缓存未同步？）");
      const data = JSON.parse(new TextDecoder().decode(body).replace(/^\uFEFF/, ""));
      validate(data);
      return { data, sha: actual };
    }

    async function tryMirrors(list) {
      const attempts = [];
      for (const m of list || MIRRORS) {
        const start = Date.now();
        try {
          const { data, sha } = await fetchMirror(m.base);
          attempts.push({ name: m.name, ok: true, ms: Date.now() - start, error: "" });
          return { mirror: m, data, sha, attempts };
        } catch (e) {
          attempts.push({ name: m.name, ok: false, ms: Date.now() - start, error: String((e && e.message) || e).slice(0, 120) });
        }
      }
      return { mirror: null, attempts };
    }

    async function load(payload = {}) {
      const cache = (storage.load() || {}).records_cache || null;
      const nowSec = now().getTime() / 1000;
      if (cache && !payload.refresh && nowSec - Number(cache.ts || 0) < CACHE_FRESH_SECONDS)
        return { ...cache.result, from_cache: true };
      const r = await tryMirrors();
      if (r.mirror) {
        const result = { data: r.data, mirror: r.mirror.name, sha256: r.sha, offline: false, note: "",
          fetched_at: nowStr(now()), attempts: r.attempts };
        storage.save({ ...(storage.load() || {}), records_cache: { ts: nowSec, result } });
        return result;
      }
      if (cache)
        return { ...cache.result, offline: true, attempts: r.attempts, from_cache: true,
          note: `所有镜像都连不上，显示的是 ${cache.result.fetched_at} 缓存的数据（离线）。` };
      throw new Error("所有镜像都连不上，且没有本地缓存。请检查网络后点刷新。");
    }

    return {
      MIRRORS, tryMirrors,
      async call(action, payload) {
        if (action === "load") return load(payload || {});
        if (action === "mirrors") return { mirrors: MIRRORS, timeout: TIMEOUT };
        throw new Error(`未知动作 ${action}`);
      },
    };
  }

  return { createApi, MIRRORS, validate };
});
