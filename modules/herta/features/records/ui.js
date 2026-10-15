/* 角色顶分：按模式/关卡浏览 The Herta 采集的低配通关阵容，支持按角色名筛选 */

const MODES = ["混沌回忆", "虚构叙事", "末日幻影", "异相仲裁"];

function esc(v) {
  return String(v ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

function resultText(r) {
  // 末日幻影没有轮次只有积分，异相仲裁部分记录只有 AV：有什么显示什么
  const has = (v) => v != null && v !== "";
  const parts = [];
  if (has(r.cycle)) parts.push(`${r.cycle} 轮`);
  if (has(r.score)) parts.push(`${r.score} 分`);
  if (has(r.av)) parts.push(`AV ${r.av}`);
  return parts.length ? parts.join(" · ") : String(r.tag ?? "—");
}

// 光锥：图标（对得上才有）+ 名字 + 叠影；没有光锥数据就只显示 S
function lcHTML(c, lcIcons) {
  const lc = c.lightcone ? String(c.lightcone) : "";
  const icon = lc && lcIcons[lc]
    ? `<img class="hr-lc-img" src="${esc(avatarSrc(lcIcons[lc]))}" alt="" loading="lazy" onerror="this.remove()">`
    : "";
  const name = lc ? `<span class="hr-lc-name">${esc(lc)}</span>` : "";
  return `<div class="hr-lc"${lc ? ` title="${esc(lc)} S${esc(c.superimposition)}"` : ""}>${icon}${name}`
    + `<span class="hr-lc-s">S${esc(c.superimposition)}</span></div>`;
}

// 头像：站内路径在单文件网页版里换成内联的 data URI；图片加载失败退回首字圆圈
function avatarSrc(path) {
  return path && path.startsWith("/") ? (window.GT_ASSETS || {})[path] || path : path;
}

function cardHTML(r, q, avatars, lcIcons) {
  const lineup = (r.lineup || []).map((c) => {
    const name = String(c.name ?? "");
    const avatar = [...name][0] ?? "";
    const match = q && name.toLowerCase().includes(q) ? " is-match" : "";
    const up = c.eidolon > 0 ? " is-up" : "";
    return `<div class="hr-char${match}">`
      + `<div class="hr-avatar">${avatars[name]
        ? `<img class="hr-avatar-img" src="${esc(avatarSrc(avatars[name]))}" alt="" loading="lazy" onerror="this.parentNode.textContent=this.dataset.f" data-f="${esc(avatar)}">`
        : esc(avatar)}</div>`
      + `<div class="hr-name" title="${esc(name)}">${esc(name)}</div>`
      + `<div class="hr-cons${up}">E${esc(c.eidolon)}</div>`
      + lcHTML(c, lcIcons)
      + `</div>`;
  }).join("");
  return `<div class="hr-card">`
    + `<div class="hr-card-head"><span class="hr-group">${esc(r.group)}</span><span class="hr-runs">${esc(r.runs_in_group)} 条同组</span></div>`
    + `<div class="hr-lineup">${lineup}</div>`
    + `<div class="hr-stats">`
    + `<span class="hr-pill hr-ltd">限定 ${esc(r.ltd)}</span>`
    + `<span class="hr-pill hr-std">常驻 ${esc(r.std)}</span>`
    + `<span class="hr-pill">${esc(resultText(r))}</span>`
    + `</div>`
    + `<div class="hr-date">${esc(r.date)}</div>`
    + `</div>`;
}

export default {
  title: "角色顶分",
  async mount(root, ctx) {
    let res = null;
    let mode = null;
    let selIdx = 0;
    let query = "";

    const targetsOf = () => ((res && res.data) || {}).targets || [];
    const firstIdxOfMode = (m) => targetsOf().findIndex((t) => t.mode === m);

    async function doLoad(refresh) {
      const btn = root.querySelector(".hr-refresh");
      if (btn) {
        btn.disabled = true;
        btn.textContent = "刷新中…";
      }
      try {
        res = await ctx.call("load", { refresh });
      } catch (err) {
        renderError(err && err.message != null ? err.message : String(err));
        return;
      }
      query = "";
      buildAll();
    }

    function renderError(message) {
      root.innerHTML = `<div class="hr-wrap"><div class="hr-note">加载失败：${esc(message)}</div><button class="hr-refresh">重试</button></div>`;
      root.querySelector(".hr-refresh").addEventListener("click", () => doLoad(true));
    }

    function buildAll() {
      const targets = targetsOf();
      mode = MODES.find((m) => targets.some((t) => t.mode === m)) ?? null;
      selIdx = mode == null ? 0 : firstIdxOfMode(mode);

      const noteHTML = res.offline ? `<div class="hr-note">${esc(res.note)}</div>` : "";
      root.innerHTML = `<div class="hr-wrap">`
        + `<div class="hr-top">`
        + `<div class="hr-tabs"></div>`
        + `<div class="hr-tools">`
        + `<input class="hr-search" type="search" placeholder="按角色名筛选，如 爻光">`
        + `<button class="hr-refresh">刷新</button>`
        + `<span class="hr-status"></span>`
        + `</div>`
        + `</div>`
        + `<div class="hr-stagebar">`
        + `<label class="hr-label">关卡</label>`
        + `<select class="hr-stage"></select>`
        + `<span class="hr-chip"></span>`
        + `<span class="hr-meta"></span>`
        + `</div>`
        + noteHTML
        + `<div class="hr-grid"></div>`
        + `<div class="hr-footer"></div>`
        + `</div>`;

      const status = root.querySelector(".hr-status");
      status.className = res.offline ? "hr-status is-offline" : "hr-status is-ok";
      status.textContent = res.offline
        ? `离线缓存 · ${res.fetched_at ?? ""}`
        : `已连接：${res.mirror ?? ""} · ${res.fetched_at ?? ""}`;
      status.title = (res.attempts || [])
        .map((a) => `${a.name} ${a.ok ? "✓" : "✗"} ${a.ms}ms ${a.error ?? ""}`)
        .join("\n");

      const data = res.data || {};
      root.querySelector(".hr-footer").textContent =
        `数据来自 The Herta（theherta.com），每天 12 点更新 · 采集于 ${data.collected_at ?? ""} · ${data.selection_rule ?? ""}`;

      renderTabs();
      renderStage();
      renderGrid();

      root.querySelector(".hr-search").addEventListener("input", (e) => {
        query = e.target.value.replace(/\s+/g, "");
        renderGrid();
      });
      root.querySelector(".hr-stage").addEventListener("change", (e) => {
        selIdx = Number(e.target.value);
        renderGrid();
      });
      root.querySelector(".hr-refresh").addEventListener("click", () => doLoad(true));
      root.querySelector(".hr-tabs").addEventListener("click", (e) => {
        const btn = e.target.closest(".hr-tab");
        if (!btn || btn.dataset.mode === mode) return;
        mode = btn.dataset.mode;
        selIdx = firstIdxOfMode(mode);
        renderTabs();
        renderStage();
        renderGrid();
      });
    }

    function renderTabs() {
      const targets = targetsOf();
      root.querySelector(".hr-tabs").innerHTML = MODES
        .filter((m) => targets.some((t) => t.mode === m))
        .map((m) => {
          const first = targets.find((t) => t.mode === m);
          const active = m === mode ? " is-active" : "";
          return `<button class="hr-tab${active}" data-mode="${esc(m)}">${esc(m)}<span class="hr-season">${esc(first ? first.season : "")}</span></button>`;
        })
        .join("");
    }

    function renderStage() {
      const sel = root.querySelector(".hr-stage");
      sel.innerHTML = targetsOf()
        .map((t, i) => (t.mode === mode ? `<option value="${i}">${esc(t.stage)} · ${esc(t.category)}</option>` : ""))
        .join("");
      sel.value = String(selIdx);
    }

    function renderGrid() {
      const target = targetsOf()[selIdx];
      const q = query.toLowerCase();
      const records = (target && target.records) || [];
      const list = q
        ? records.filter((r) => (r.lineup || []).some((c) => String(c.name ?? "").toLowerCase().includes(q)))
        : records;

      const body = list.length
        ? `<div class="hr-grid">${list.map((r) => cardHTML(r, q, res.avatars || {}, res.lightcone_icons || {})).join("")}</div>`
        : `<div class="hr-empty">没有符合条件的记录</div>`;
      const old = root.querySelector(".hr-grid") || root.querySelector(".hr-empty");
      if (old) old.outerHTML = body;
      else root.querySelector(".hr-footer").insertAdjacentHTML("beforebegin", body);

      root.querySelector(".hr-chip").textContent = target ? (target.category ?? "") : "";
      root.querySelector(".hr-meta").textContent = target
        ? `共 ${target.total_runs} 条记录 · 显示 ${list.length} 组`
        : "共 0 条记录 · 显示 0 组";
    }

    await doLoad(false);
  },
  unmount() {},
};
