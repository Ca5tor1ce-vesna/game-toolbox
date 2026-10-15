/* 配速查询：选角色 →（同命途）光锥 → 星魂/遗器 → 各模式各 T 数各动数的需求速度。
 *
 * 数学全在 api.py；这里负责选择与呈现。注意两个刻意的设计：
 *   1. 光锥只列同命途的（角色装不了别的命途）；
 *   2. 自动抽出来的速度效果默认只勾「看起来无条件」的，其余留给你判断——
 *      界面会把原文摆出来，公式里也标明每一条的来源。
 */

export default {
  title: "配速查询",

  async mount(root, ctx) {
    const esc = (text) => ctx.ui.escapeHtml(String(text ?? ""));
    const fix = (value, digits = 2) =>
      Number.isFinite(Number(value)) ? Number(value).toFixed(digits) : "-";

    let catalog;
    try {
      catalog = await ctx.call("catalog");
    } catch (err) {
      root.innerHTML = `<div class="card error"><h2 data-text="speed-plan.card.error">读不到数据</h2><p class="error-text">${esc(
        err.message,
      )}</p><p class="muted small">先在项目目录跑一次 <code>python tools/import_hsr_data.py</code>。</p></div>`;
      return;
    }

    const state = {
      characterId: catalog.characters[0]?.id || null,
      lightconeId: null,
      superimpose: 5,
      eidolon: 0,
      enabled: null, // null = 用后端的默认勾选
      relic: {
        speedBoots: true,
        fourPieceId: "",
        fourPieceUlts: 0,
        ultTargetsAlly: false,
        ornamentIds: ["", ""],
        substatSpeed: 0,
        customPct: 0,
        customFlat: 0,
      },
      advance: { coneUlts: 0, custom: 0, excludeLastUlt: false },
      // 模拟参数：第一次开大发生在自己第几次行动之后（只管"开大才提速"的加速）
      simulation: { firstUltAction: 1 },
      target: { t: 0, actions: 2, customAV: 0, mode: catalog.modes?.[0]?.id || "moc" },
    };

    const charById = new Map(catalog.characters.map((item) => [String(item.id), item]));
    let cones = [];

    root.innerHTML = `
      <div class="card">
        <h2 data-text="speed-plan.card.pick">🎯 选角色与配装</h2>
        <div class="picker-layout">
          <div class="splash-panel">
            <img id="splash" alt="角色立绘" />
            <div class="splash-meta" id="splash-meta">选个角色</div>
          </div>
          <div class="picker-controls">
            <div class="row">
              <div class="field"><label>角色（越新推出的越靠上）</label>
                <button id="character-picker" type="button" class="picker-button"></button>
              </div>
              <div class="field"><label>光锥（只显示同命途）</label>
                <button id="lightcone-picker" type="button" class="picker-button"></button>
              </div>
              <div class="field"><label>叠影</label>
                <select id="superimpose" class="input narrow">
                  <option>1</option><option>2</option><option>3</option><option>4</option><option selected>5</option>
                </select>
              </div>
              <div class="field"><label>星魂</label>
                <select id="eidolon" class="input narrow">
                  <option value="0" selected>0 魂</option><option value="1">1 魂</option><option value="2">2 魂</option>
                  <option value="3">3 魂</option><option value="4">4 魂</option><option value="5">5 魂</option><option value="6">6 魂</option>
                </select>
              </div>
            </div>
            <div class="row" style="margin-top:10px">
              <div class="field"><label>我的配装（存在 userdata，升级不丢）</label>
                <select id="preset" class="input wide"></select>
              </div>
              <button id="save-preset" class="btn secondary">存为我的配装</button>
              <button id="delete-preset" class="ghost">删除</button>
            </div>
            <p class="hint" id="preset-note"></p>
            <div id="pick-summary" class="pick-summary">
              <div class="ps-title">已选配装（直接在这里改）</div>
              <div class="ps-row"><span>遗器 4 件套</span>
                <button id="fourPiece-picker-top" type="button" class="picker-button"></button></div>
              <div class="ps-row"><span>位面饰品</span>
                <button id="ornamentA-picker-top" type="button" class="picker-button"></button></div>
              <div class="ps-row"><span>速度鞋 / 副词条</span>
                <span class="ps-controls">
                  <label class="ps-check"><input id="speedBootsTop" type="checkbox" /> 速度鞋 +25</label>
                  <label class="ps-label">副词条合计</label>
                  <input id="substatTop" class="input tiny" type="number" value="0" min="0" step="1" />
                </span></div>
              <div class="ps-row"><span>其它加成</span>
                <span class="ps-controls">
                  <label class="ps-label">速度 %</label>
                  <input id="customPct-panel" class="input tiny" type="number" value="0" step="1" />
                  <label class="ps-label">固定速度</label>
                  <input id="customFlat-panel" class="input tiny" type="number" value="0" step="1" />
                </span></div>
              <div class="ps-row"><span>开大 / 拉条</span>
                <span class="ps-controls">
                  <label class="ps-label">开大次数</label>
                  <input id="fourUltsTop" class="input tiny" type="number" value="0" min="0" step="1" />
                  <label class="ps-label">光锥开大</label>
                  <input id="coneUlts-panel" class="input tiny" type="number" value="0" min="0" step="1" />
                  <label class="ps-label">其它拉条 %</label>
                  <input id="advCustom-panel" class="input tiny" type="number" value="0" step="5" />
                  <label class="ps-check"><input id="excludeLastUltTop" type="checkbox" /> 轴底开大</label>
                  <label class="ps-check"><input id="ultTargetsAllyTop" type="checkbox" /> 开大打队友</label>
                </span></div>
              <div class="ps-row"><span>首次开大</span>
                <span class="ps-controls">
                  <label class="ps-label">第</label>
                  <input id="firstUltAction-panel" class="input tiny" type="number" value="1" min="1" step="1" />
                  <label class="ps-label">次行动后（只影响「开大才提速」的加速，不影响拉条）</label>
                </span></div>
              <div class="ps-row"><span>套装贡献</span><b id="ps-contrib">—</b></div>
              <div class="ps-title">配速结论</div>
              <div class="ps-row"><span>目标</span>
                <span class="ps-controls">
                  <select id="mode-panel" class="input small"></select>
                  <select id="targetT-panel" class="input small"></select>
                  <label class="ps-label">动数</label>
                  <input id="targetActions-panel" class="input tiny" type="number" value="2" min="1" max="12" />
                  <label class="ps-label">或行动值</label>
                  <input id="customAV-panel" class="input tiny" type="number" value="0" min="0" step="10" />
                  <span class="ps-label" id="ps-target"></span>
                </span></div>
              <div class="ps-row"><span>需要速度</span><b class="ps-need" id="ps-need">—</b></div>
              <div class="ps-row"><span>当前速度</span><b id="ps-current">—</b></div>
              <div class="ps-row"><span id="ps-gap-label">还差</span><b id="ps-gap">—</b></div>
              <div class="ps-row"><span>该行动值能打</span><b id="ps-actions">—</b></div>
              <div class="ps-row" id="ps-timeline-row" style="display:none"><span>行动时间线</span><b id="ps-timeline"></b></div>
            </div>
          </div>
        </div>
        <p class="hint" id="char-info"></p>
      </div>

      <div class="card">
        <h2 data-text="speed-plan.card.speed">⚡ 实际速度</h2>
        <div class="row">
          <div class="field check"><input id="speedBoots" type="checkbox" checked /><label for="speedBoots">速度鞋（主词条 +25）</label></div>
          <div class="field"><label>遗器 4 件套</label>
            <button id="fourPiece-picker" type="button" class="picker-button"></button>
          </div>
          <div class="field"><label>开大次数（风套这类按次触发）</label><input id="fourUlts" class="input narrow" type="number" value="0" min="0" step="1" /></div>
          <div class="field check"><input id="ultTargetsAlly" type="checkbox" /><label for="ultTargetsAlly">开大目标是队友（信使 4 件套才生效）</label></div>
          <div class="field"><label>位面饰品</label>
            <button id="ornamentA-picker" type="button" class="picker-button"></button>
          </div>
          <div class="field"><label>副词条速度合计</label><input id="substat" class="input narrow" type="number" value="0" step="1" /></div>
          <div class="field"><label>其它速度 %</label><input id="customPct" class="input narrow" type="number" value="0" step="1" /></div>
          <div class="field"><label>其它固定速度</label><input id="customFlat" class="input narrow" type="number" value="0" step="1" /></div>
        </div>
        <p class="hint" id="relic-note">套装效果从官方文案里带出来：风套（开大拉条 25%）、翁瓦克（速度 ≥ 120 才计入进战拉条 40%）、速度 2 件套选中即自动计入。信使 4 件套要再勾「开大目标是队友」。</p>

        <div class="stat-grid" style="margin-top:12px">
          <div class="stat accent"><div class="k">实际速度</div><div class="v" id="r-speed">-</div></div>
          <div class="stat"><div class="k">基础速度</div><div class="v" id="r-base">-</div></div>
          <div class="stat"><div class="k">速度 % / 固定</div><div class="v small" id="r-split">-</div></div>
          <div class="stat"><div class="k">单动行动值</div><div class="v" id="r-av">-</div></div>
        </div>
        <p class="formula" id="r-formula"></p>
        <div id="r-breakdown"></div>
        <div id="r-relics"></div>

        <h3>检测到的速度效果（勾选后计入上表）</h3>
        <div id="r-effects"></div>
        <div id="r-advance-effects"></div>
      </div>

      <div class="card">
        <h2 data-text="speed-plan.card.advance">🌀 拉条来源</h2>
        <p class="hint">遗器套装的拉条（风套、翁瓦克）在「实际速度」卡片里选套装就自动带入；这里管光锥和其它。</p>
        <div class="row">
          <div class="field"><label>光锥开大次数</label><input id="coneUlts" class="input narrow" type="number" value="0" min="0" step="1" /></div>
          <div class="field"><label>其它拉条 %</label><input id="advCustom" class="input narrow" type="number" value="0" step="5" /></div>
        </div>
        <div id="r-cone-advance"></div>
        <p class="hint" id="r-advance"></p>
      </div>

      <div class="card">
        <h2 data-text="speed-plan.card.targets">📋 需求速度：各模式 × T 数 × 动数</h2>
        <div class="row">
          <div class="field"><label>目标模式</label><select id="mode" class="input wide"></select></div>
          <div class="field"><label>目标 T 数</label><select id="targetT" class="input narrow"></select></div>
          <div class="field"><label>目标动数</label><input id="targetActions" class="input narrow" type="number" value="2" min="1" max="8" step="1" /></div>
          <div class="field"><label>或直接指定行动值（0 = 按 T 数）</label>
            <div class="row tight">
              <input id="customAV" class="input narrow" type="number" value="0" min="0" step="10" />
              <button class="ghost small" data-av="150">150</button>
              <button class="ghost small" data-av="250">250</button>
              <button class="ghost small" data-av="300">300</button>
            </div>
          </div>
          <div class="field check">
            <input id="excludeLastUlt" type="checkbox" />
            <label for="excludeLastUlt">轴底开大（最后一次开大的拉条不计入）</label>
          </div>
        </div>
        <div id="r-verdict"></div>
        <div id="r-suggestions"></div>
        <div id="r-tables"></div>
      </div>

      <div class="card">
        <h2 data-text="speed-plan.card.recommend">🧠 自动推荐配装</h2>
        <p class="hint">
          在你这个角色能用的光锥与遗器范围内穷举一遍，找出「达成当前目标最省」的几套。
          这是自动算出来的最优解，<b>不是社区主流配装表</b>（那个数据源拿不到）。
        </p>
        <div class="row">
          <div class="field"><label>光锥开大次数</label><input id="recConeUlts" class="input narrow" type="number" value="1" min="0" step="1" /></div>
          <div class="field"><label>风套开大次数</label><input id="recFourUlts" class="input narrow" type="number" value="1" min="0" step="1" /></div>
          <div class="field"><label>光锥叠影</label>
            <select id="recS" class="input narrow"><option>1</option><option>2</option><option>3</option><option>4</option><option selected>5</option></select>
          </div>
          <button id="rec-btn" class="btn">算一下哪套最省</button>
        </div>
        <div id="r-recommend"></div>
      </div>
    `;

    /* ---------------- 角色 / 光锥 ---------------- */

    /* ---------------- 官方图：按需下载 + 本地缓存 ---------------- */

    // 工具箱里图片走本地缓存接口（/api/asset 会下载一次并缓存到 userdata）；
    // 独立网页版（window.GT_STANDALONE）没有服务端，直接指向官方 CDN。
    const assetUrl = (remote) => {
      if (!remote) return "";
      // 本地化素材是站内路径（/modules/...）：工具箱里原样用（不能过 /api/asset，会被域名白名单拦）；
      // 单文件网页版查 window.GT_ASSETS 内联表，查不到就原样（立绘会 onerror 退回 splashFallback）。
      if (remote.startsWith("/")) return (window.GT_ASSETS || {})[remote] || remote;
      return window.GT_STANDALONE ? remote : `/api/asset?url=${encodeURIComponent(remote)}`;
    };

    function updateSplash() {
      const character = charById.get(String(state.characterId)) || {};
      const image = root.querySelector("#splash");
      const source = character.splash || "";
      const fallback = character.splashFallback || "";
      if (source || fallback) {
        // 优先游戏内立绘预览；取不到就退回米游社那张（带角标），再取不到就藏起来
        image.onerror = () => {
          if (fallback && image.src !== assetUrl(fallback)) {
            image.src = assetUrl(fallback);
          } else {
            image.style.visibility = "hidden";
          }
        };
        image.src = assetUrl(source || fallback);
        image.style.visibility = "visible";
      } else {
        image.onerror = null;
        image.removeAttribute("src");
        image.style.visibility = "hidden";
      }
      const trace = Number(character.traceSpeed || 0);
      const speed = character.effectiveBaseSpeed ?? character.baseSpeed;
      root.querySelector("#splash-meta").innerHTML =
        `<b>${esc(character.name || "选个角色")}</b><br/>` +
        `<span class="row-meta">${esc(character.pathName || "")} · ${esc(character.elementName || "")}${
          character.rarity ? ` · ${character.rarity}★` : ""
        }</span><br/>` +
        `<span class="row-meta">初始速度 ${fix(speed, 0)}${
          trace ? `（基础 ${fix(character.baseSpeed, 0)} + 行迹 ${fix(trace, 0)}）` : ""
        }</span>`;
    }

    /* ---------------- 带官方图的下拉 ----------------
       原生 <select> 塞不进图片，所以自己做一个：按钮 + 浮层 + 搜索。 */

    function createPicker({ buttonId, placeholder, searchPlaceholder, onPick }) {
      const button = root.querySelector(buttonId);
      const popup = document.createElement("div");
      popup.className = "picker-popup hidden";
      popup.innerHTML =
        `<input class="input picker-search" placeholder="${esc(searchPlaceholder || "搜索…")}" />` +
        `<div class="picker-list"></div>`;
      // 挂在功能容器里：切走功能时会被一起清掉
      root.appendChild(popup);
      const search = popup.querySelector(".picker-search");
      const list = popup.querySelector(".picker-list");
      let items = [];
      let current = "";

      const image = (remote) =>
        `<img src="${esc(assetUrl(remote))}" onerror="this.style.visibility='hidden'" alt="" />`;

      function renderButton() {
        const item = items.find((entry) => String(entry.id) === String(current));
        button.innerHTML =
          image(item?.icon) +
          `<span class="pb-name">${esc(item ? item.name : placeholder)}</span>` +
          `<span class="pb-caret">▾</span>`;
      }

      function renderList() {
        const needle = search.value.trim().toLowerCase();
        const visible = needle
          ? items.filter((item) =>
              `${item.name} ${item.meta || ""}`.toLowerCase().includes(needle),
            )
          : items;
        list.innerHTML =
          visible
            .map(
              (item) =>
                `<button type="button" class="picker-item ${
                  String(item.id) === String(current) ? "active" : ""
                }" data-id="${esc(item.id)}" title="${esc(item.title || item.meta || "")}">` +
                image(item.icon) +
                `<span class="pi-name">${esc(item.name)}</span>` +
                `<span class="pi-meta">${esc(item.meta || "")}</span></button>`,
            )
            .join("") || `<p class="hint" style="padding:8px">没有匹配项</p>`;
        list.querySelectorAll("[data-id]").forEach((element) => {
          element.addEventListener("click", () => {
            const picked = element.dataset.id;
            close();
            onPick(picked);
          });
        });
      }

      function open() {
        const rect = button.getBoundingClientRect();
        const margin = 8;
        // 浮层宽度不超过屏幕，位置也不许跑到屏幕外——手机上全靠这个
        const width = Math.min(
          Math.max(rect.width, 320),
          Math.max(240, window.innerWidth - margin * 2),
        );
        const left = Math.min(
          Math.max(margin, rect.left),
          Math.max(margin, window.innerWidth - width - margin),
        );
        popup.style.left = `${left}px`;
        popup.style.width = `${width}px`;
        popup.style.minWidth = "0";
        popup.style.top = `${margin}px`;
        popup.classList.remove("hidden");
        search.value = "";
        renderList();
        // 先显示再量高度：下方放不下就往上翻，上下都放不下就贴着屏幕
        const height = popup.offsetHeight || 360;
        const spaceBelow = window.innerHeight - rect.bottom - margin;
        let top = rect.bottom + 4;
        if (height > spaceBelow && rect.top - margin > spaceBelow) {
          top = rect.top - height - 4;
        }
        top = Math.min(
          Math.max(margin, top),
          Math.max(margin, window.innerHeight - height - margin),
        );
        popup.style.top = `${top}px`;
        search.focus();
      }

      function close() {
        popup.classList.add("hidden");
      }

      button.addEventListener("click", (event) => {
        event.stopPropagation();
        if (popup.classList.contains("hidden")) open();
        else close();
      });
      search.addEventListener("input", renderList);
      popup.addEventListener("click", (event) => event.stopPropagation());
      document.addEventListener("click", close);
      document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") close();
      });

      return {
        setItems(next, value) {
          items = next;
          if (value !== undefined) current = value;
          renderButton();
        },
        setValue(value) {
          current = value;
          renderButton();
        },
      };
    }

    const characterPicker = createPicker({
      buttonId: "#character-picker",
      placeholder: "选角色",
      searchPlaceholder: "搜索角色 / 命途 / 属性…",
      onPick: async (id) => {
        state.characterId = id;
        state.enabled = null;
        characterPicker.setValue(id);
        await loadCones();
        refreshPresets();
        updateSplash();
        run();
      },
    });

    const lightconePicker = createPicker({
      buttonId: "#lightcone-picker",
      placeholder: "（不装备光锥）",
      searchPlaceholder: "搜索光锥…",
      onPick: (id) => {
        state.lightconeId = id;
        state.enabled = null;
        lightconePicker.setValue(id);
        schedule();
      },
    });

    const fourPiecePicker = createPicker({
      buttonId: "#fourPiece-picker",
      placeholder: "（不用）",
      searchPlaceholder: "搜索遗器 4 件套…",
      onPick: (id) => {
        state.relic.fourPieceId = id;
        fourPiecePicker.setValue(id);
        schedule();
      },
    });

    const ornamentPicker = createPicker({
      buttonId: "#ornamentA-picker",
      placeholder: "（不用）",
      searchPlaceholder: "搜索位面饰品…",
      onPick: (id) => {
        state.relic.ornamentIds[0] = id;
        state.relic.ornamentIds[1] = "";
        ornamentPicker.setValue(id);
        ornamentTopPicker.setValue(id);
        schedule();
      },
    });

    /* 顶部快捷区的第二组控件：和下面的卡片共用同一份 state，改哪边都一样 */

    const fourPieceTopPicker = createPicker({
      buttonId: "#fourPiece-picker-top",
      placeholder: "（不用）",
      searchPlaceholder: "搜索遗器 4 件套…",
      onPick: (id) => {
        state.relic.fourPieceId = id;
        fourPiecePicker.setValue(id);
        fourPieceTopPicker.setValue(id);
        schedule();
      },
    });

    const ornamentTopPicker = createPicker({
      buttonId: "#ornamentA-picker-top",
      placeholder: "（不用）",
      searchPlaceholder: "搜索位面饰品…",
      onPick: (id) => {
        state.relic.ornamentIds[0] = id;
        state.relic.ornamentIds[1] = "";
        ornamentPicker.setValue(id);
        ornamentTopPicker.setValue(id);
        schedule();
      },
    });

    /** 把 state 刷到「上下两份」控件上（预设/推荐套用后要调用）。 */
    function syncRelicControls() {
      fourPiecePicker.setValue(state.relic.fourPieceId || "");
      fourPieceTopPicker.setValue(state.relic.fourPieceId || "");
      ornamentPicker.setValue(state.relic.ornamentIds?.[0] || "");
      ornamentTopPicker.setValue(state.relic.ornamentIds?.[0] || "");
      const pairs = [
        ["#speedBoots", "#speedBootsTop", !!state.relic.speedBoots],
        ["#substat", "#substatTop", state.relic.substatSpeed ?? 0],
        ["#fourUlts", "#fourUltsTop", state.relic.fourPieceUlts ?? 0],
        ["#excludeLastUlt", "#excludeLastUltTop", !!state.advance.excludeLastUlt],
        ["#ultTargetsAlly", "#ultTargetsAllyTop", !!state.relic.ultTargetsAlly],
      ];
      for (const [idA, idB, value] of pairs) {
        for (const id of [idA, idB]) {
          const element = root.querySelector(id);
          if (!element) continue;
          if (element.type === "checkbox") element.checked = !!value;
          else element.value = String(value);
        }
      }
    }

    /** 一对镜像控件：改任意一个，同步另一个并更新 state。 */
    function bindPair(idA, idB, eventName, apply) {
      const elements = [root.querySelector(idA), root.querySelector(idB)];
      elements.forEach((element, index) => {
        if (!element) return;
        element.addEventListener(eventName, (event) => {
          const value = element.type === "checkbox" ? element.checked : event.target.value;
          apply(value);
          const other = elements[index === 0 ? 1 : 0];
          if (other) {
            if (other.type === "checkbox") other.checked = !!value;
            else other.value = value;
          }
          schedule();
        });
      });
    }

    bindPair("#speedBoots", "#speedBootsTop", "change", (value) => {
      state.relic.speedBoots = !!value;
    });
    bindPair("#substat", "#substatTop", "input", (value) => {
      state.relic.substatSpeed = Number(value || 0);
    });
    bindPair("#fourUlts", "#fourUltsTop", "input", (value) => {
      state.relic.fourPieceUlts = Number(value || 0);
    });
    bindPair("#excludeLastUlt", "#excludeLastUltTop", "change", (value) => {
      state.advance.excludeLastUlt = !!value;
    });
    bindPair("#ultTargetsAlly", "#ultTargetsAllyTop", "change", (value) => {
      state.relic.ultTargetsAlly = !!value;
    });

    function setOptions(list) {
      return [
        { id: "", name: "（不用）", meta: "", icon: "" },
        ...list.map((set) => ({
          id: set.id,
          name: set.name,
          meta: describeSet(set),
          // 完整文案放 tooltip：下拉行里只显示短标签，否则长文案会把名字挤没
          title: set.summary || set.name,
          icon: set.icon,
        })),
      ];
    }

    function loadCharacterPicker() {
      characterPicker.setItems(
        catalog.characters.map((item) => {
          const trace = Number(item.traceSpeed || 0);
          const speed = item.effectiveBaseSpeed ?? item.baseSpeed;
          return {
            id: item.id,
            name: item.name,
            meta:
              `${item.pathName} · ${item.rarity}★ · ${fix(speed, 0)} 速` +
              (trace ? `（含行迹 +${fix(trace, 0)}）` : ""),
            icon: item.icon,
          };
        }),
        state.characterId,
      );
    }

    async function loadCones() {
      const character = charById.get(String(state.characterId));
      const data = await ctx.call("lightcones", { path: character?.path });
      cones = (data.lightcones || []).sort(
        (a, b) =>
          (b.rarity - a.rarity) || (Number(b.speedRelated) - Number(a.speedRelated)) ||
          a.name.localeCompare(b.name, "zh"),
      );
      state.lightconeId = cones[0]?.id || "";
      lightconePicker.setItems(
        [
          { id: "", name: "（不装备光锥）", meta: "", icon: "" },
          ...cones.map((cone) => ({
            id: cone.id,
            name: cone.name,
            meta: `${cone.rarity}★ · ${cone.pathName}${cone.speedRelated ? " · 配速相关" : ""}`,
            icon: cone.icon,
          })),
        ],
        state.lightconeId,
      );
    }

    /* ---------------- 重算 ---------------- */

    let timer = null;
    function schedule() {
      if (timer) clearTimeout(timer);
      timer = setTimeout(run, 150);
    }

    let effectSignature = "";

    async function run() {
      const character = charById.get(String(state.characterId));
      root.querySelector("#char-info").textContent = character
        ? `${character.name}｜${character.pathName}｜${character.elementName}｜${character.rarity}★｜基础速度 ${fix(character.baseSpeed, 0)}`
        : "";

      let result;
      try {
        // 模式一定要带上，否则后端不知道用哪套行动值口径
        const modeSelect = root.querySelector("#mode");
        if (modeSelect?.value) state.target.mode = modeSelect.value;
        result = await ctx.call("plan", {
          characterId: state.characterId,
          lightconeId: state.lightconeId || null,
          superimpose: state.superimpose,
          eidolon: state.eidolon,
          enabledEffects: state.enabled,
          relic: state.relic,
          advance: state.advance,
          target: state.target,
          // 模拟参数：第一次开大发生在自己第几次行动之后（只影响"开大才提速"的加速）
          simulation: state.simulation,
        });
      } catch (err) {
        root.querySelector("#r-formula").innerHTML = `<span class="error-text">${esc(err.message)}</span>`;
        return;
      }

      state.enabled = result.effects.enabled;

      const speed = result.speed;
      root.querySelector("#r-speed").textContent = fix(speed.final, 2);
      root.querySelector("#r-base").textContent = fix(speed.base, 0);
      root.querySelector("#r-split").textContent = `+${fix(speed.pct, 1)}% / +${fix(speed.flat, 1)}`;
      root.querySelector("#r-av").textContent = `${fix(10000 / Math.max(1, speed.final), 2)} AV`;
      root.querySelector("#r-formula").textContent = speed.formula;

      root.querySelector("#r-breakdown").innerHTML = speed.breakdown.length
        ? `<table class="data" style="margin-top:10px"><thead><tr><th>来源</th><th class="num">类型</th><th class="num">数值</th></tr></thead><tbody>${speed.breakdown
            .map(
              (item) =>
                `<tr><td>${esc(item.label)}${item.team ? ' <span class="pill">全队</span>' : ""}${
                  item.text ? `<div class="muted small">${esc(item.text)}</div>` : ""
                }</td><td class="num">${
                  item.kind === "pct" ? "速度 %" : item.kind === "base" ? "基础" : "固定速度"
                }</td><td class="num">${item.kind === "pct" ? "+" : item.kind === "base" ? "" : "+"}${fix(
                  item.value,
                  1,
                )}</td></tr>`,
            )
            .join("")}</tbody></table>`
        : `<p class="hint">还没有任何速度来源（只靠基础速度）。</p>`;

      // 效果清单：集合没变就不重建，免得勾选时列表跳动
      const signature = result.effects.speed.map((item) => item.id).join(",");
      if (signature !== effectSignature) {
        effectSignature = signature;
        renderEffects(result);
      } else {
        syncEffectCheckboxes(result);
      }

      // 遗器套装：生效的 + 有条件没计入的，都摆出来
      const applied = result.relicSets || [];
      const conditional = result.effects.conditional || [];
      const describeEffect = (effect) =>
        `${effect.slot} ${effect.kind === "pct" ? `速度 +${fix(effect.value, 1)}%` : effect.kind === "advance" ? `拉条 +${fix(effect.value, 0)}%` : `固定速度 +${fix(effect.value, 0)}`}`;
      root.querySelector("#r-relics").innerHTML =
        (applied.length
          ? `<h3>遗器套装生效</h3>` +
            applied
              .map(
                (set) =>
                  `<div class="effect-row"><span class="pill">${esc(set.label)}</span>` +
                  `<span class="grow"><b>${esc(set.setName)}</b>　${set.effects
                    .map((effect) => esc(describeEffect(effect)))
                    .join("；")}</span></div>`,
              )
              .join("")
          : "") +
        (conditional.length
          ? `<h3>有条件的效果（未计入，需要的话自己加到「其它」里）</h3>` +
            conditional
              .map(
                (effect) =>
                  `<div class="effect-row"><span class="pill">${esc(effect.setName)}·${esc(effect.slot)}</span>` +
                  `<span class="grow">${esc(effect.text)}</span>` +
                  `<span class="num">${esc(describeEffect(effect))}</span></div>`,
              )
              .join("")
          : "");

      root.querySelector("#r-advance-effects").innerHTML = result.effects.advance.length
        ? `<h3>检测到的拉条效果（参考，换算成上面的「其它拉条 %」）</h3>` +
          result.effects.advance
            .map(
              (item) =>
                `<div class="effect-row"><span class="pill">${esc(item.origin)}</span>` +
                `<span>${esc(item.text)}</span><span class="num">${fix(item.value, 0)}%</span></div>`,
            )
            .join("")
        : "";

      root.querySelector("#r-advance").innerHTML = result.advance.items.length
        ? `合计拉条 <b>${fix(result.advance.total, 1)}%</b>（折算 ${fix(result.advance.distance, 0)} 行动值距离）：` +
          result.advance.items.map((item) => esc(item.label)).join("；")
        : "没有拉条。";

      const verdict = result.verdict;
      root.querySelector("#r-verdict").innerHTML = `
        <div class="stat-grid" style="margin-top:12px">
          <div class="stat ${verdict.gap <= 0 ? "accent" : ""}"><div class="k">${verdict.t}T 内 ${verdict.actions} 动需要</div><div class="v">${fix(verdict.requiredSpeed, 2)}</div></div>
          <div class="stat"><div class="k">你当前速度</div><div class="v">${fix(verdict.currentSpeed, 2)}</div></div>
          <div class="stat ${verdict.gap > 0 ? "accent" : ""}"><div class="k">${verdict.gap > 0 ? "还差" : "富余"}</div><div class="v">${fix(Math.abs(verdict.gap), 2)}</div></div>
          <div class="stat"><div class="k">该行动值下能打</div><div class="v">${verdict.achievableActions} 动</div></div>
        </div>
        <p class="formula">${esc(verdict.text)}</p>
        ${(result.warnings || []).map((text) => `<p class="warnbar" style="margin-top:8px">${esc(text)}</p>`).join("")}
      `;

      renderTables(result);
      renderTargetOptions(result);
      renderPickSummary(result, verdict);

      // 光锥自带的拉条：告诉用户「你选了这把光锥，它能提供什么、要填几次开大」
      const coneAdvance = result.effects.coneAdvance || [];
      const coneConditional = result.effects.coneConditional || [];
      root.querySelector("#r-cone-advance").innerHTML =
        (coneAdvance.length
          ? `<h3>当前光锥的拉条</h3>` +
            coneAdvance
              .map(
                (item) =>
                  `<div class="effect-row"><span class="pill">叠影 ${item.superimpose}</span>` +
                  `<span class="grow">${esc(item.text)}</span>` +
                  `<span class="num">${item.counted !== undefined ? `已计入 ${fix(item.counted, 0)}%` : "填开大次数后计入"}</span></div>`,
              )
              .join("")
          : "") +
        (coneConditional.length
          ? coneConditional
              .map(
                (item) =>
                  `<div class="effect-row"><span class="pill">有条件</span>` +
                  `<span class="grow">${esc(item.text)}</span><span class="num">未计入</span></div>`,
              )
              .join("")
          : "");

      // 补足建议：差速度的时候给具体办法
      const suggestions = result.suggestions || [];
      root.querySelector("#r-suggestions").innerHTML = suggestions.length
        ? `<h3>怎么补上这 ${fix(Math.abs(verdict.gap), 2)} 速</h3><table class="data">
             <thead><tr><th>办法</th><th class="num">之后速度</th><th class="num">还需要</th><th>结果</th></tr></thead>
             <tbody>${suggestions
               .map(
                 (item) =>
                   `<tr><td>${esc(item.label)}</td><td class="num">${fix(item.speed, 1)}</td>` +
                   `<td class="num">${fix(Math.max(0, item.required), 1)}</td>` +
                   `<td>${item.ok ? "✅ 够了" : `还差 ${fix(item.gap, 1)}`}</td></tr>`,
               )
               .join("")}</tbody></table>`
        : "";
    }

    function renderEffects(result) {
      const list = result.effects.speed;
      const box = root.querySelector("#r-effects");
      if (!list.length) {
        box.innerHTML = `<p class="hint">这个角色 + 光锥组合没有检测到速度类效果。</p>`;
        return;
      }
      const TRIGGER_TEXT = {
        passive: { label: "常驻", hint: "开局就生效，默认勾上" },
        onEnter: { label: "进战", hint: "进入战斗时触发，开局即生效" },
        perUlt: { label: "开大", hint: "要开大才生效，按上面的「首次开大」时刻开始算" },
        conditional: { label: "条件", hint: "需要满足特定条件才生效，请自行判断" },
      };
      box.innerHTML = `<div class="effect-list">${list
        .map((item) => {
          const trigger = TRIGGER_TEXT[item.trigger] || TRIGGER_TEXT.conditional;
          // 只给队友的提速（「被指定的我方目标」这类）不算自己的速度
          const ally = item.apply === "ally";
          const allyBadge = ally
            ? `<span class="trigger-badge conditional" title="提速对象是队友，不是自己，不计入本角色速度">仅队友</span>`
            : "";
          return `
        <label class="effect-row ${ally ? "ally-only" : ""}" title="${esc(
          ally ? "这条提速给的是队友（不算作自己的速度）" : trigger.hint,
        )}">
          <input type="checkbox" data-effect="${esc(item.id)}" ${
            item.id in Object.fromEntries(result.effects.enabled.map((id) => [id, 1])) ? "checked" : ""
          } />
          <span class="pill">${esc(item.origin)}</span>
          <span class="trigger-badge ${esc(item.trigger || "conditional")}">${esc(trigger.label)}</span>
          ${allyBadge}
          <span class="grow">${esc(item.text)}</span>
          <span class="num">+${fix(item.value, 1)}${item.kind === "pct" ? "%" : ""}${
            item.apply === "team" ? "（全队）" : ""
          }</span>
        </label>`;
        })
        .join("")}</div>
      <p class="hint">「开大」类要按上面填的「首次开大」时刻开始生效；「条件」类不会自动计入，勾上表示你自己确认它成立；
      「仅队友」类的提速不算这个角色的速度。</p>`;

      box.querySelectorAll("[data-effect]").forEach((input) => {
        input.addEventListener("change", () => {
          const ids = new Set(state.enabled || []);
          if (input.checked) ids.add(input.dataset.effect);
          else ids.delete(input.dataset.effect);
          state.enabled = [...ids];
          schedule();
        });
      });
    }

    function syncEffectCheckboxes(result) {
      const enabled = new Set(result.effects.enabled);
      root.querySelectorAll("[data-effect]").forEach((input) => {
        input.checked = enabled.has(input.dataset.effect);
      });
    }

    /* ---------------- 表格 ---------------- */

    function currentMode() {
      const id = root.querySelector("#mode").value;
      return (resultCache?.tables || []).find((table) => table.id === id);
    }

    let resultCache = null;

    /* ---------------- 小结面板：选了什么遗器 + 配速结论 ----------------
       面板里的控件是**静态 HTML**（见 mount 里的 #pick-summary），
       这里只更新算出来的文字，避免每次重算都把控件重建一遍（那样下拉会失灵）。 */

    function renderPickSummary(result, verdict) {
      const applied = result.relicSets || [];
      const contributions = applied
        .map(
          (set) =>
            `${set.setName}（${set.effects
              .map(
                (effect) =>
                  `${effect.slot} ${
                    effect.kind === "advance"
                      ? `拉条+${fix(effect.value, 0)}%`
                      : `速度+${fix(effect.value, 0)}%`
                  }`,
              )
              .join("、")}）`,
        )
        .join("；");
      const extras = [];
      if (state.relic.speedBoots) extras.push("速度鞋 +25");
      if (state.relic.substatSpeed) extras.push(`副词条 +${fix(state.relic.substatSpeed, 0)}`);

      const set = (id, text) => {
        const element = root.querySelector(id);
        if (element) element.textContent = text;
      };
      // 有「开大才触发」的效果但开大次数是 0 时，必须显眼提示 ——
      // 否则用户选了套装却看到速度没变，会以为功能坏了（踩过）。
      const perUltBlocked = (result.effects?.conditional || []).filter(
        (item) => item.note && item.note.includes("需要开大"),
      );
      const hint = perUltBlocked.length
        ? `<div class="hint" style="color:var(--warn)">⚠ ${perUltBlocked
            .map((item) => item.setName || item.name || "该效果")
            .join("、")} 需要<span style="color:var(--text)">开大</span>才生效：
            请把上面的「开大次数」设成 1 或更大（目前是 0，所以没计入）。</div>`
        : "";
      set(
        "#ps-contrib",
        (contributions || (extras.length ? `${extras.join("，")}（套装无速度相关效果）` : "无速度相关效果")) +
          (hint ? " " + hint : ""),
      );
      set(
        "#ps-target",
        `（${verdict.customAV > 0 ? `${fix(verdict.customAV, 0)} AV 节点` : `${verdict.t}T`} · ${
          verdict.actions
        } 动）`,
      );
      set("#ps-need", fix(verdict.requiredSpeed, 2));
      set("#ps-current", fix(verdict.currentSpeed, 2));
      set(
        "#ps-gap-label",
        verdict.gap > 0 ? "还差" : "富余",
      );
      const gap = root.querySelector("#ps-gap");
      if (gap) {
        gap.textContent = fix(Math.abs(verdict.gap), 2);
        gap.className = verdict.gap > 0 ? "ps-bad" : "ps-good";
      }
      set("#ps-actions", `${verdict.achievableActions} 动`);

      // 行动时间线（后端真的按行动顺序模拟出来的）：让"加速什么时候生效"看得见
      const sim = result.simulation;
      const timelineRow = root.querySelector("#ps-timeline-row");
      const timelineBox = root.querySelector("#ps-timeline");
      if (sim && (sim.timeline || []).length && timelineBox && timelineRow) {
        timelineRow.style.display = "";
        timelineBox.innerHTML =
          sim.timeline
            .map((step) => {
              const active = (step.active || []).length
                ? `<span class="muted small">（${esc(step.active.join("、"))}）</span>`
                : "";
              return `第 ${step.action} 动 <span class="num">${fix(step.speed, 1)}</span> 速 @ ${fix(
                step.av,
                0,
              )} AV ${active}`;
            })
            .join("<br/>") +
          ((sim.notes || []).length
            ? `<div class="hint">${sim.notes.map((note) => esc(note)).join("<br/>")}</div>`
            : "");
      } else if (timelineRow) {
        timelineRow.style.display = "none";
      }
    }

    function renderTables(result) {
      resultCache = result;
      const activeMode = root.querySelector("#mode").value || result.tables[0]?.id;
      const table = result.tables.find((item) => item.id === activeMode) || result.tables[0];
      if (!table) {
        root.querySelector("#r-tables").innerHTML = "";
        return;
      }
      const current = result.speed.final;
      const firstAV = Number(table.firstCycleAV ?? 150);
      const stepAV = Number(table.cycleAV ?? 100);
      const starLine = (table.stars || []).length
        ? `<p class="hint">星级线：${table.stars
            .map((star) => `${esc(star.label)} = ${star.cycles} 轮（${star.totalAV} AV）`)
            .join("　")}</p>`
        : "";
      root.querySelector("#r-tables").innerHTML = `
        <p class="hint">${esc(table.note || "")}　绿色 = 当前速度可达；单元格里是需要的速度。</p>
        ${starLine}
        <div style="overflow-x:auto">
          <table class="data">
            <thead><tr><th>动数 \\ T</th>${table.tValues
              .map(
                (t) =>
                  `<th class="num">${t}T<span class="muted small">（${firstAV + t * stepAV} AV）</span></th>`,
              )
              .join("")}</tr></thead>
            <tbody>${table.rows
              .map(
                (row) =>
                  `<tr><td>${row.actions} 动</td>${row.cells
                    .map(
                      (cell) =>
                        `<td class="num ${cell.reachable ? "reachable" : "unreachable"}">${fix(cell.speed, 1)}</td>`,
                    )
                    .join("")}</tr>`,
              )
              .join("")}</tbody>
          </table>
        </div>`;
    }

    function renderTargetOptions(result) {
      // 面板里和下面卡片里各有一份「模式 / T 数」下拉，两份都要刷成一样
      const modeSelects = ["#mode", "#mode-panel"]
        .map((selector) => root.querySelector(selector))
        .filter(Boolean);
      for (const select of modeSelects) {
        if (!select.options.length) {
          select.innerHTML = result.tables
            .map((table) => `<option value="${esc(table.id)}">${esc(table.name)}</option>`)
            .join("");
        }
      }
      const modeSelect = modeSelects[0];
      if (!modeSelect) return;
      // 以 state.target.mode 为准：面板里那个下拉改了也要算数（两个下拉只是同一份状态的视图）
      const known = new Set((result.tables || []).map((table) => table.id));
      const activeMode =
        state.target.mode && known.has(state.target.mode)
          ? state.target.mode
          : modeSelect.value || result.tables[0]?.id;
      // 目标模式要跟着一起发给后端：异相仲裁的首轮行动值是 400，不是 150
      state.target.mode = activeMode;
      for (const select of modeSelects) {
        if (select.value !== activeMode) select.value = activeMode;
      }

      const table = result.tables.find((item) => item.id === activeMode) || result.tables[0];
      const firstAV = Number(table?.firstCycleAV ?? 150);
      const stepAV = Number(table?.cycleAV ?? 100);
      const wanted = String(state.target.t);
      const tSelects = ["#targetT", "#targetT-panel"]
        .map((selector) => root.querySelector(selector))
        .filter(Boolean);
      for (const select of tSelects) {
        select.innerHTML = (table?.tValues || [0])
          .map(
            (t) =>
              `<option value="${t}" ${String(t) === wanted ? "selected" : ""}>` +
              `${t}T（${firstAV + t * stepAV} AV）</option>`,
          )
          .join("");
      }
      const tSelect = tSelects[0];
      if (tSelect && ![...tSelect.options].some((option) => option.selected)) {
        const fallback = String((state.target.t = table?.tValues?.[0] ?? 0));
        for (const select of tSelects) select.value = fallback;
      } else {
        for (const select of tSelects) select.value = wanted;
      }
    }

    /* ---------------- 绑定 ---------------- */

    /* ---------------- 我的配装 ---------------- */

    let presets = {};

    function currentConfig() {
      return {
        lightconeId: state.lightconeId,
        superimpose: state.superimpose,
        eidolon: state.eidolon,
        enabledEffects: state.enabled,
        relic: state.relic,
        advance: state.advance,
        target: state.target,
      };
    }

    function refreshPresets() {
      const select = root.querySelector("#preset");
      const saved = presets[String(state.characterId)];
      select.innerHTML = saved
        ? `<option value="">（已存：${esc(saved.savedAt)}）</option>`
        : `<option value="">（这个角色还没存过）</option>`;
      root.querySelector("#preset-note").textContent = saved
        ? `已存配装：光锥 ${esc(
            cones.find((cone) => String(cone.id) === String(saved.config?.lightconeId))?.name || "无",
          )}　叠影 ${saved.config?.superimpose ?? "-"}　星魂 ${saved.config?.eidolon ?? "-"}`
        : "把当前这套（光锥/叠影/星魂/遗器/拉条）存下来，下次一键套用。";
    }

    async function loadPresets() {
      try {
        presets = (await ctx.call("presets")).presets || {};
      } catch {
        presets = {};
      }
      refreshPresets();
    }

    root.querySelector("#save-preset").addEventListener("click", async () => {
      const button = root.querySelector("#save-preset");
      button.disabled = true;
      try {
        const result = await ctx.call("save_preset", {
          characterId: state.characterId,
          config: currentConfig(),
        });
        await loadPresets();
        root.querySelector("#preset-note").textContent = `已保存（共 ${result.count} 个角色的配装）。`;
      } catch (err) {
        root.querySelector("#preset-note").innerHTML = `<span class="error-text">${esc(err.message)}</span>`;
      } finally {
        button.disabled = false;
      }
    });

    root.querySelector("#delete-preset").addEventListener("click", async () => {
      try {
        await ctx.call("delete_preset", { characterId: state.characterId });
        await loadPresets();
      } catch (err) {
        root.querySelector("#preset-note").innerHTML = `<span class="error-text">${esc(err.message)}</span>`;
      }
    });

    root.querySelector("#preset").addEventListener("change", () => {
      const saved = presets[String(state.characterId)];
      if (!saved?.config) return;
      const config = saved.config;
      state.lightconeId = config.lightconeId || "";
      state.superimpose = config.superimpose ?? 5;
      state.eidolon = config.eidolon ?? 0;
      state.enabled = config.enabledEffects ?? null;
      state.relic = { ...state.relic, ...(config.relic || {}) };
      state.advance = { ...state.advance, ...(config.advance || {}) };
      state.target = { ...state.target, ...(config.target || {}) };
      // 同步到控件（上下两份都要刷）
      lightconePicker.setValue(state.lightconeId || "");
      root.querySelector("#superimpose").value = String(state.superimpose);
      root.querySelector("#eidolon").value = String(state.eidolon);
      root.querySelector("#fourUlts").value = state.relic.fourPieceUlts ?? 0;
      root.querySelector("#substat").value = state.relic.substatSpeed ?? 0;
      root.querySelector("#customPct").value = state.relic.customPct ?? 0;
      root.querySelector("#customFlat").value = state.relic.customFlat ?? 0;
      root.querySelector("#coneUlts").value = state.advance.coneUlts ?? 0;
      root.querySelector("#advCustom").value = state.advance.custom ?? 0;
      root.querySelector("#customAV").value = state.target.customAV ?? 0;
      syncRelicControls();
      effectSignature = "";
      run();
    });

    root.querySelector("#superimpose").addEventListener("change", (event) => {
      state.superimpose = Number(event.target.value);
      state.enabled = null;
      schedule();
    });
    root.querySelector("#eidolon").addEventListener("change", (event) => {
      state.eidolon = Number(event.target.value);
      state.enabled = null;
      schedule();
    });

    // 小结面板里的控件和下面卡片的控件共用同一份 state（bindPair 双向同步）
    bindPair("#customPct", "#customPct-panel", "input", (value) => {
      state.relic.customPct = Number(value || 0);
    });
    bindPair("#customFlat", "#customFlat-panel", "input", (value) => {
      state.relic.customFlat = Number(value || 0);
    });
    bindPair("#coneUlts", "#coneUlts-panel", "input", (value) => {
      state.advance.coneUlts = Number(value || 0);
    });
    bindPair("#advCustom", "#advCustom-panel", "input", (value) => {
      state.advance.custom = Number(value || 0);
    });
    root.querySelector("#firstUltAction-panel").addEventListener("input", (event) => {
      state.simulation.firstUltAction = Math.max(1, Number(event.target.value || 1));
      schedule();
    });

    /* ---------------- 自动推荐配装 ---------------- */

    root.querySelector("#rec-btn").addEventListener("click", runRecommend);

    async function runRecommend() {
      const box = root.querySelector("#r-recommend");
      box.innerHTML = `<div class="loading">穷举中…</div>`;
      try {
        const result = await ctx.call("recommend", {
          characterId: state.characterId,
          target: state.target,
          relic: { speedBoots: state.relic.speedBoots },
          superimpose: Number(root.querySelector("#recS").value || 5),
          coneUlts: Number(root.querySelector("#recConeUlts").value || 0),
          fourPieceUlts: Number(root.querySelector("#recFourUlts").value || 0),
          // 「轴底开大」也要作用于推荐，否则推荐出来的方案套用后会变
          excludeLastUlt: !!state.advance.excludeLastUlt,
          maxResults: 10,
        });
        const assumptions = result.assumptions;
        box.innerHTML = `
          <p class="hint">穷举了 ${result.evaluated} 套组合 · 假设：速度鞋${assumptions.speedBoots ? "开" : "关"}、
            叠影 ${assumptions.superimpose}、光锥开大 ${assumptions.coneUlts} 次、风套开大 ${assumptions.fourPieceUlts} 次${
              assumptions.excludeLastUlt ? "（已按「轴底开大」扣掉最后一次）" : ""
            } ·
            目标 ${result.target.totalAV} AV 内 ${result.target.actions} 动</p>
          <div style="overflow-x:auto">
            <table class="data">
              <thead><tr><th>光锥</th><th>遗器 4 件套</th><th>位面饰品</th><th class="num">速度</th><th class="num">拉条</th><th>结果</th><th></th></tr></thead>
              <tbody>${result.results
                .map(
                  (item, index) => `<tr>
                    <td>${esc(item.coneName)}</td>
                    <td>${esc(item.fourPieceName)}</td>
                    <td>${item.ornamentNames.filter(Boolean).map(esc).join("、") || "—"}</td>
                    <td class="num">${fix(item.speed, 1)}</td>
                    <td class="num">${fix(item.advance, 0)}%</td>
                    <td>${item.ok ? "✅ 够" : `还差 ${fix(item.neededSubstatSpeed, 1)} 副词条`}${
                      item.notes.length ? `<div class="muted small">${esc(item.notes.join("；"))}</div>` : ""
                    }</td>
                    <td><button class="ghost small" data-apply="${index}">套用</button></td>
                  </tr>`,
                )
                .join("")}</tbody>
            </table>
          </div>`;
        box.querySelectorAll("[data-apply]").forEach((button) => {
          button.addEventListener("click", () => {
            const item = result.results[Number(button.dataset.apply)];
            state.lightconeId = item.coneId || "";
            state.relic.fourPieceId = item.fourPieceId || "";
            state.relic.ornamentIds = [...item.ornamentIds];
            state.relic.speedBoots = true;
            lightconePicker.setValue(state.lightconeId);
            root.querySelector("#speedBoots").checked = true;
            // 推荐是按它自己的假设算的（叠影、风套/光锥开大次数），套用时必须一起同步，
            // 否则主界面还是原值，算出来的速度和推荐里写的不一样。
            state.superimpose = Number(assumptions.superimpose || state.superimpose);
            root.querySelector("#superimpose").value = String(state.superimpose);
            state.relic.fourPieceUlts = Number(assumptions.fourPieceUlts || 0);
            state.advance.coneUlts = Number(assumptions.coneUlts || 0);
            root.querySelector("#coneUlts").value = String(state.advance.coneUlts);
            syncRelicControls();
            run();
          });
        });
      } catch (err) {
        box.innerHTML = `<p class="error-text">${esc(err.message)}</p>`;
      }
    }

    // 模式 / T 数 / 动数 / 自定义行动值：面板里与下面卡片里各有一份，两边都要能改
    function onModeChanged(value) {
      const mode = value || root.querySelector("#mode")?.value || state.target.mode;
      state.target.mode = mode;
      state.target.t = 0;
      state.target.customAV = 0;
      // 面板与下面卡片里的下拉是同一份状态的两个视图，改哪个都同步另一个
      for (const id of ["#mode", "#mode-panel"]) {
        const element = root.querySelector(id);
        if (element && element.value !== mode) element.value = mode;
      }
      for (const id of ["#customAV", "#customAV-panel"]) {
        const element = root.querySelector(id);
        if (element) element.value = 0;
      }
      run();
    }
    function onTChanged(value) {
      state.target.t = Number(value);
      // 两个 T 下拉同步（面板里的改动不能让下面那个把它拽回去）
      for (const id of ["#targetT", "#targetT-panel"]) {
        const element = root.querySelector(id);
        if (element && element.value !== String(value)) element.value = String(value);
      }
      state.target.customAV = 0;
      for (const id of ["#customAV", "#customAV-panel"]) {
        const element = root.querySelector(id);
        if (element) element.value = 0;
      }
      schedule();
    }
    function onActionsChanged(value) {
      state.target.actions = Math.max(1, Number(value || 1));
      schedule();
    }
    function onCustomAVChanged(value) {
      state.target.customAV = Math.max(0, Number(value || 0));
      schedule();
    }

    root.querySelector("#mode").addEventListener("change", (event) =>
      onModeChanged(event.target.value),
    );
    root.querySelector("#mode-panel").addEventListener("change", (event) =>
      onModeChanged(event.target.value),
    );
    root.querySelector("#targetT").addEventListener("change", (event) => onTChanged(event.target.value));
    root.querySelector("#targetT-panel").addEventListener("change", (event) =>
      onTChanged(event.target.value),
    );
    root.querySelector("#customAV").addEventListener("input", (event) =>
      onCustomAVChanged(event.target.value),
    );
    root.querySelector("#customAV-panel").addEventListener("input", (event) =>
      onCustomAVChanged(event.target.value),
    );
    root.querySelector("#targetActions").addEventListener("input", (event) =>
      onActionsChanged(event.target.value),
    );
    root.querySelector("#targetActions-panel").addEventListener("input", (event) =>
      onActionsChanged(event.target.value),
    );
    root.querySelectorAll("[data-av]").forEach((button) => {
      button.addEventListener("click", () => {
        state.target.customAV = Number(button.dataset.av);
        for (const id of ["#customAV", "#customAV-panel"]) {
          const element = root.querySelector(id);
          if (element) element.value = state.target.customAV;
        }
        schedule();
      });
    });

    /* ---------------- 启动 ---------------- */

    // 套装下拉：把「选了能拿到什么」直接写在下拉项里
    function describeSet(set) {
      if (!(set.effects || []).length) {
        // 没有速度效果的套装照样能选，只是不计入配速。
        // 说明文字**必须短**：下拉行里名字优先显示，长文案会把名字挤没（踩过）。
        return "无速度效果";
      }
      return (set.effects || [])
        .map((effect) => {
          const prefix = effect.slot === "4件套" ? "4件" : "2件";
          if (effect.kind === "advance") return `${prefix} 拉条+${fix(effect.value, 0)}%`;
          if (effect.kind === "pct") return `${prefix} 速度+${fix(effect.value, 0)}%`;
          return `${prefix} 速度+${fix(effect.value, 0)}`;
        })
        .join("，");
    }

    const setItems = setOptions(catalog.fourPieceSets);
    const ornamentItems = setOptions(catalog.ornamentSets);
    fourPiecePicker.setItems(setItems, state.relic.fourPieceId);
    fourPieceTopPicker.setItems(setItems, state.relic.fourPieceId);
    ornamentPicker.setItems(ornamentItems, "");
    ornamentTopPicker.setItems(ornamentItems, "");
    root.querySelector("#relic-note").textContent =
      `套装效果来自官方文案，选中即自动计入：4 件套可选 ${(catalog.fourPieceSets || []).length} 个、` +
      `位面饰品可选 ${(catalog.ornamentSets || []).length} 个。带条件的效果不会自动算，会单独列出来。`;

    const sources = catalog.sources || {};
    if (sources.generatedAt) {
      root.querySelector("#char-info").textContent = `数据抓取于 ${sources.generatedAt}（米游社官方图鉴 + StarRailRes 数值）`;
    }

    loadCharacterPicker();
    updateSplash();
    await loadCones();
    await loadPresets();
    await run();
  },

  unmount() {},
};
