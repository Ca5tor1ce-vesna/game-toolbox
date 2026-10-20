/* 配速查询（0.17.0 新界面）：左边按步骤配装，右边固定显示结论。
 *
 * 数学全在 api.py（单文件网页版换成 web_api.js）；这里只负责选择与呈现。
 * 和旧界面的约定保持一致：
 *   1. 光锥只列同命途的（自定义角色不限命途）；
 *   2. 自动抽出来的速度效果默认只勾「看起来无条件」的，其余留给你判断；
 *   3. 同样的选择发出的 plan 请求和旧界面完全一样（tests/ui_equivalence 会对比）。
 * 每个状态字段只有一个控件（旧界面顶部快捷区和下面卡片各有一份，容易不同步）。
 */

export default {
  title: "配速查询",

  async mount(root, ctx) {
    const esc = (text) => ctx.ui.escapeHtml(String(text ?? ""));
    const fix = (value, digits = 2) =>
      Number.isFinite(Number(value)) ? Number(value).toFixed(digits) : "-";
    const CUSTOM_ID = "__custom__";
    // 一条速度副词条平均约 2.3 速（2.0 / 2.3 / 2.6 三档的中位），只用来估算「还要几条」
    const SUBSTAT_ROLL = 2.3;

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
      custom: { name: "自定义角色", baseSpeed: 100, traceSpeed: 0 },
      lightconeId: null,
      superimpose: 1,
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
      // 模拟参数：第一次开大发生在自己第几次行动之后（0 = 进战即开大）
      simulation: { firstUltAction: 1 },
      target: { t: 0, actions: 2, customAV: 0, mode: catalog.modes?.[0]?.id || "moc" },
    };

    const charById = new Map(catalog.characters.map((item) => [String(item.id), item]));
    const isCustom = () => String(state.characterId) === CUSTOM_ID;
    let cones = [];
    let lastResult = null;

    const STEP_KEY = "gt-speed-plan-steps";
    let collapsedSteps = new Set();
    try {
      const saved = JSON.parse(localStorage.getItem(STEP_KEY) || "[]");
      if (Array.isArray(saved)) collapsedSteps = new Set(saved);
    } catch {
      /* 读不到就全部展开 */
    }

    const step = (id, no, textKey, title, body) => `
      <section class="sp-step${collapsedSteps.has(id) ? " collapsed" : ""}" data-step="${id}">
        <button type="button" class="sp-step-head" aria-expanded="${collapsedSteps.has(id) ? "false" : "true"}">
          <span class="sp-step-no">${no}</span>
          <span class="sp-step-title" data-text="${textKey}">${title}</span>
          <span class="sp-step-sum" id="sum-${id}"></span>
          <span class="sp-caret">▾</span>
        </button>
        <div class="sp-step-body">${body}</div>
      </section>`;

    root.innerHTML = `
    <div class="sp">
      <div class="sp-left">
        <h2 class="sp-col-title" data-text="speed-plan.card.pick">🎯 选角色与配装</h2>
        ${step(
          "char",
          "①",
          "speed-plan.step.character",
          "角色",
          `
          <div class="sp-char-top">
            <img id="splash" class="sp-splash" alt="角色立绘" />
            <div class="sp-char-meta">
              <div id="splash-meta" class="sp-splash-meta">选个角色</div>
              <div class="row" style="margin-top:8px">
                <div class="field"><label for="eidolon">星魂</label>
                  <select id="eidolon" class="input narrow">
                    <option value="0" selected>0 魂</option><option value="1">1 魂</option><option value="2">2 魂</option>
                    <option value="3">3 魂</option><option value="4">4 魂</option><option value="5">5 魂</option><option value="6">6 魂</option>
                  </select>
                </div>
              </div>
            </div>
          </div>
          <input id="char-search" class="input sp-search" type="search" placeholder="搜索角色 / 命途 / 属性…（越新推出的越靠前）" autocomplete="off" />
          <div id="char-grid" class="sp-char-grid" role="listbox" aria-label="角色"></div>
          <div id="custom-fields" class="sp-custom hidden">
            <div class="row">
              <div class="field"><label for="customName">名字</label><input id="customName" class="input" maxlength="20" value="自定义角色" /></div>
              <div class="field"><label for="customBase">基础速度（1–1000）</label><input id="customBase" class="input narrow" type="number" min="1" max="1000" step="1" value="100" /></div>
              <div class="field"><label for="customTrace">行迹速度（0–200）</label><input id="customTrace" class="input narrow" type="number" min="0" max="200" step="1" value="0" /></div>
            </div>
            <p class="hint" data-text="speed-plan.custom.hint">自定义角色没有自带的速度效果；光锥不限命途。</p>
          </div>
          <p class="hint" id="char-info"></p>`,
        )}
        ${step(
          "cone",
          "②",
          "speed-plan.step.lightcone",
          "光锥",
          `
          <div class="row">
            <div class="field sp-grow"><label>光锥（只显示同命途）</label>
              <button id="lightcone-picker" type="button" class="picker-button"></button>
            </div>
            <div class="field"><label for="superimpose">叠影</label>
              <select id="superimpose" class="input narrow">
                <option selected>1</option><option>2</option><option>3</option><option>4</option><option>5</option>
              </select>
            </div>
          </div>
          <div id="r-cone-advance"></div>`,
        )}
        ${step(
          "relic",
          "③",
          "speed-plan.step.relic",
          "遗器",
          `
          <div class="row">
            <div class="field sp-grow"><label>遗器 4 件套</label>
              <button id="fourPiece-picker" type="button" class="picker-button"></button>
            </div>
            <div class="field sp-grow"><label>位面饰品</label>
              <button id="ornamentA-picker" type="button" class="picker-button"></button>
            </div>
          </div>
          <div class="row" style="margin-top:8px">
            <label class="field check"><input id="speedBoots" type="checkbox" checked /> 速度鞋（主词条 +25）</label>
            <label class="field check"><input id="ultTargetsAlly" type="checkbox" /> 开大目标是队友（信使 4 件套才生效）</label>
          </div>
          <div class="row" style="margin-top:8px">
            <div class="field"><label for="fourUlts">开大次数（风套这类按次触发）</label><input id="fourUlts" class="input narrow" type="number" value="0" min="0" step="1" /></div>
            <div class="field"><label for="coneUlts">光锥开大次数</label><input id="coneUlts" class="input narrow" type="number" value="0" min="0" step="1" /></div>
          </div>
          <div id="relic-warn"></div>
          <div id="r-relics"></div>
          <p class="hint" id="relic-note"></p>`,
        )}
        ${step(
          "bonus",
          "④",
          "speed-plan.step.bonus",
          "加成与拉条",
          `
          <div class="row">
            <div class="field"><label for="substat">副词条速度合计</label><input id="substat" class="input narrow" type="number" value="0" step="1" /></div>
            <div class="field"><label for="customPct">其它速度 %</label><input id="customPct" class="input narrow" type="number" value="0" step="1" /></div>
            <div class="field"><label for="customFlat">其它固定速度</label><input id="customFlat" class="input narrow" type="number" value="0" step="1" /></div>
            <div class="field"><label for="advCustom">其它拉条 %</label><input id="advCustom" class="input narrow" type="number" value="0" step="5" /></div>
          </div>
          <h3>检测到的速度效果（勾选后计入）</h3>
          <div id="r-effects"></div>
          <div id="r-advance-effects"></div>`,
        )}
        ${step(
          "target",
          "⑤",
          "speed-plan.step.target",
          "目标",
          `
          <div class="row">
            <div class="field"><label for="mode">目标模式</label><select id="mode" class="input wide"></select></div>
            <div class="field"><label for="targetT">目标 T 数</label><select id="targetT" class="input"></select></div>
            <div class="field"><label for="targetActions">目标动数</label><input id="targetActions" class="input narrow" type="number" value="2" min="1" max="8" step="1" /></div>
          </div>
          <div class="row" style="margin-top:8px">
            <div class="field"><label for="customAV">或直接指定行动值（0 = 按 T 数）</label>
              <div class="row tight">
                <input id="customAV" class="input narrow" type="number" value="0" min="0" step="10" />
                <button type="button" class="ghost small" data-av="150">150</button>
                <button type="button" class="ghost small" data-av="250">250</button>
                <button type="button" class="ghost small" data-av="300">300</button>
              </div>
            </div>
            <div class="field"><label for="firstUltAction">首次开大在第几次行动后（0 = 进战即开大）</label>
              <input id="firstUltAction" class="input narrow" type="number" value="1" min="0" step="1" />
            </div>
          </div>
          <div class="row" style="margin-top:8px">
            <label class="field check"><input id="excludeLastUlt" type="checkbox" /> 轴底开大（最后一次开大的拉条不计入）</label>
          </div>
          <p class="hint">首次开大只影响「开大才提速」的加速，不影响拉条。</p>`,
        )}
      </div>

      <aside class="sp-right">
        <div class="sp-presetbar">
          <span class="sp-presetbar-label" data-text="speed-plan.preset.title">我的配装</span>
          <select id="preset" class="input" aria-label="已存配装"></select>
          <button type="button" id="apply-preset" class="ghost small" data-text="speed-plan.preset.apply">套用</button>
          <button type="button" id="save-preset" class="btn secondary small-btn" data-text="speed-plan.preset.save">保存</button>
          <button type="button" id="delete-preset" class="ghost small" data-text="speed-plan.preset.delete">删除</button>
        </div>
        <p class="hint sp-preset-note" id="preset-note"></p>
        <details class="sp-sim-save">
          <summary>队伍模拟补充参数（随角色配装保存）</summary>
          <div class="row">
            <label class="field">额外充能效率 (%)<input id="preset-err" class="input narrow" type="number" min="0" step="0.1" value="0"></label>
            <label class="field">开局资源（留空用默认）<input id="preset-energy" class="input narrow" type="number" min="0" step="any"></label>
            <label class="field">出招<select id="preset-rotation" class="input"><option value="auto">智能出招</option><option value="skill">全程战技</option><option value="basic">全程普攻</option></select></label>
          </div>
          <p class="hint">充能填写遗器和光锥特效以外的加成；愿力、隐藏分角色不使用充能效率。开局资源单位为角色的能量、愿力或隐藏分。</p>
        </details>
        <a class="ghost small" id="open-team-simulator" href="#/honkai-star-rail/aha-speed">前往队伍与行动模拟 →</a>

        <div class="sp-hero" id="hero">
          <div class="sp-hero-nums">
            <div class="sp-hero-num">
              <div class="k" data-text="speed-plan.hero.current">当前速度</div>
              <div class="v" id="hero-current">—</div>
            </div>
            <div class="sp-hero-vs">→</div>
            <div class="sp-hero-num">
              <div class="k"><span data-text="speed-plan.hero.required">需要速度</span> <span id="hero-target" class="muted"></span></div>
              <div class="v accent" id="hero-need">—</div>
            </div>
          </div>
          <div class="sp-hero-gap" id="hero-gap">—</div>
          <div class="sp-hero-sub" id="hero-sub"></div>
          <div id="hero-error"></div>
        </div>

        <div class="tabs sp-tabs" role="tablist">
          <button type="button" class="tab active" data-tab="detail" data-text="speed-plan.tab.detail">计算明细</button>
          <button type="button" class="tab" data-tab="timeline" data-text="speed-plan.tab.timeline">行动时间轴</button>
          <button type="button" class="tab" data-tab="tables" data-text="speed-plan.tab.tables">各模式需求</button>
          <button type="button" class="tab" data-tab="recommend" data-text="speed-plan.tab.recommend">自动推荐</button>
        </div>

        <div class="sp-panel" data-panel="detail">
          <h3 data-text="speed-plan.card.speed">⚡ 实际速度</h3>
          <div class="stat-grid">
            <div class="stat accent"><div class="k">实际速度</div><div class="v" id="r-speed">-</div></div>
            <div class="stat"><div class="k">基础速度</div><div class="v" id="r-base">-</div></div>
            <div class="stat"><div class="k">速度 % / 固定</div><div class="v small" id="r-split">-</div></div>
            <div class="stat"><div class="k">单动行动值</div><div class="v small" id="r-av">-</div></div>
          </div>
          <p class="formula" id="r-formula"></p>
          <div id="r-breakdown"></div>
          <h3 data-text="speed-plan.card.advance">🌀 拉条来源</h3>
          <p class="hint" id="r-advance"></p>
          <div id="r-verdict"></div>
          <div id="r-suggestions"></div>
        </div>

        <div class="sp-panel hidden" data-panel="timeline">
          <div id="r-timeline"><p class="hint">算完之后这里显示每一动的速度和行动值。</p></div>
        </div>

        <div class="sp-panel hidden" data-panel="tables">
          <h3 data-text="speed-plan.card.targets">📋 需求速度：各模式 × T 数 × 动数</h3>
          <div class="sp-mode-switch" id="table-modes"></div>
          <div id="r-tables"></div>
        </div>

        <div class="sp-panel hidden" data-panel="recommend">
          <h3 data-text="speed-plan.card.recommend">🧠 自动推荐配装</h3>
          <p class="hint">
            在这个角色能用的光锥与遗器里穷举一遍，找出「达成当前目标最省」的几套。
            这是自动算出来的最优解，<b>不是社区主流配装表</b>（那个数据源拿不到）。
          </p>
          <div class="row">
            <div class="field"><label for="recConeUlts">光锥开大次数</label><input id="recConeUlts" class="input tiny" type="number" value="1" min="0" step="1" /></div>
            <div class="field"><label for="recFourUlts">风套开大次数</label><input id="recFourUlts" class="input tiny" type="number" value="1" min="0" step="1" /></div>
            <div class="field"><label for="recS">光锥叠影</label>
              <select id="recS" class="input tiny"><option selected>1</option><option>2</option><option>3</option><option>4</option><option>5</option></select>
            </div>
            <button type="button" id="rec-btn" class="btn">算一下哪套最省</button>
          </div>
          <div id="r-recommend"></div>
        </div>
      </aside>
    </div>`;

    const $ = (selector) => root.querySelector(selector);
    if (window.GT_STANDALONE) {
      $("#open-team-simulator").onclick = event => {
        event.preventDefault();
        document.querySelector('[data-view="view-aha"]')?.click();
      };
    }

    /* ---------------- 步骤卡片折叠 ---------------- */

    root.querySelectorAll(".sp-step-head").forEach((head) => {
      head.addEventListener("click", () => {
        const box = head.closest(".sp-step");
        const id = box.dataset.step;
        const collapsed = box.classList.toggle("collapsed");
        head.setAttribute("aria-expanded", collapsed ? "false" : "true");
        if (collapsed) collapsedSteps.add(id);
        else collapsedSteps.delete(id);
        try {
          localStorage.setItem(STEP_KEY, JSON.stringify([...collapsedSteps]));
        } catch {
          /* 存不了就算了 */
        }
      });
    });

    /* ---------------- 右栏页签 ---------------- */

    root.querySelectorAll(".sp-tabs .tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        root.querySelectorAll(".sp-tabs .tab").forEach((t) => t.classList.toggle("active", t === tab));
        root.querySelectorAll(".sp-panel").forEach((panel) => {
          panel.classList.toggle("hidden", panel.dataset.panel !== tab.dataset.tab);
        });
      });
    });

    /* ---------------- 官方图：按需下载 + 本地缓存 ---------------- */

    // 工具箱里图片走本地缓存接口（/api/asset 会下载一次并缓存到 userdata）；
    // 独立网页版（window.GT_STANDALONE）没有服务端，直接指向官方 CDN。
    const assetUrl = (remote) => {
      if (!remote) return "";
      if (remote.startsWith("/")) return (window.GT_ASSETS || {})[remote] || remote;
      return window.GT_STANDALONE ? remote : `/api/asset?url=${encodeURIComponent(remote)}`;
    };
    const image = (remote) =>
      remote ? `<img src="${esc(assetUrl(remote))}" onerror="this.style.visibility='hidden'" alt="" loading="lazy" />` : `<span class="sp-noimg"></span>`;

    function currentCharacter() {
      if (isCustom()) {
        return {
          id: CUSTOM_ID,
          name: state.custom.name || "自定义角色",
          pathName: "自定义",
          baseSpeed: state.custom.baseSpeed,
          traceSpeed: state.custom.traceSpeed,
          effectiveBaseSpeed: Number(state.custom.baseSpeed) + Number(state.custom.traceSpeed || 0),
        };
      }
      return charById.get(String(state.characterId)) || {};
    }

    function updateSplash() {
      const character = currentCharacter();
      const img = $("#splash");
      const source = character.splash || "";
      const fallback = character.splashFallback || "";
      if (source || fallback) {
        img.onerror = () => {
          if (fallback && img.src !== assetUrl(fallback)) img.src = assetUrl(fallback);
          else img.style.visibility = "hidden";
        };
        img.src = assetUrl(source || fallback);
        img.style.visibility = "visible";
      } else {
        img.onerror = null;
        img.removeAttribute("src");
        img.style.visibility = "hidden";
      }
      const trace = Number(character.traceSpeed || 0);
      const speed = character.effectiveBaseSpeed ?? character.baseSpeed;
      $("#splash-meta").innerHTML =
        `<b>${esc(character.name || "选个角色")}</b>` +
        `<div class="muted small">${esc(character.pathName || "")}${
          character.elementName ? ` · ${esc(character.elementName)}` : ""
        }${character.rarity ? ` · ${character.rarity}★` : ""}</div>` +
        `<div class="muted small">初始速度 ${fix(speed, 0)}${
          trace ? `（基础 ${fix(character.baseSpeed, 0)} + 行迹 ${fix(trace, 0)}）` : ""
        }</div>`;
      $("#custom-fields").classList.toggle("hidden", !isCustom());
    }

    /* ---------------- 角色头像网格 ---------------- */

    function renderCharGrid() {
      const needle = $("#char-search").value.trim().toLowerCase();
      const list = catalog.characters.filter(
        (item) =>
          !needle ||
          `${item.name} ${item.pathName || ""} ${item.elementName || ""}`.toLowerCase().includes(needle),
      );
      const tile = (id, icon, name, meta) =>
        `<button type="button" class="sp-char${String(state.characterId) === String(id) ? " active" : ""}" data-char="${esc(
          id,
        )}" title="${esc(meta)}" role="option" aria-selected="${String(state.characterId) === String(id)}">` +
        icon +
        `<span class="sp-char-name">${esc(name)}</span></button>`;
      const showCustom = !needle || "自定义角色 custom".includes(needle);
      $("#char-grid").innerHTML =
        (showCustom
          ? tile(CUSTOM_ID, `<span class="sp-custom-icon">＋</span>`, "自定义角色", "空白角色：自己填基础速度和行迹速度")
          : "") +
        list
          .map((item) => {
            const trace = Number(item.traceSpeed || 0);
            const speed = item.effectiveBaseSpeed ?? item.baseSpeed;
            return tile(
              item.id,
              image(item.icon),
              item.name,
              `${item.pathName} · ${item.rarity}★ · ${fix(speed, 0)} 速${trace ? `（含行迹 +${fix(trace, 0)}）` : ""}`,
            );
          })
          .join("") +
        (!list.length && !showCustom ? `<p class="hint">没有匹配的角色</p>` : "");
    }

    $("#char-search").addEventListener("input", renderCharGrid);
    $("#char-grid").addEventListener("click", async (event) => {
      const button = event.target.closest("[data-char]");
      if (!button) return;
      await pickCharacter(button.dataset.char);
    });

    async function pickCharacter(id) {
      state.characterId = id;
      $("#preset-err").value = 0;
      $("#preset-energy").value = "";
      $("#preset-rotation").value = "auto";
      state.enabled = null;
      renderCharGrid();
      await loadCones();
      refreshPresets();
      updateSplash();
      run();
    }

    function onCustomInput() {
      state.custom.name = $("#customName").value;
      state.custom.baseSpeed = $("#customBase").value === "" ? NaN : Number($("#customBase").value);
      state.custom.traceSpeed = $("#customTrace").value === "" ? 0 : Number($("#customTrace").value);
      updateSplash();
      schedule();
    }
    ["#customName", "#customBase", "#customTrace"].forEach((id) => $(id).addEventListener("input", onCustomInput));

    /* ---------------- 带官方图的下拉（光锥 / 遗器） ---------------- */

    function createPicker({ buttonId, placeholder, searchPlaceholder, onPick }) {
      const button = $(buttonId);
      const popup = document.createElement("div");
      popup.className = "picker-popup hidden";
      popup.innerHTML =
        `<input class="input picker-search" placeholder="${esc(searchPlaceholder || "搜索…")}" />` +
        `<div class="picker-list"></div>`;
      root.appendChild(popup);
      const search = popup.querySelector(".picker-search");
      const list = popup.querySelector(".picker-list");
      let items = [];
      let current = "";

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
          ? items.filter((item) => `${item.name} ${item.meta || ""}`.toLowerCase().includes(needle))
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
            close();
            onPick(element.dataset.id);
          });
        });
      }

      function open() {
        const rect = button.getBoundingClientRect();
        const margin = 8;
        const width = Math.min(Math.max(rect.width, 320), Math.max(240, window.innerWidth - margin * 2));
        const left = Math.min(Math.max(margin, rect.left), Math.max(margin, window.innerWidth - width - margin));
        popup.style.left = `${left}px`;
        popup.style.width = `${width}px`;
        popup.style.top = `${margin}px`;
        popup.classList.remove("hidden");
        search.value = "";
        renderList();
        const height = popup.offsetHeight || 360;
        const spaceBelow = window.innerHeight - rect.bottom - margin;
        let top = rect.bottom + 4;
        if (height > spaceBelow && rect.top - margin > spaceBelow) top = rect.top - height - 4;
        top = Math.min(Math.max(margin, top), Math.max(margin, window.innerHeight - height - margin));
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
        name(value) {
          return items.find((entry) => String(entry.id) === String(value))?.name || "";
        },
      };
    }

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
        schedule();
      },
    });

    function describeSet(set) {
      if (!(set.effects || []).length) return "无速度效果";
      return (set.effects || [])
        .map((effect) => {
          const prefix = effect.slot === "4件套" ? "4件" : "2件";
          if (effect.kind === "advance") return `${prefix} 拉条+${fix(effect.value, 0)}%`;
          if (effect.kind === "pct") return `${prefix} 速度+${fix(effect.value, 0)}%`;
          return `${prefix} 速度+${fix(effect.value, 0)}`;
        })
        .join("，");
    }

    function setOptions(list) {
      return [
        { id: "", name: "（不用）", meta: "", icon: "" },
        ...list.map((set) => ({
          id: set.id,
          name: set.name,
          meta: describeSet(set),
          title: set.summary || set.name,
          icon: set.icon,
        })),
      ];
    }

    async function loadCones() {
      const character = currentCharacter();
      // 自定义角色没有命途：不传 path，列出全部光锥
      const data = await ctx.call("lightcones", isCustom() ? {} : { path: character?.path });
      cones = (data.lightcones || []).sort(
        (a, b) =>
          b.rarity - a.rarity || Number(b.speedRelated) - Number(a.speedRelated) || a.name.localeCompare(b.name, "zh"),
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

    /** 把 state 刷到控件上（预设/推荐套用后调用）。每个字段只有一个控件。 */
    function syncControls() {
      lightconePicker.setValue(state.lightconeId || "");
      fourPiecePicker.setValue(state.relic.fourPieceId || "");
      ornamentPicker.setValue(state.relic.ornamentIds?.[0] || "");
      $("#superimpose").value = String(state.superimpose);
      $("#eidolon").value = String(state.eidolon);
      $("#speedBoots").checked = !!state.relic.speedBoots;
      $("#ultTargetsAlly").checked = !!state.relic.ultTargetsAlly;
      $("#excludeLastUlt").checked = !!state.advance.excludeLastUlt;
      $("#fourUlts").value = state.relic.fourPieceUlts ?? 0;
      $("#substat").value = state.relic.substatSpeed ?? 0;
      $("#customPct").value = state.relic.customPct ?? 0;
      $("#customFlat").value = state.relic.customFlat ?? 0;
      $("#coneUlts").value = state.advance.coneUlts ?? 0;
      $("#advCustom").value = state.advance.custom ?? 0;
      $("#customAV").value = state.target.customAV ?? 0;
      $("#targetActions").value = state.target.actions ?? 2;
      $("#firstUltAction").value = state.simulation.firstUltAction ?? 1;
      if (isCustom()) {
        $("#customName").value = state.custom.name ?? "";
        $("#customBase").value = Number.isFinite(state.custom.baseSpeed) ? state.custom.baseSpeed : "";
        $("#customTrace").value = state.custom.traceSpeed ?? 0;
      }
    }

    /* ---------------- 重算（约 200ms 防抖） ---------------- */

    let timer = null;
    function schedule() {
      if (timer) clearTimeout(timer);
      timer = setTimeout(run, 200);
    }

    let effectSignature = "";
    let runSeq = 0;

    function buildPlanPayload() {
      const payload = {
        characterId: state.characterId,
        lightconeId: state.lightconeId || null,
        superimpose: state.superimpose,
        eidolon: state.eidolon,
        enabledEffects: state.enabled,
        relic: state.relic,
        advance: state.advance,
        target: state.target,
        simulation: state.simulation,
      };
      if (isCustom()) payload.customCharacter = { ...state.custom };
      return payload;
    }

    async function run() {
      const seq = ++runSeq;
      let result;
      try {
        // 模式一定要带上，否则后端不知道用哪套行动值口径
        const modeSelect = $("#mode");
        if (modeSelect?.value) state.target.mode = modeSelect.value;
        result = await ctx.call("plan", buildPlanPayload());
      } catch (err) {
        if (seq !== runSeq) return;
        $("#hero-error").innerHTML = `<p class="error-text">${esc(err.message)}</p>`;
        $("#hero").classList.add("is-error");
        return;
      }
      if (seq !== runSeq) return;
      $("#hero-error").innerHTML = "";
      $("#hero").classList.remove("is-error");
      lastResult = result;
      state.enabled = result.effects.enabled;

      renderDetail(result);
      const signature = result.effects.speed.map((item) => item.id).join(",");
      if (signature !== effectSignature) {
        effectSignature = signature;
        renderEffects(result);
      } else {
        syncEffectCheckboxes(result);
      }
      renderRelics(result);
      renderTargetOptions(result);
      renderTables(result);
      renderHero(result);
      renderTimeline(result);
      renderSummaries(result);
    }

    function renderDetail(result) {
      const speed = result.speed;
      $("#r-speed").textContent = fix(speed.final, 2);
      $("#r-base").textContent = fix(speed.base, 0);
      $("#r-split").textContent = `+${fix(speed.pct, 1)}% / +${fix(speed.flat, 1)}`;
      $("#r-av").textContent = `${fix(10000 / Math.max(1, speed.final), 2)} AV`;
      $("#r-formula").textContent = speed.formula;
      $("#r-breakdown").innerHTML = speed.breakdown.length
        ? `<div class="table-wrap"><table class="data"><thead><tr><th>来源</th><th class="num">类型</th><th class="num">数值</th></tr></thead><tbody>${speed.breakdown
            .map(
              (item) =>
                `<tr><td>${esc(item.label)}${item.team ? ' <span class="pill">全队</span>' : ""}${
                  item.text ? `<div class="muted small">${esc(item.text)}</div>` : ""
                }</td><td class="num">${
                  item.kind === "pct" ? "速度 %" : item.kind === "base" ? "基础" : "固定速度"
                }</td><td class="num">${item.kind === "base" ? "" : "+"}${fix(item.value, 1)}</td></tr>`,
            )
            .join("")}</tbody></table></div>`
        : `<p class="hint">还没有任何速度来源（只靠基础速度）。</p>`;

      $("#r-advance").innerHTML = result.advance.items.length
        ? `合计拉条 <b>${fix(result.advance.total, 1)}%</b>（折算 ${fix(result.advance.distance, 0)} 行动值距离）：` +
          result.advance.items.map((item) => esc(item.label)).join("；")
        : "没有拉条。";

      const verdict = result.verdict;
      $("#r-verdict").innerHTML =
        `<p class="formula">${esc(verdict.text)}</p>` +
        (result.warnings || []).map((text) => `<p class="warnbar">${esc(text)}</p>`).join("");

      const suggestions = result.suggestions || [];
      $("#r-suggestions").innerHTML = suggestions.length
        ? `<h3>怎么补上这 ${fix(Math.abs(verdict.gap), 2)} 速</h3><div class="table-wrap"><table class="data">
             <thead><tr><th>办法</th><th class="num">之后速度</th><th class="num">还需要</th><th>结果</th></tr></thead>
             <tbody>${suggestions
               .map(
                 (item) =>
                   `<tr><td>${esc(item.label)}</td><td class="num">${fix(item.speed, 1)}</td>` +
                   `<td class="num">${fix(Math.max(0, item.required), 1)}</td>` +
                   `<td>${item.ok ? "✅ 够了" : `还差 ${fix(item.gap, 1)}`}</td></tr>`,
               )
               .join("")}</tbody></table></div>`
        : "";

      const coneAdvance = result.effects.coneAdvance || [];
      const coneConditional = result.effects.coneConditional || [];
      $("#r-cone-advance").innerHTML =
        (coneAdvance.length
          ? `<h3>当前光锥的拉条</h3>` +
            coneAdvance
              .map(
                (item) =>
                  `<div class="effect-row"><span class="pill">叠影 ${item.superimpose}</span>` +
                  `<span class="grow">${esc(item.text)}</span>` +
                  `<span class="num">${item.counted !== undefined ? `已计入 ${fix(item.counted, 0)}%` : "填「光锥开大次数」后计入"}</span></div>`,
              )
              .join("")
          : "") +
        coneConditional
          .map(
            (item) =>
              `<div class="effect-row"><span class="pill">有条件</span>` +
              `<span class="grow">${esc(item.text)}</span><span class="num">未计入</span></div>`,
          )
          .join("");

      $("#r-advance-effects").innerHTML = result.effects.advance.length
        ? `<h3>检测到的拉条效果（参考，换算成上面的「其它拉条 %」）</h3>` +
          result.effects.advance
            .map(
              (item) =>
                `<div class="effect-row"><span class="pill">${esc(item.origin)}</span>` +
                `<span class="grow">${esc(item.text)}</span><span class="num">${fix(item.value, 0)}%</span></div>`,
            )
            .join("")
        : "";
    }

    const TRIGGER_TEXT = {
      passive: { label: "常驻", hint: "开局就生效，默认勾上" },
      onEnter: { label: "进战", hint: "进入战斗时触发，开局即生效" },
      perUlt: { label: "开大", hint: "要开大才生效，按「⑤目标」里的「首次开大」时刻开始算" },
      conditional: { label: "条件", hint: "需要满足特定条件才生效，请自行判断" },
    };

    function renderEffects(result) {
      const list = result.effects.speed;
      const box = $("#r-effects");
      if (!list.length) {
        box.innerHTML = `<p class="hint">这个角色 + 光锥组合没有检测到速度类效果。</p>`;
        return;
      }
      const enabled = new Set(result.effects.enabled);
      const groups = ["passive", "onEnter", "perUlt", "conditional"].map((key) => ({
        key,
        items: list.filter((item) => (TRIGGER_TEXT[item.trigger] ? item.trigger : "conditional") === key),
      }));
      box.innerHTML =
        groups
          .filter((group) => group.items.length)
          .map((group) => {
            const trigger = TRIGGER_TEXT[group.key];
            return `<div class="sp-effect-group">
              <div class="sp-effect-group-head"><span class="trigger-badge ${group.key}">${esc(trigger.label)}</span>
                <span class="muted small">${esc(trigger.hint)}</span></div>
              <div class="effect-list">${group.items
                .map((item) => {
                  const ally = item.apply === "ally";
                  const enemy = item.apply === "enemy";
                  const badge = ally
                    ? `<span class="trigger-badge conditional" title="提速对象是队友，不是自己，不计入本角色速度">仅队友</span>`
                    : enemy
                      ? `<span class="trigger-badge enemy" title="这是对敌方的效果，不计入本角色速度">作用于敌方</span>`
                      : "";
                  return `<label class="effect-row ${ally || enemy ? "ally-only" : ""}" title="${esc(
                    ally ? "这条提速给的是队友（不算作自己的速度）" : enemy ? "作用于敌方，不计入本角色" : trigger.hint,
                  )}">
                    <input type="checkbox" data-effect="${esc(item.id)}" ${enabled.has(item.id) ? "checked" : ""} />
                    <span class="pill">${esc(item.origin)}</span>
                    ${badge}
                    <span class="grow">${esc(item.text)}</span>
                    <span class="num">${item.value >= 0 ? "+" : ""}${fix(item.value, 1)}${item.kind === "pct" ? "%" : ""}${
                      item.apply === "team" ? "（全队）" : ""
                    }</span>
                  </label>`;
                })
                .join("")}</div></div>`;
          })
          .join("") +
        `<p class="hint">「条件」类不会自动计入，勾上表示你自己确认它成立；「仅队友」「作用于敌方」的不算这个角色的速度。</p>`;

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

    function describeEffect(effect) {
      return `${effect.slot} ${
        effect.kind === "pct"
          ? `速度 +${fix(effect.value, 1)}%`
          : effect.kind === "advance"
            ? `拉条 +${fix(effect.value, 0)}%`
            : `固定速度 +${fix(effect.value, 0)}`
      }`;
    }

    function renderRelics(result) {
      const applied = result.relicSets || [];
      const conditional = result.effects.conditional || [];
      $("#r-relics").innerHTML =
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
          ? `<h3>有条件的效果（未计入，需要的话自己加到「④其它」里）</h3>` +
            conditional
              .map(
                (effect) =>
                  `<div class="effect-row"><span class="pill">${esc(effect.setName)}·${esc(effect.slot)}</span>` +
                  `<span class="grow">${esc(effect.text)}</span>` +
                  `<span class="num">${esc(describeEffect(effect))}</span></div>`,
              )
              .join("")
          : "");
      // 有「开大才触发」的套装效果但开大次数是 0：显眼提示，免得以为功能坏了
      const blocked = conditional.filter((item) => item.note && item.note.includes("需要开大"));
      $("#relic-warn").innerHTML = blocked.length
        ? `<p class="warnbar">⚠ ${esc(
            blocked.map((item) => item.setName || item.name || "该效果").join("、"),
          )} 需要开大才生效：请把「开大次数」设成 1 或更大（目前是 0，所以没计入）。</p>`
        : "";
    }

    /* ---------------- 结论区 ---------------- */

    function renderHero(result) {
      const verdict = result.verdict;
      $("#hero-current").textContent = fix(verdict.currentSpeed, 1);
      $("#hero-need").textContent = fix(verdict.requiredSpeed, 1);
      $("#hero-target").textContent = `（${
        verdict.customAV > 0 ? `${fix(verdict.customAV, 0)} AV` : `${verdict.t}T`
      } · ${verdict.actions} 动）`;
      const gap = Number(verdict.gap);
      const gapBox = $("#hero-gap");
      if (gap > 0) {
        gapBox.className = "sp-hero-gap bad";
        gapBox.textContent = `还差 ${fix(gap, 1)} 速`;
        const rolls = Math.ceil(gap / SUBSTAT_ROLL);
        $("#hero-sub").textContent = `约需 ${rolls} 条速度副词条（按每条 ≈${SUBSTAT_ROLL} 速估算）· 当前行动值下能打 ${verdict.achievableActions} 动`;
      } else {
        gapBox.className = "sp-hero-gap good";
        gapBox.textContent = `已达标，多 ${fix(Math.abs(gap), 1)} 速`;
        $("#hero-sub").textContent = `当前行动值下能打 ${verdict.achievableActions} 动`;
      }
    }

    function renderTimeline(result) {
      const sim = result.simulation;
      const box = $("#r-timeline");
      if (!sim || !(sim.timeline || []).length) {
        box.innerHTML = `<p class="hint">这一套没有需要模拟的行动顺序。</p>`;
        return;
      }
      box.innerHTML =
        `<ol class="sp-timeline">${sim.timeline
          .map(
            (s) =>
              `<li><span class="sp-tl-no">第 ${s.action} 动</span>` +
              `<span class="num">${fix(s.speed, 1)} 速</span>` +
              `<span class="num muted">@ ${fix(s.av, 0)} AV</span>` +
              `<span class="muted small sp-tl-active">${(s.active || []).length ? esc(s.active.join("、")) : ""}</span></li>`,
          )
          .join("")}</ol>` +
        ((sim.notes || []).length ? `<p class="hint">${sim.notes.map((note) => esc(note)).join("<br/>")}</p>` : "");
    }

    let tableModeView = null; // 只影响「各模式需求」页签里看哪张表，不是计算状态

    function renderTables(result) {
      const tables = result.tables || [];
      const viewId = tables.some((t) => t.id === tableModeView) ? tableModeView : state.target.mode;
      $("#table-modes").innerHTML = tables
        .map(
          (t) =>
            `<button type="button" class="ghost small ${t.id === viewId ? "active" : ""}" data-view-mode="${esc(t.id)}">${esc(
              t.name,
            )}${t.id === state.target.mode ? " ·目标" : ""}</button>`,
        )
        .join("");
      $("#table-modes")
        .querySelectorAll("[data-view-mode]")
        .forEach((button) =>
          button.addEventListener("click", () => {
            tableModeView = button.dataset.viewMode;
            renderTables(lastResult);
          }),
        );
      const table = tables.find((item) => item.id === viewId) || tables[0];
      if (!table) {
        $("#r-tables").innerHTML = "";
        return;
      }
      const firstAV = Number(table.firstCycleAV ?? 150);
      const stepAV = Number(table.cycleAV ?? 100);
      const starLine = (table.stars || []).length
        ? `<p class="hint">星级线：${table.stars
            .map((star) => `${esc(star.label)} = ${star.cycles} 轮（${star.totalAV} AV）`)
            .join("　")}</p>`
        : "";
      $("#r-tables").innerHTML = `
        <p class="hint">${esc(table.note || "")}　绿色 = 当前速度可达；单元格里是需要的速度。</p>
        ${starLine}
        <div class="table-wrap">
          <table class="data sp-req">
            <thead><tr><th>动数 \\ T</th>${table.tValues
              .map((t) => `<th class="num">${t}T<div class="muted small">${firstAV + t * stepAV} AV</div></th>`)
              .join("")}</tr></thead>
            <tbody>${table.rows
              .map(
                (row) =>
                  `<tr><td>${row.actions} 动</td>${row.cells
                    .map((cell) => `<td class="num ${cell.reachable ? "reachable" : "unreachable"}">${fix(cell.speed, 1)}</td>`)
                    .join("")}</tr>`,
              )
              .join("")}</tbody>
          </table>
        </div>`;
    }

    function renderTargetOptions(result) {
      const modeSelect = $("#mode");
      if (!modeSelect.options.length) {
        modeSelect.innerHTML = result.tables
          .map((table) => `<option value="${esc(table.id)}">${esc(table.name)}</option>`)
          .join("");
      }
      const known = new Set((result.tables || []).map((table) => table.id));
      const activeMode =
        state.target.mode && known.has(state.target.mode) ? state.target.mode : modeSelect.value || result.tables[0]?.id;
      state.target.mode = activeMode;
      if (modeSelect.value !== activeMode) modeSelect.value = activeMode;

      const table = result.tables.find((item) => item.id === activeMode) || result.tables[0];
      const firstAV = Number(table?.firstCycleAV ?? 150);
      const stepAV = Number(table?.cycleAV ?? 100);
      const wanted = String(state.target.t);
      const tSelect = $("#targetT");
      tSelect.innerHTML = (table?.tValues || [0])
        .map(
          (t) => `<option value="${t}" ${String(t) === wanted ? "selected" : ""}>${t}T（${firstAV + t * stepAV} AV）</option>`,
        )
        .join("");
      if (![...tSelect.options].some((option) => option.selected)) {
        tSelect.value = String((state.target.t = table?.tValues?.[0] ?? 0));
      } else {
        tSelect.value = wanted;
      }
    }

    function renderSummaries(result) {
      const character = currentCharacter();
      const set = (id, text) => {
        const element = $(`#sum-${id}`);
        if (element) element.textContent = text;
      };
      set("char", `${character.name || "—"} · ${state.eidolon} 魂 · 初始 ${fix(character.effectiveBaseSpeed ?? character.baseSpeed, 0)} 速`);
      const cone = cones.find((item) => String(item.id) === String(state.lightconeId));
      set("cone", cone ? `${cone.name} · 叠影 ${state.superimpose}` : "不装备光锥");
      const four = fourPiecePicker.name(state.relic.fourPieceId);
      const orn = ornamentPicker.name(state.relic.ornamentIds?.[0]);
      set(
        "relic",
        [
          state.relic.fourPieceId ? four : "无 4 件套",
          state.relic.ornamentIds?.[0] ? orn : "无饰品",
          state.relic.speedBoots ? "速度鞋" : "非速度鞋",
        ].join(" · "),
      );
      const on = (result.effects.enabled || []).length;
      set(
        "bonus",
        `副词条 +${fix(state.relic.substatSpeed || 0, 0)} · 已勾 ${on} 条效果 · 拉条 ${fix(result.advance.total, 0)}%`,
      );
      const mode = (result.tables || []).find((t) => t.id === state.target.mode);
      const v = result.verdict;
      set(
        "target",
        `${mode?.name || state.target.mode} · ${v.customAV > 0 ? `${fix(v.customAV, 0)} AV` : `${v.t}T`} · ${v.actions} 动 · 首次开大 ${
          state.simulation.firstUltAction === 0 ? "进战" : `第 ${state.simulation.firstUltAction} 动后`
        }`,
      );
    }

    /* ---------------- 绑定（每个字段一个控件） ---------------- */

    const bindNumber = (id, apply) =>
      $(id).addEventListener("input", (event) => {
        apply(event.target.value);
        schedule();
      });
    const bindCheck = (id, apply) =>
      $(id).addEventListener("change", (event) => {
        apply(event.target.checked);
        schedule();
      });

    $("#superimpose").addEventListener("change", (event) => {
      state.superimpose = Number(event.target.value);
      state.enabled = null;
      schedule();
    });
    $("#eidolon").addEventListener("change", (event) => {
      state.eidolon = Number(event.target.value);
      state.enabled = null;
      schedule();
    });
    bindCheck("#speedBoots", (v) => (state.relic.speedBoots = !!v));
    bindCheck("#ultTargetsAlly", (v) => (state.relic.ultTargetsAlly = !!v));
    bindCheck("#excludeLastUlt", (v) => (state.advance.excludeLastUlt = !!v));
    bindNumber("#fourUlts", (v) => (state.relic.fourPieceUlts = Number(v || 0)));
    bindNumber("#substat", (v) => (state.relic.substatSpeed = Number(v || 0)));
    bindNumber("#customPct", (v) => (state.relic.customPct = Number(v || 0)));
    bindNumber("#customFlat", (v) => (state.relic.customFlat = Number(v || 0)));
    bindNumber("#coneUlts", (v) => (state.advance.coneUlts = Number(v || 0)));
    bindNumber("#advCustom", (v) => (state.advance.custom = Number(v || 0)));
    // 0 = 进战即开大（开大类效果从第 1 次行动起生效）
    bindNumber("#firstUltAction", (v) => (state.simulation.firstUltAction = Math.max(0, v === "" ? 1 : Number(v))));
    bindNumber("#targetActions", (v) => (state.target.actions = Math.max(1, Number(v || 1))));
    bindNumber("#customAV", (v) => (state.target.customAV = Math.max(0, Number(v || 0))));

    $("#mode").addEventListener("change", (event) => {
      state.target.mode = event.target.value || state.target.mode;
      state.target.t = 0;
      state.target.customAV = 0;
      $("#customAV").value = 0;
      tableModeView = null;
      run();
    });
    $("#targetT").addEventListener("change", (event) => {
      state.target.t = Number(event.target.value);
      state.target.customAV = 0;
      $("#customAV").value = 0;
      schedule();
    });
    root.querySelectorAll("[data-av]").forEach((button) => {
      button.addEventListener("click", () => {
        state.target.customAV = Number(button.dataset.av);
        $("#customAV").value = state.target.customAV;
        schedule();
      });
    });

    /* ---------------- 我的配装 ---------------- */

    let presets = {};

    function currentConfig() {
      const config = {
        simulation: state.simulation,
        aha: {
          err: Number($("#preset-err").value),
          initialEnergy: $("#preset-energy").value,
          rotation: $("#preset-rotation").value,
        },
        lightconeId: state.lightconeId,
        superimpose: state.superimpose,
        eidolon: state.eidolon,
        enabledEffects: state.enabled,
        relic: state.relic,
        advance: state.advance,
        target: state.target,
      };
      if (isCustom()) config.customCharacter = { ...state.custom };
      return config;
    }

    function refreshPresets() {
      const saved = presets[String(state.characterId)];
      $("#preset").innerHTML = saved
        ? `<option value="saved">已存：${esc(saved.savedAt)}</option>`
        : `<option value="">（这个角色还没存过）</option>`;
      $("#apply-preset").disabled = !saved;
      $("#delete-preset").disabled = !saved;
      $("#preset-note").textContent = saved
        ? `光锥 ${cones.find((cone) => String(cone.id) === String(saved.config?.lightconeId))?.name || "无"}　叠影 ${
            saved.config?.superimpose ?? "-"
          }　星魂 ${saved.config?.eidolon ?? "-"}（存在 userdata，升级不丢）`
        : "把当前这套（光锥/叠影/星魂/遗器/拉条/目标）存下来，下次一键套用。";
    }

    async function loadPresets() {
      try {
        presets = (await ctx.call("presets")).presets || {};
      } catch {
        presets = {};
      }
      refreshPresets();
    }

    $("#save-preset").addEventListener("click", async () => {
      const button = $("#save-preset");
      button.disabled = true;
      try {
        if (!$("#preset-err").checkValidity() || !$("#preset-energy").checkValidity()) {
          throw new Error("充能效率与开局资源需要填写非负数，开局资源也可以留空。");
        }
        const result = await ctx.call("save_preset", { characterId: state.characterId, config: currentConfig() });
        await loadPresets();
        $("#preset-note").textContent = `已保存（共 ${result.count} 个角色的配装）。`;
      } catch (err) {
        $("#preset-note").innerHTML = `<span class="error-text">${esc(err.message)}</span>`;
      } finally {
        button.disabled = false;
      }
    });

    $("#delete-preset").addEventListener("click", async () => {
      try {
        await ctx.call("delete_preset", { characterId: state.characterId });
        await loadPresets();
      } catch (err) {
        $("#preset-note").innerHTML = `<span class="error-text">${esc(err.message)}</span>`;
      }
    });

    $("#apply-preset").addEventListener("click", () => {
      const saved = presets[String(state.characterId)];
      if (!saved?.config) return;
      const config = saved.config;
      $("#preset-err").value = config.aha?.err ?? 0;
      $("#preset-energy").value = config.aha?.initialEnergy ?? "";
      $("#preset-rotation").value = config.aha?.rotation ?? "auto";
      state.simulation = { ...state.simulation, ...(config.simulation || {}) };
      state.lightconeId = config.lightconeId || "";
      state.superimpose = config.superimpose ?? 1;
      state.eidolon = config.eidolon ?? 0;
      state.enabled = config.enabledEffects ?? null;
      state.relic = { ...state.relic, ...(config.relic || {}) };
      state.advance = { ...state.advance, ...(config.advance || {}) };
      state.target = { ...state.target, ...(config.target || {}) };
      if (isCustom() && config.customCharacter) state.custom = { ...state.custom, ...config.customCharacter };
      syncControls();
      updateSplash();
      effectSignature = "";
      run();
    });

    /* ---------------- 自动推荐配装 ---------------- */

    $("#rec-btn").addEventListener("click", runRecommend);

    async function runRecommend() {
      const box = $("#r-recommend");
      box.innerHTML = `<div class="loading">穷举中…</div>`;
      try {
        const payload = {
          characterId: state.characterId,
          target: state.target,
          relic: { speedBoots: state.relic.speedBoots },
          superimpose: Number($("#recS").value || 1),
          coneUlts: Number($("#recConeUlts").value || 0),
          fourPieceUlts: Number($("#recFourUlts").value || 0),
          excludeLastUlt: !!state.advance.excludeLastUlt,
          maxResults: 10,
        };
        if (isCustom()) payload.customCharacter = { ...state.custom };
        const result = await ctx.call("recommend", payload);
        const assumptions = result.assumptions;
        box.innerHTML = `
          <p class="hint">穷举了 ${result.evaluated} 套组合 · 假设：速度鞋${assumptions.speedBoots ? "开" : "关"}、
            叠影 ${assumptions.superimpose}、光锥开大 ${assumptions.coneUlts} 次、风套开大 ${assumptions.fourPieceUlts} 次${
              assumptions.excludeLastUlt ? "（已按「轴底开大」扣掉最后一次）" : ""
            } · 目标 ${result.target.totalAV} AV 内 ${result.target.actions} 动</p>
          <div class="table-wrap">
            <table class="data">
              <thead><tr><th>光锥</th><th>4 件套</th><th>饰品</th><th class="num">速度</th><th class="num">拉条</th><th>结果</th><th></th></tr></thead>
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
                    <td><button type="button" class="ghost small" data-apply="${index}">套用</button></td>
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
            // 推荐按它自己的假设算（叠影、风套/光锥开大次数），套用时一起同步
            state.superimpose = Number(assumptions.superimpose || state.superimpose);
            state.relic.fourPieceUlts = Number(assumptions.fourPieceUlts || 0);
            state.advance.coneUlts = Number(assumptions.coneUlts || 0);
            syncControls();
            run();
          });
        });
      } catch (err) {
        box.innerHTML = `<p class="error-text">${esc(err.message)}</p>`;
      }
    }

    /* ---------------- 启动 ---------------- */

    fourPiecePicker.setItems(setOptions(catalog.fourPieceSets), state.relic.fourPieceId);
    ornamentPicker.setItems(setOptions(catalog.ornamentSets), "");
    $("#relic-note").textContent =
      `套装效果来自官方文案，选中即自动计入：4 件套可选 ${(catalog.fourPieceSets || []).length} 个、` +
      `位面饰品可选 ${(catalog.ornamentSets || []).length} 个。带条件的效果不会自动算，会单独列出来。`;
    const sources = catalog.sources || {};
    if (sources.generatedAt) {
      $("#char-info").textContent = `数据抓取于 ${sources.generatedAt}（米游社官方图鉴 + StarRailRes 数值）`;
    }

    renderCharGrid();
    updateSplash();
    await loadCones();
    await loadPresets();
    await run();
  },

  unmount() {},
};
