/* 工具箱外壳：模块导航、功能懒加载、扩展指南、状态诊断。
 *
 * 这里只负责"装东西"，不含任何游戏逻辑——具体功能各自在自己的 ui.js 里。
 */

const state = {
  registry: null,
  current: { moduleId: null, featureId: null },
  cleanup: null,
  styleEl: null,
  filter: "",
};

const $ = (sel, el = document) => el.querySelector(sel);
let persistenceReady = false;
const shellState = () => persistenceReady ? window.GT_LOCAL_STATE.scope("shell") : null;
function saveShell() { shellState()?.save({ current: state.current, filter: state.filter, collapsed: [...navCollapsed] }); }

/* ---------------- 基础请求 ---------------- */

async function getJSON(url, options) {
  const res = await fetch(url, options);
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    throw new Error(`接口返回的不是 JSON（${res.status}）：${text.slice(0, 200)}`);
  }
  if (!res.ok || data.ok === false) {
    throw new Error(data && data.error ? data.error : `HTTP ${res.status}`);
  }
  return data;
}

async function callApi(moduleId, featureId, action, payload = {}) {
  const data = await getJSON("/api/call", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ module: moduleId, feature: featureId, action, payload }),
  });
  return data.result;
}

/* ---------------- 外观主题 ----------------
   「界面 → 外观与排版」写进去的设置，在这里变成 CSS 变量与界面文字。
   主题存在服务端 userdata/interface/theme.json，所以换版本、换窗口都还在。 */

const THEME_COLOR_VARS = {
  bg: "--bg",
  panel: "--panel",
  panel2: "--panel-2",
  border: "--border",
  text: "--text",
  muted: "--muted",
  accent: "--accent",
  accent2: "--accent-2",
  good: "--good",
  warn: "--warn",
  bad: "--bad",
};
const THEME_NUMBER_VARS = {
  baseSize: ["fonts", "--base-size", "px"],
  lineHeight: ["fonts", "--line-height", ""],
  radius: ["layout", "--radius", "px"],
  sidebarWidth: ["layout", "--sidebar-w", "px"],
  viewPadding: ["layout", "--view-pad", "px"],
  cardPadding: ["layout", "--card-pad", "px"],
};
const THEME_TEXT_DEFAULTS = {
  brand: "游戏实用工具箱",
  searchPlaceholder: "搜索功能…（配速 / 抽卡 / 伤害）",
};
let currentTheme = {};

function applyTheme(theme) {
  currentTheme = theme && typeof theme === "object" ? theme : {};
  const root = document.documentElement;
  // 先清掉上一次设的值：否则"改回默认"时会残留旧设置
  for (const varName of Object.values(THEME_COLOR_VARS)) root.style.removeProperty(varName);
  for (const [, varName] of Object.values(THEME_NUMBER_VARS)) root.style.removeProperty(varName);
  root.style.removeProperty("--sans");
  root.style.removeProperty("--mono");

  const colors = currentTheme.colors || {};
  for (const [key, varName] of Object.entries(THEME_COLOR_VARS)) {
    if (colors[key]) root.style.setProperty(varName, colors[key]);
  }
  const fonts = currentTheme.fonts || {};
  const layout = currentTheme.layout || {};
  if (fonts.sans) root.style.setProperty("--sans", fonts.sans);
  if (fonts.mono) root.style.setProperty("--mono", fonts.mono);
  for (const [key, [group, varName, unit]] of Object.entries(THEME_NUMBER_VARS)) {
    const value = (group === "fonts" ? fonts : layout)[key];
    if (value !== undefined && value !== null && value !== "") {
      root.style.setProperty(varName, `${value}${unit}`);
    }
  }
  const text = { ...THEME_TEXT_DEFAULTS, ...(currentTheme.text || {}) };
  const brand = document.querySelector(".brand-text b");
  if (brand) brand.textContent = text.brand;
  const search = document.querySelector("#search");
  if (search) search.placeholder = text.searchPlaceholder;
  document.title = text.brand;
  return currentTheme;
}

/* ---------------- 界面文字替换 ----------------
   「界面 → 文字替换」把 key → 新文字 存进 userdata/shell-overrides.json 的 texts 段。
   这里读出来，把带 data-text="key" 的元素文字换掉。
   用 MutationObserver 盯着点：功能是动态渲染的，挂载完还得再刷一遍。 */
let textOverrides = {};

function applyTextOverrides(scope) {
  const root = scope || document;
  root.querySelectorAll("[data-text]").forEach((element) => {
    const key = element.getAttribute("data-text");
    const value = textOverrides[key];
    if (value === undefined) return;
    // 只允许把换行写成 <br>。先转义，再把转义后的 br 换回去，别的标签不能执行。
    if (/<br\s*\/?>/i.test(value)) {
      element.innerHTML = escapeHtml(value).replace(/&lt;br\s*\/?&gt;/gi, "<br>");
    } else {
      element.textContent = value;
    }
  });
}

function watchTextOverrides() {
  try {
    const observer = new MutationObserver(() => applyTextOverrides(document));
    observer.observe(document.body, { childList: true, subtree: true });
  } catch (err) {
    console.warn("文字替换的监听没起来（不影响使用）：", err);
  }
}

window.GTText = {
  apply: applyTextOverrides,
  current: () => textOverrides,
  async load() {
    try {
      const data = await getJSON("/api/overrides");
      const overrides = (data && data.overrides) || {};
      textOverrides = overrides.texts && typeof overrides.texts === "object" ? overrides.texts : {};
      applyTextOverrides(document);
    } catch (err) {
      // 没有覆盖文件是正常情况（用户包里就没有），不打扰用户
      textOverrides = {};
    }
  },
};

window.GTTheme = {
  apply: applyTheme,
  current: () => currentTheme,
  async load() {
    try {
      const result = await callApi("interface", "appearance", "load", {});
      applyTheme(result && result.theme ? result.theme : {});
    } catch (err) {
      // 主题读不到不该挡住启动（例如用户把 theme.json 改坏了）
      console.warn("主题加载失败，用默认外观：", err);
      applyTheme({});
    }
  },
};

/* ---------------- 工具 ---------------- */

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

const fmt = {
  num(value, digits = 2) {
    if (value === null || value === undefined || Number.isNaN(value)) return "-";
    const n = Number(value);
    if (!Number.isFinite(n)) return "-";
    return n.toFixed(digits);
  },
  int(value) {
    if (value === null || value === undefined) return "-";
    return String(Math.round(Number(value)));
  },
  pct(value, digits = 2) {
    if (value === null || value === undefined) return "-";
    return `${(Number(value) * 100).toFixed(digits)}%`;
  },
  money(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return "-";
    return Math.round(n).toLocaleString("zh-CN");
  },
};

/* ---------------- 导航 ---------------- */

function matches(module, feature, needle) {
  if (!needle) return true;
  const haystack = [
    module.name,
    module.id,
    ...(module.tags || []),
    feature.name,
    feature.id,
    feature.description,
    ...(feature.tags || []),
  ]
    .join(" ")
    .toLowerCase();
  return haystack.includes(needle);
}

const NAV_COLLAPSE_KEY = "gt-nav-collapsed";
const navCollapsed = new Set(
  (() => {
    try {
      const v = JSON.parse(localStorage.getItem(NAV_COLLAPSE_KEY) || "[]");
      return Array.isArray(v) ? v : [];
    } catch {
      return [];
    }
  })(),
);

function renderNav() {
  const nav = $("#nav");
  const needle = state.filter.trim().toLowerCase();
  const modules = (state.registry?.modules || []).filter((m) =>
    (m.features || []).some((f) => matches(m, f, needle)),
  );

  if (!modules.length) {
    nav.innerHTML = `<div class="nav-empty" data-text="shell.noMatch">没有匹配的功能。<br/>换个词，或者点「↻ 重新扫描」。</div>`;
    return;
  }

  nav.innerHTML = modules
    .map((module) => {
      const features = (module.features || []).filter((f) => matches(module, f, needle));
      const items = features
        .map(
          (f) => `
        <button class="nav-feature ${
          state.current.moduleId === module.id && state.current.featureId === f.id ? "active" : ""
        }" data-module="${escapeHtml(module.id)}" data-feature="${escapeHtml(f.id)}"
          title="${escapeHtml(f.description || f.name)}">
          <span class="icon">${escapeHtml(f.icon || "•")}</span>
          <span class="name">${escapeHtml(f.name)}</span>
        </button>`,
        )
        .join("");
      // 搜索时全部展开；平时按用户上次的折叠状态
      const collapsed = !needle && navCollapsed.has(module.id);
      return `
        <div class="nav-module${collapsed ? " collapsed" : ""}" data-module-id="${escapeHtml(module.id)}">
          <button type="button" class="nav-module-title" aria-expanded="${collapsed ? "false" : "true"}"
            title="v${escapeHtml(module.version || "0.0.0")}">
            <span>${escapeHtml(module.icon || "🎮")}</span>
            <span>${escapeHtml(module.name)}</span>
            <span class="caret">▾</span>
          </button>
          <div class="nav-items">
          ${items || '<div class="nav-empty" data-text="shell.moduleEmpty">这个模块还没有功能</div>'}
          </div>
        </div>`;
    })
    .join("");

  nav.querySelectorAll(".nav-feature").forEach((btn) => {
    btn.addEventListener("click", () => {
      openFeature(btn.dataset.module, btn.dataset.feature);
    });
  });
  nav.querySelectorAll(".nav-module-title").forEach((btn) => {
    btn.addEventListener("click", () => {
      const box = btn.closest(".nav-module");
      const id = box.dataset.moduleId;
      const nowCollapsed = !box.classList.contains("collapsed");
      box.classList.toggle("collapsed", nowCollapsed);
      btn.setAttribute("aria-expanded", nowCollapsed ? "false" : "true");
      if (nowCollapsed) navCollapsed.add(id);
      else navCollapsed.delete(id);
      saveShell();
      try {
        localStorage.setItem(NAV_COLLAPSE_KEY, JSON.stringify([...navCollapsed]));
      } catch {
        /* 存不了就只在本次会话里记住 */
      }
    });
  });
}

function findFeature(moduleId, featureId) {
  const module = (state.registry?.modules || []).find((m) => m.id === moduleId);
  if (!module) return {};
  const feature = (module.features || []).find((f) => f.id === featureId);
  return { module, feature };
}

/* 深链：地址栏里的 #/模块/功能，可以存书签、可以直接发给别人 */
function parseHash() {
  const match = /^#\/([^/]+)\/([^/]+)$/.exec(location.hash || "");
  if (!match) return null;
  return {
    moduleId: decodeURIComponent(match[1]),
    featureId: decodeURIComponent(match[2]),
  };
}

function setHash(moduleId, featureId) {
  const hash = `#/${encodeURIComponent(moduleId)}/${encodeURIComponent(featureId)}`;
  if (location.hash !== hash) history.replaceState(null, "", hash);
}

function clearHash() {
  if (location.hash) history.replaceState(null, "", location.pathname + location.search);
}

function setCrumb(text, sub) {
  $("#crumb").innerHTML = `${escapeHtml(text)}${sub ? `<span class="sub">${escapeHtml(sub)}</span>` : ""}`;
}

/* ---------------- 打开功能 ---------------- */

function makeCtx(module, feature) {
  return {
    moduleId: module.id,
    featureId: feature.id,
    module,
    feature,
    persistence: persistenceReady ? window.GT_LOCAL_STATE.scope(`${module.id}/${feature.id}`) : null,
    call: (action, payload) => callApi(module.id, feature.id, action, payload),
    data: async (name) =>
      (await getJSON(`/api/data/${encodeURIComponent(module.id)}/${encodeURIComponent(name)}`)).data,
    fmt,
    ui: { escapeHtml, fmt },
  };
}

function clearCurrent() {
  if (typeof state.cleanup === "function") {
    try {
      state.cleanup();
    } catch (err) {
      console.warn("unmount 出错：", err);
    }
  }
  state.cleanup = null;
  if (state.styleEl) {
    state.styleEl.remove();
    state.styleEl = null;
  }
}

async function openFeature(moduleId, featureId) {
  const { module, feature } = findFeature(moduleId, featureId);
  if (!module || !feature) return;

  clearCurrent();
  state.current = { moduleId, featureId };
  saveShell();
  setHash(moduleId, featureId);
  renderNav();

  setCrumb(
    `${feature.icon || ""} ${feature.name}`.trim(),
    `${module.icon || ""} ${module.name}${module.gameVersion ? ` · 数据 ${module.gameVersion}` : ""}`,
  );
  updateMeta();

  const view = $("#view");
  view.innerHTML = `<div class="loading">加载中…</div>`;

  if (!feature.uiUrl) {
    view.innerHTML = `
      <div class="card">
        <h2>这个功能没有前端界面</h2>
        <p class="muted">它只提供了后端动作：<code>${(feature.actions || []).join("、") || "（无）"}</code></p>
        <p class="muted">要给它做界面，在 <code>${escapeHtml(feature.baseUrl)}/ui.js</code> 里写一个 <code>export default { mount(root, ctx) }</code>。</p>
      </div>`;
    return;
  }

  if (feature.styleUrl) {
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = feature.styleUrl;
    document.head.appendChild(link);
    state.styleEl = link;
  }

  try {
    // 带时间戳，改完 ui.js 刷新页面就是新的，不用清缓存
    const mod = await import(`${feature.uiUrl}?t=${Date.now()}`);
    const component = mod.default || {};
    view.innerHTML = "";
    if (typeof component.mount === "function") {
      const ctx = makeCtx(module, feature);
      const mountCleanup = await component.mount(view, ctx);
      const stopSaving = ctx.persistence?.bind(view, component.getState ? () => component.getState() : undefined);
      state.cleanup = () => { stopSaving?.(); if (typeof mountCleanup === "function") mountCleanup(); component.unmount?.(); };
    } else {
      view.innerHTML = `<div class="card error">ui.js 里没有 <code>export default { mount }</code>。</div>`;
    }
  } catch (err) {
    view.innerHTML = `<div class="card error">
      <h2>界面加载失败</h2>
      <p class="error-text">${escapeHtml(err.message)}</p>
      <p class="muted small">检查 <code>${escapeHtml(feature.uiUrl)}</code> 是否有语法错误（浏览器 F12 控制台里有详细信息）。</p>
    </div>`;
  }
}

function updateMeta() {
  const { module, feature } = findFeature(state.current.moduleId, state.current.featureId);
  if (!module || !feature) {
    $("#meta").textContent = "";
    return;
  }
  const bits = [`v${module.version || "0.0.0"}`];
  if (feature.actions?.length) bits.push(`${feature.actions.length} 个后端动作`);
  if (module.dataFiles?.length) bits.push(`数据：${module.dataFiles.join(" / ")}`);
  $("#meta").textContent = bits.join(" · ");
}

/* ---------------- 内置页面 ---------------- */

async function openGuide() {
  clearCurrent();
  state.current = { moduleId: null, featureId: null };
  clearHash();
  renderNav();
  setCrumb("📘 扩展指南", "怎么加功能、加游戏、更新数据");
  $("#meta").textContent = "";
  const view = $("#view");
  view.innerHTML = `<div class="loading">加载文档…</div>`;
  try {
    const data = await getJSON("/api/docs/EXTENDING.md");
    view.innerHTML = `<div class="card md">${renderMarkdown(data.text)}</div>`;
  } catch (err) {
    view.innerHTML = `<div class="card error">读不到 docs/EXTENDING.md：${escapeHtml(err.message)}</div>`;
  }
}

async function openStatus() {
  clearCurrent();
  state.current = { moduleId: null, featureId: null };
  clearHash();
  renderNav();
  setCrumb("🩺 模块状态", "加载结果与错误诊断");
  $("#meta").textContent = "";

  const view = $("#view");
  const reg = state.registry;
  const scan = reg?.scan || {};
  const errors = reg?.errors || [];

  const moduleCards = (reg?.modules || [])
    .map(
      (m) => `
      <div class="card">
        <h2>${escapeHtml(m.icon || "🎮")} ${escapeHtml(m.name)} <span class="pill">${escapeHtml(m.id)}</span></h2>
        <p class="muted small">${escapeHtml(m.description || "（没有描述）")}</p>
        <p class="muted small">目录：<code>modules/${escapeHtml(m.folder)}</code> · 版本 ${escapeHtml(m.version)}
          ${m.gameVersion ? ` · 数据版本 ${escapeHtml(m.gameVersion)}` : ""}</p>
        <table class="data">
          <thead><tr><th>功能</th><th>ID</th><th>前端</th><th>后端动作</th></tr></thead>
          <tbody>
            ${(m.features || [])
              .map(
                (f) => `<tr>
                  <td>${escapeHtml(f.icon || "")} ${escapeHtml(f.name)}</td>
                  <td class="mono">${escapeHtml(f.id)}</td>
                  <td>${f.hasUi ? "✓" : "—"}</td>
                  <td class="mono">${(f.actions || []).join(", ") || "—"}</td>
                </tr>`,
              )
              .join("")}
          </tbody>
        </table>
      </div>`,
    )
    .join("");

  view.innerHTML = `
    <div class="card">
      <h2>加载概况</h2>
      <div class="stat-grid">
        <div class="stat"><div class="k">模块</div><div class="v">${scan.modules ?? (reg?.modules || []).length}</div></div>
        <div class="stat"><div class="k">功能</div><div class="v">${scan.features ?? "-"}</div></div>
        <div class="stat"><div class="k">后端动作已加载</div><div class="v">${scan.apisLoaded ?? "-"}</div></div>
        <div class="stat ${scan.apisFailed ? "accent" : ""}"><div class="k">加载失败</div><div class="v">${scan.apisFailed ?? 0}</div></div>
      </div>
      <div class="hint">加完新功能点「↻ 重新扫描」，不用重启程序。</div>
    </div>

    <div class="card ${errors.length ? "error" : ""}">
      <h2>诊断（${errors.length} 条）</h2>
      ${
        errors.length
          ? `<table class="data"><thead><tr><th>位置</th><th>问题</th></tr></thead><tbody>${errors
              .map(
                (e) =>
                  `<tr><td class="mono">${escapeHtml(e.scope || "-")}</td><td>${escapeHtml(e.error || "")}${
                    e.file ? `<div class="muted small mono">${escapeHtml(e.file)}</div>` : ""
                  }</td></tr>`,
              )
              .join("")}</tbody></table>`
          : `<p class="muted">一切正常。</p>`
      }
    </div>

    ${moduleCards}
  `;
}

/* ---------------- 极简 Markdown 渲染（够用就好） ---------------- */

function renderMarkdown(md) {
  const lines = String(md).split(/\r?\n/);
  const out = [];
  let inCode = false;
  let codeBuf = [];
  let listBuf = [];

  const flushList = () => {
    if (listBuf.length) {
      out.push(`<ul>${listBuf.map((li) => `<li>${inline(li)}</li>`).join("")}</ul>`);
      listBuf = [];
    }
  };

  const inline = (text) =>
    escapeHtml(text)
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');

  for (const raw of lines) {
    const line = raw.replace(/\s+$/, "");
    if (line.trim().startsWith("```")) {
      if (inCode) {
        out.push(`<pre><code>${escapeHtml(codeBuf.join("\n"))}</code></pre>`);
        codeBuf = [];
        inCode = false;
      } else {
        flushList();
        inCode = true;
      }
      continue;
    }
    if (inCode) {
      codeBuf.push(raw);
      continue;
    }
    if (/^#{1,6}\s/.test(line)) {
      flushList();
      const level = Math.min(line.match(/^#+/)[0].length + 1, 4);
      out.push(`<h${level}>${inline(line.replace(/^#+\s*/, ""))}</h${level}>`);
      continue;
    }
    if (/^\s*[-*]\s+/.test(line)) {
      listBuf.push(line.replace(/^\s*[-*]\s+/, ""));
      continue;
    }
    flushList();
    if (!line.trim()) continue;
    out.push(`<p>${inline(line)}</p>`);
  }
  if (inCode) out.push(`<pre><code>${escapeHtml(codeBuf.join("\n"))}</code></pre>`);
  flushList();
  return out.join("\n");
}

/* ---------------- 启动 ---------------- */

function renderWarnings() {
  const errors = state.registry?.errors || [];
  const badge = $("#err-badge");
  badge.textContent = String(errors.length);
  badge.classList.toggle("hidden", errors.length === 0);

  const box = $("#warnings");
  if (!errors.length) {
    box.innerHTML = "";
    return;
  }
  box.innerHTML = `<div class="warnbar">有 ${errors.length} 条加载警告（${escapeHtml(
    errors[0].scope || "",
  )}${errors.length > 1 ? " 等" : ""}）。<button class="ghost small" id="show-status">查看</button></div>`;
  $("#show-status").addEventListener("click", openStatus);
}

async function loadRegistry() {
  const data = await getJSON("/api/registry");
  state.registry = data;
  $("#brand-version").textContent = `v${data.toolbox?.version || "?"} · ${
    (data.modules || []).length
  } 个模块`;
  renderNav();
  renderWarnings();
}

async function rescan() {
  const btn = $("#rescan");
  btn.disabled = true;
  btn.textContent = "扫描中…";
  try {
    await getJSON("/api/reload", { method: "POST" });
    await loadRegistry();
    if (state.current.moduleId) {
      openFeature(state.current.moduleId, state.current.featureId);
    }
  } catch (err) {
    alert(`重新扫描失败：${err.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = "↻ 重新扫描";
  }
}

/* 左下角的「扩展指南 / 模块状态」是给作者排查问题的，用户包里不显示；
   只有 /api/health 说这是作者包（admin=true）时才放出来。 */
async function revealAdminOnly() {
  try {
    const data = await getJSON("/api/health");
    if (!data || !data.admin) return;
    document.querySelectorAll("[data-admin-only]").forEach((element) => {
      element.hidden = false;
    });
  } catch (err) {
    // 读不到就当用户包处理，什么都不显示
  }
}

function startHeartbeat() {
  const beat = () => {
    fetch("/api/heartbeat", { method: "POST" }).catch(() => {});
  };
  beat();
  setInterval(beat, 2000);
}

async function boot() {
  const saveStatus = document.createElement("div");
  saveStatus.id = "local-save-status"; saveStatus.setAttribute("role", "status");
  document.body.append(saveStatus);
  window.addEventListener("gt-save-status", event => {
    saveStatus.textContent = event.detail.text; saveStatus.classList.toggle("is-error", event.detail.failed);
  });
  try { await window.GT_LOCAL_STATE.init(true); persistenceReady = true; }
  catch { /* 状态读取错误已显示；不能用默认值覆盖原文件。 */ }
  const savedShell = shellState()?.load() || {};
  state.filter = typeof savedShell.filter === "string" ? savedShell.filter : "";
  $("#search").value = state.filter;
  if (Array.isArray(savedShell.collapsed)) { navCollapsed.clear(); savedShell.collapsed.forEach(id => navCollapsed.add(id)); }
  $("#search").addEventListener("input", (event) => {
    state.filter = event.target.value;
    saveShell();
    renderNav();
  });
  $("#rescan").addEventListener("click", rescan);
  document.querySelectorAll("[data-page]").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (btn.dataset.page === "guide") openGuide();
      else openStatus();
    });
  });
  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      $("#search").focus();
      $("#search").select();
    }
  });

  startHeartbeat();

  // 先套用用户保存的外观与文字（读 userdata，失败就用默认继续启动）
  await window.GTTheme.load();
  await window.GTText.load();
  await revealAdminOnly();
  watchTextOverrides();

  try {
    await loadRegistry();
    const deep = parseHash() || savedShell.current;
    if (deep) {
      const { module, feature } = findFeature(deep.moduleId, deep.featureId);
      if (module && feature) openFeature(deep.moduleId, deep.featureId);
    }
  } catch (err) {
    $("#view").innerHTML = `<div class="card error">
      <h2>连不上本地服务</h2>
      <p class="error-text">${escapeHtml(err.message)}</p>
      <p class="muted">确认工具箱进程还在运行，然后刷新页面。</p>
    </div>`;
  }
}

boot();
