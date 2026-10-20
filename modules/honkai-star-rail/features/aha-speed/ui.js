/* 【阿哈时刻】与欢愉队配速排轴模拟 —— 前端界面
 *
 * 同时支持两种视图模式：
 *   1. 「🎭 欢愉队完整机制排轴模拟」（默认）：调用后端 `simulate` / `threshold` 引擎，
 *      完整模拟真珠【美学底本】拉人（10%/15%/30% + 4欢愉额外回合）与【艺术壁垒】90点固定回能、
 *      星神★阿哈【愿力】5大来源与终结技拉条【阿哈时刻】20%（E6 首次改为 100% 并 +100 笑点）与【欢愉万相】升格、
 *      砂金•戏浪终结技4回合提速（+30%/39%）、队友攻击叠【热意】满10点回合外施放欢愉技、
 *      行迹【纵享惊涛】/升格【三赌牌局】使阿哈速度+25与全队提速，以及存护砂金、爻光、火花、欢愉主等联动。
 *   2. 「📄 原版静态工具（original.html）」：逐字节原样嵌入 `original.html`（磁盘文件完全不动）。
 */

async function exists(url) {
  try {
    const response = await fetch(url, { method: "HEAD" });
    return response.ok;
  } catch {
    return false;
  }
}

function esc(v) {
  return String(v ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

function fmtNum(v, digits = 2) {
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  return n.toFixed(digits);
}

const TEAM_PRESETS = {
  aha_quad: {
    label: "阿哈 / 戏浪 / 真珠 / 爻光",
    short: "阿哈 / 戏浪 / 真珠 / 爻光",
    desc: "星神★阿哈【欢愉令使】锁定砂金•戏浪；真珠【美学底本】锁定砂金•戏浪，开大按欢愉人数拉条 10%/15%/30%，4 名欢愉角色时赋予 1 个额外回合；砂金•戏浪开大触发真珠【艺术壁垒】固定回能 90 点；星神★阿哈开大拉条【阿哈时刻】20% 并开启 3 回合【欢愉万相】；砂金•戏浪开大自身提速 30%（4 回合），队友攻击累积【热意】满 10 点后回合外施放欢愉技。",
    config: {
      maxAV: 300,
      useAeonAha: true,
      useTech: true,
      trace3Advance: true,
      ultAdvanceAha: 20,
      e1Wishpower: 5,
      ultSpdPct: 30,
      sanduTeamSpdPct: 15,
      aeonAhaBaseSpd: 94,
      aeonAhaLcBaseSpd: 12,
      ahaSpdPct: 0,
      ahaAdvancePct: 0,
    },
    team: [
      {
        id: "1511", name: "星神★阿哈", elation: true, baseSpd: 94, lcBaseSpd: 12, traceSpd: 5,
        permPct: 12, permFlat: 35, err: 0, eidolon: 0, initAdv: 0, targetSlot: 1, rotation: "skill",
        equipment: { vonwacq: false, godJoy: true, windSet4: false, danceS5: false, hasSigLc: true, hasSummerLc: false },
      },
      {
        id: "1513", name: "砂金•戏浪", elation: true, baseSpd: 107, lcBaseSpd: 0, traceSpd: 9,
        permPct: 6, permFlat: 28, err: 19.4, eidolon: 0, initAdv: 0, targetSlot: 0, rotation: "skill",
        equipment: { vonwacq: false, godJoy: false, windSet4: false, danceS5: false, hasSigLc: false, hasSummerLc: true },
      },
      {
        id: "1503", name: "真珠", elation: true, baseSpd: 99, lcBaseSpd: 0, traceSpd: 9,
        permPct: 12, permFlat: 26, err: 24.4, eidolon: 0, initAdv: 0, targetSlot: 1, rotation: "auto",
        equipment: { vonwacq: true, godJoy: false, windSet4: false, danceS5: false, hasSigLc: false, hasSummerLc: false },
      },
      {
        id: "1502", name: "爻光", elation: true, baseSpd: 101, lcBaseSpd: 0, traceSpd: 9,
        permPct: 18, permFlat: 45, err: 24.4, eidolon: 0, initAdv: 0, targetSlot: 1, rotation: "skill",
        equipment: { vonwacq: true, godJoy: false, windSet4: false, danceS5: false, hasSigLc: false, hasSummerLc: false },
      },
    ],
  },
  sandu_duel: {
    label: "戏浪 / 阿哈 / 星期日 / 砂金(存护)",
    short: "戏浪 / 阿哈 / 星期日 / 砂金(存护)",
    desc: "队内欢愉角色为砂金•戏浪与星神★阿哈 2 人；星神★阿哈开大进入【欢愉万相】后，砂金•戏浪【三赌牌局】使全队速度 +15%；行迹【纵享惊涛】使队友攻击时【阿哈时刻】速度 +25；星期日终结技为指定目标回复能量；砂金(存护)开大与护盾联动星神★阿哈行迹2。",
    config: {
      maxAV: 300,
      useAeonAha: true,
      useTech: true,
      trace3Advance: true,
      ultAdvanceAha: 20,
      e1Wishpower: 5,
      ultSpdPct: 30,
      sanduTeamSpdPct: 15,
      aeonAhaBaseSpd: 94,
      aeonAhaLcBaseSpd: 12,
      ahaSpdPct: 0,
      ahaAdvancePct: 0,
    },
    team: [
      {
        id: "1513", name: "砂金•戏浪", elation: true, baseSpd: 107, lcBaseSpd: 0, traceSpd: 9,
        permPct: 6, permFlat: 30, err: 19.4, eidolon: 1, initAdv: 0, targetSlot: 0, rotation: "skill",
        equipment: { vonwacq: false, godJoy: false, windSet4: false, danceS5: false, hasSigLc: false, hasSummerLc: true },
      },
      {
        id: "1511", name: "星神★阿哈", elation: true, baseSpd: 94, lcBaseSpd: 12, traceSpd: 5,
        permPct: 12, permFlat: 35, err: 0, eidolon: 1, initAdv: 0, targetSlot: 0, rotation: "skill",
        equipment: { vonwacq: false, godJoy: true, windSet4: false, danceS5: false, hasSigLc: true, hasSummerLc: false },
      },
      {
        id: "1313", name: "星期日", elation: false, baseSpd: 96, lcBaseSpd: 0, traceSpd: 0,
        permPct: 6, permFlat: 33, err: 24.4, eidolon: 0, initAdv: 0, targetSlot: 0, rotation: "skill",
        equipment: { vonwacq: false, godJoy: false, windSet4: false, danceS5: true, hasSigLc: false, hasSummerLc: false },
      },
      {
        id: "1304", name: "砂金(存护)", elation: false, baseSpd: 106, lcBaseSpd: 0, traceSpd: 0,
        permPct: 6, permFlat: 28, err: 19.4, eidolon: 0, initAdv: 0, targetSlot: 0, rotation: "skill",
        equipment: { vonwacq: false, godJoy: false, windSet4: false, danceS5: false, hasSigLc: false, hasSummerLc: false },
      },
    ],
  },
  feiying_aha: {
    label: "绯英 / 阿哈 / 真珠 / 爻光",
    short: "绯英 / 阿哈 / 真珠 / 爻光",
    desc: "真珠【美学底本】与星神★阿哈【欢愉令使】均锁定 1 号位绯英；真珠开大拉条绯英 30% 并赋予 1 个额外回合；绯英累计 240 能量触发【狐狸老师】追击，满 480 能量开大时触发真珠【艺术壁垒】固定回能 90 点。",
    config: {
      maxAV: 300,
      useAeonAha: true,
      useTech: true,
      trace3Advance: true,
      ultAdvanceAha: 20,
      e1Wishpower: 5,
      ultSpdPct: 30,
      sanduTeamSpdPct: 15,
      aeonAhaBaseSpd: 94,
      aeonAhaLcBaseSpd: 12,
      ahaSpdPct: 0,
      ahaAdvancePct: 0,
    },
    team: [
      {
        id: "1505", name: "绯英", elation: true, baseSpd: 104, lcBaseSpd: 0, traceSpd: 5,
        permPct: 6, permFlat: 25, err: 0, eidolon: 0, initAdv: 0, targetSlot: 0, rotation: "skill",
        equipment: { vonwacq: false, godJoy: false, windSet4: false, danceS5: false, hasSigLc: false, hasSummerLc: false },
      },
      {
        id: "1511", name: "星神★阿哈", elation: true, baseSpd: 94, lcBaseSpd: 12, traceSpd: 5,
        permPct: 12, permFlat: 35, err: 0, eidolon: 0, initAdv: 0, targetSlot: 0, rotation: "skill",
        equipment: { vonwacq: false, godJoy: true, windSet4: false, danceS5: false, hasSigLc: true, hasSummerLc: false },
      },
      {
        id: "1503", name: "真珠", elation: true, baseSpd: 99, lcBaseSpd: 0, traceSpd: 9,
        permPct: 12, permFlat: 26, err: 24.4, eidolon: 2, initAdv: 0, targetSlot: 0, rotation: "auto",
        equipment: { vonwacq: true, godJoy: false, windSet4: false, danceS5: false, hasSigLc: false, hasSummerLc: false },
      },
      {
        id: "1502", name: "爻光", elation: true, baseSpd: 101, lcBaseSpd: 0, traceSpd: 9,
        permPct: 18, permFlat: 50, err: 24.4, eidolon: 2, initAdv: 0, targetSlot: 0, rotation: "skill",
        equipment: { vonwacq: true, godJoy: false, windSet4: false, danceS5: false, hasSigLc: false, hasSummerLc: false },
      },
    ],
  },
  wolf_sparkle: {
    label: "银狼 / 火花 / 爻光 / 真珠",
    short: "银狼 / 火花 / 爻光 / 真珠",
    desc: "队伍不含星神★阿哈，【阿哈时刻】底速 80；银狼LV.999 将笑点转化为【隐藏分】，满 60 点开大并进入【无敌玩家】；火花在【阿哈时刻】结束后获得额外回合（2魂）；真珠锁定银狼拉条 30%、赋予额外回合，并在目标开大时触发【艺术壁垒】固定回能 90 点。",
    config: {
      maxAV: 300,
      useAeonAha: false,
      useTech: true,
      trace3Advance: false,
      ultAdvanceAha: 20,
      e1Wishpower: 5,
      ultSpdPct: 30,
      sanduTeamSpdPct: 15,
      aeonAhaBaseSpd: 80,
      aeonAhaLcBaseSpd: 0,
      ahaSpdPct: 0,
      ahaAdvancePct: 0,
    },
    team: [
      {
        id: "1506", name: "银狼LV.999", elation: true, baseSpd: 110, lcBaseSpd: 0, traceSpd: 9,
        permPct: 18, permFlat: 50, err: 0, eidolon: 0, initAdv: 0, targetSlot: 0, rotation: "skill",
        equipment: { vonwacq: false, godJoy: false, windSet4: false, danceS5: false, hasSigLc: false, hasSummerLc: false },
      },
      {
        id: "1501", name: "火花", elation: true, baseSpd: 107, lcBaseSpd: 0, traceSpd: 0,
        permPct: 6, permFlat: 43, err: 19.4, eidolon: 2, initAdv: 0, targetSlot: 0, rotation: "skill",
        equipment: { vonwacq: false, godJoy: false, windSet4: false, danceS5: false, hasSigLc: false, hasSummerLc: false },
      },
      {
        id: "1502", name: "爻光", elation: true, baseSpd: 101, lcBaseSpd: 0, traceSpd: 9,
        permPct: 18, permFlat: 70, err: 24.4, eidolon: 1, initAdv: 0, targetSlot: 0, rotation: "skill",
        equipment: { vonwacq: false, godJoy: false, windSet4: false, danceS5: false, hasSigLc: false, hasSummerLc: false },
      },
      {
        id: "1503", name: "真珠", elation: true, baseSpd: 99, lcBaseSpd: 0, traceSpd: 9,
        permPct: 0, permFlat: 26, err: 24.4, eidolon: 0, initAdv: 0, targetSlot: 0, rotation: "auto",
        equipment: { vonwacq: false, godJoy: false, windSet4: false, danceS5: false, hasSigLc: false, hasSummerLc: false },
      },
    ],
  },
};

const EIDOLON_CHOICES = {
  "1511": [0, 1, 2, 6],
  "1513": [0, 1, 2],
  "1503": [0, 2],
  "1502": [0, 1, 2],
  "1501": [0, 2, 4],
  "1505": [0, 6],
  "1506": [0, 1],
  "1304": [0, 1, 4],
  "1313": [0, 4],
  "1309": [0, 2],
};

const TARGET_LABELS = {
  "1503": "【美学底本】目标",
  "1511": "【欢愉令使】目标",
  "1313": "技能指定目标",
  "8009": "技能指定目标",
};

const LIGHT_CONE_OPTIONS = {
  "1511": { key: "hasSigLc", label: "阿哈专武《当第一声「阿哈」响起》" },
  "1513": { key: "hasSummerLc", label: "《向浪花掷下盛夏》" },
  "1503": { key: "hasPearlLc", label: "真珠专武《献给明日的色彩》" },
  "1502": { key: "hasYaoLc", label: "《当她决定看见》" },
  "8009": { key: "hasYaoLc", label: "《当她决定看见》" },
  "1505": { key: "hasFeiyLc", label: "绯英专武《邂逅于下一个花季》" },
  "1313": { key: "hasSundayLc", label: "星期日专武《回到大地的飞行》" },
  "1309": { key: "hasRobinLc", label: "知更鸟专武《夜色流光溢彩》" },
  "1506": { key: "hasWolfLc", label: "银狼专武《欢迎来到银河城》" },
};

const RELIC_OPTIONS = [
  { key: "vonwacq", label: "翁瓦克", title: "ERR +5%；进战速度 ≥ 120 时开局拉条 40%" },
  { key: "godJoy", label: "神的瞬息欢愉", title: "速度 +6%" },
  { key: "windSet4", label: "风套4件", title: "施放终结技后自身拉条 25%" },
  { key: "danceS5", label: "舞舞舞S5", title: "施放终结技后我方全体拉条 24%" },
];

function errApplies(uid) {
  return uid !== "1511" && uid !== "1505" && uid !== "1506";
}

function errText(unit) {
  if (!unit || !errApplies(unit.id)) return "—";
  return `${fmtNum(unit.err, 1)}%`;
}

export default {
  title: "阿哈时刻配速",

  async mount(root, ctx) {
    const base =
      ctx.feature.baseUrl || `/modules/${ctx.moduleId}/features/${ctx.featureId}`;

    // 兼容单文件网页版与服务端调用
    const localApi =
      typeof window !== "undefined" && window.GT_AHA_SPEED_API
        ? window.GT_AHA_SPEED_API.createApi()
        : null;

    async function callAction(action, payload = {}) {
      if (ctx && typeof ctx.call === "function") {
        try {
          return await ctx.call(action, payload);
        } catch (err) {
          if (localApi) return localApi.call(action, payload);
          throw err;
        }
      }
      if (localApi) return localApi.call(action, payload);
      throw new Error("未找到 aha-speed 后端接口");
    }

    let catalog = { roster: [] };
    try {
      catalog = await callAction("catalog");
    } catch {
      catalog = { roster: [] };
    }
    const rosterById = {};
    (catalog.roster || []).forEach((r) => {
      rosterById[r.id] = r;
    });

    const state = {
      presetKey: "aha_quad",
      filterType: "core", // core | all | ultimate | aha | extra | elation | pearl | aeon | aventurine
      toolsTab: "threshold", // threshold | original
      threshold: {
        targetAV: 150,
        actions: 2,
        advancePct: 0,
      },
      config: structuredClone(TEAM_PRESETS.aha_quad.config),
      team: structuredClone(TEAM_PRESETS.aha_quad.team),
      simResult: null,
      thresholdResult: null,
    };

    function renderShell() {
      root.innerHTML = `
        <div class="aha-sim-wrap">
          <div class="aha-topbar">
            <div class="aha-title-block">
              <h2>🎭 欢愉队配速与【阿哈时刻】排轴模拟器</h2>
              <p>角色卡默认只保留速度、ERR、光锥与遗器；星魂、出招、目标等收进「高级」。工具在页面底部。</p>
            </div>
          </div>
          <div id="aha-body-container"></div>
        </div>
      `;

      const body = root.querySelector("#aha-body-container");
      mountSimulatorView(body);
    }

    async function mountOriginalIframe(container) {
      const preloadedHtml =
        typeof window !== "undefined" ? window.GT_AHA_ORIGINAL_HTML : "";
      let html;
      if (preloadedHtml) {
        html = preloadedHtml;
      } else {
        try {
          const response = await fetch(`${base}/original.html`);
          if (!response.ok) throw new Error(`HTTP ${response.status}`);
          html = await response.text();
        } catch (err) {
          container.innerHTML = `<div class="card error">
            <h2>读不到原版文件</h2>
            <p class="error-text">${esc(err.message)}</p>
            <p class="muted small">应该是 <code>${esc(base)}/original.html</code> 丢了。</p>
          </div>`;
          return;
        }
      }

      const preloadedVendor =
        typeof window !== "undefined" ? window.GT_AHA_VENDOR_JS : "";
      if (preloadedVendor) {
        html = html.replace(
          '<script src="https://cdn.tailwindcss.com"><\/script>',
          ""
        );
        html = html.replace(
          "</head>",
          () => `<script>${preloadedVendor}<\/script>\n</head>`
        );
      } else {
        const vendorUrl = `${base}/vendor/tailwind.js`;
        if (await exists(vendorUrl)) {
          const absolute = new URL(vendorUrl, location.origin).href;
          html = html.replace('src="https://cdn.tailwindcss.com"', `src="${absolute}"`);
        }
      }

      container.innerHTML = `<iframe class="aha-original-frame" title="【阿哈时刻】配速（原版工具）"></iframe>`;
      const frame = container.querySelector("iframe");
      frame.setAttribute("srcdoc", html);
    }

    function mountSimulatorView(container) {
      const presetButtons = Object.entries(TEAM_PRESETS)
        .map(
          ([key, item]) =>
            `<button type="button" class="aha-preset-btn ${state.presetKey === key ? "is-active" : ""}" data-preset="${key}">${esc(item.short || item.label)}</button>`
        )
        .join("");

      const presetDesc = TEAM_PRESETS[state.presetKey]?.desc || "";
      const hasAven = state.team.some((u) => u.id === "1513");
      const filters = [
        ["core", "关键事件"],
        ["all", "显示全部行动"],
        ["ultimate", "终结技"],
        ["aha", "阿哈时刻"],
        ["extra", "额外回合"],
        ["elation", "欢愉技"],
        ["pearl", "真珠"],
        ["aeon", "阿哈"],
        ["aventurine", "砂金"],
      ];
      const filterButtons = filters
        .map(
          ([key, label]) =>
            `<button type="button" class="aha-filter-btn ${state.filterType === key ? "is-active" : ""}" data-filter="${key}">${label}</button>`
        )
        .join("");

      container.innerHTML = `
        <div class="aha-preset-bar">
          <span class="aha-preset-label">阵容预设：</span>
          ${presetButtons}
        </div>
        <details class="aha-preset-details">
          <summary>预设说明（客观机制）</summary>
          <div class="aha-preset-desc" id="aha-preset-desc">${esc(presetDesc)}</div>
        </details>

        <div class="aha-result-bar" id="aha-summary-box"></div>

        <div class="aha-main-grid">
          <div class="aha-col aha-col-left">
            <div class="aha-card">
              <div class="aha-card-head">
                <h3>🎭 全局机制</h3>
                <span class="aha-pill">开关</span>
              </div>

              <div class="aha-switch-list">
                <label class="aha-switch-row">
                  <span>启用星神★阿哈升格底速（80 → 94 + 专武白值）</span>
                  <input type="checkbox" id="cfg-useAeonAha" ${state.config.useAeonAha ? "checked" : ""}>
                </label>
                <label class="aha-switch-row">
                  <span>秘技进战</span>
                  <input type="checkbox" id="cfg-useTech" ${state.config.useTech ? "checked" : ""}>
                </label>
                <label class="aha-switch-row">
                  <span>阿哈行迹3【盒中蕴藏的世界】（进战自身拉条 30%）</span>
                  <input type="checkbox" id="cfg-trace3Advance" ${state.config.trace3Advance ? "checked" : ""}>
                </label>
              </div>

              <details class="aha-advanced">
                <summary>高级参数</summary>
                <div class="aha-form-grid">
                  <div class="aha-field">
                    <label>阿哈大招拉条【阿哈时刻】 (%)</label>
                    <input type="number" class="aha-input" id="cfg-ultAdvanceAha" value="${state.config.ultAdvanceAha}" step="5">
                  </div>
                  ${
                    hasAven
                      ? `<div class="aha-field">
                          <label>砂金•戏浪大招自提速 (%)</label>
                          <input type="number" class="aha-input" id="cfg-ultSpdPct" value="${state.config.ultSpdPct}" step="3">
                        </div>
                        <div class="aha-field">
                          <label>【三赌牌局】全队提速 (%)</label>
                          <input type="number" class="aha-input" id="cfg-sanduTeamSpdPct" value="${state.config.sanduTeamSpdPct}" step="5">
                        </div>`
                      : ""
                  }
                  <div class="aha-field">
                    <label>【阿哈时刻】额外速度加成 (%)</label>
                    <input type="number" class="aha-input" id="cfg-ahaSpdPct" value="${state.config.ahaSpdPct}" step="1">
                  </div>
                  <div class="aha-field">
                    <label>开局拉条【阿哈时刻】 (%)</label>
                    <input type="number" class="aha-input" id="cfg-ahaAdvancePct" value="${state.config.ahaAdvancePct}" step="5">
                  </div>
                </div>
                <p class="aha-advanced-note">阿哈基础速度与专武白值在星神★阿哈角色卡的「高级」里填写。</p>
              </details>
            </div>
          </div>

          <div class="aha-col">
            <div class="aha-card">
              <div class="aha-card-head">
                <h3>👥 队伍与配装</h3>
                <div style="display:flex;align-items:center;gap:8px;font-size:12px;">
                  <span>模拟上限 (AV)：</span>
                  <input type="number" class="aha-input" id="cfg-maxAV" value="${state.config.maxAV}" min="100" max="1000" step="50" style="width:82px;text-align:center;">
                </div>
              </div>
              <div class="aha-team-list" id="aha-team-list"></div>
            </div>

            <div class="aha-card">
              <div class="aha-card-head">
                <div>
                  <h3>⏱️ 行动值与技能事件时间轴</h3>
                  <small id="aha-timeline-sub" style="color:var(--muted,#94a3b8);font-size:11.5px;"></small>
                </div>
                <div class="aha-filter-bar">${filterButtons}</div>
              </div>
              <div class="aha-timeline-list" id="aha-timeline-list"></div>
            </div>
          </div>
        </div>

        <details class="aha-tools">
          <summary>🛠 工具（速度阈值反推 / 旧版静态工具）</summary>
          <div class="aha-tool-tabs">
            <button type="button" class="aha-tool-tab ${state.toolsTab === "threshold" ? "is-active" : ""}" data-tool-tab="threshold">速度阈值反推</button>
            <button type="button" class="aha-tool-tab ${state.toolsTab === "original" ? "is-active" : ""}" data-tool-tab="original">旧版静态工具</button>
          </div>

          <div class="aha-tool-panel" id="aha-tool-threshold" ${state.toolsTab === "original" ? "hidden" : ""}>
            <div class="aha-form-grid cols-3">
              <div class="aha-field">
                <label>目标行动值上限</label>
                <select class="aha-select" id="thr-targetAV">
                  <option value="150" ${state.threshold.targetAV === 150 ? "selected" : ""}>0T 首轮 (150 AV)</option>
                  <option value="250" ${state.threshold.targetAV === 250 ? "selected" : ""}>1T 次轮 (250 AV)</option>
                  <option value="300" ${state.threshold.targetAV === 300 ? "selected" : ""}>绝境节点 (300 AV)</option>
                  <option value="350" ${state.threshold.targetAV === 350 ? "selected" : ""}>2T 三轮 (350 AV)</option>
                  <option value="450" ${state.threshold.targetAV === 450 ? "selected" : ""}>3T 四轮 (450 AV)</option>
                </select>
              </div>
              <div class="aha-field">
                <label>期望行动次数</label>
                <input type="number" class="aha-input" id="thr-actions" value="${state.threshold.actions}" min="1" max="15">
              </div>
              <div class="aha-field">
                <label>累计全身拉条 (%)</label>
                <input type="number" class="aha-input" id="thr-advancePct" value="${state.threshold.advancePct}" step="5">
              </div>
            </div>
            <div class="aha-result-box" id="aha-threshold-box"></div>
          </div>

          <div class="aha-tool-panel" id="aha-tool-original" ${state.toolsTab === "original" ? "" : "hidden"}></div>
        </details>
      `;

      // 绑定预设切换
      container.querySelectorAll(".aha-preset-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          const key = btn.dataset.preset;
          if (!TEAM_PRESETS[key]) return;
          state.presetKey = key;
          state.config = structuredClone(TEAM_PRESETS[key].config);
          state.team = structuredClone(TEAM_PRESETS[key].team);
          mountSimulatorView(container);
        });
      });

      // 绑定全局配置控件
      const bindChk = (id, key) => {
        const el = container.querySelector(`#${id}`);
        if (!el) return;
        el.addEventListener("change", () => {
          state.config[key] = el.checked;
          if (key === "useAeonAha") {
            state.config.aeonAhaBaseSpd = el.checked ? 94 : 80;
            state.config.aeonAhaLcBaseSpd = el.checked ? 12 : 0;
            const slot = state.team.findIndex((u) => u.id === "1511");
            if (slot >= 0) {
              state.team[slot].baseSpd = state.config.aeonAhaBaseSpd;
              state.team[slot].lcBaseSpd = state.config.aeonAhaLcBaseSpd;
            }
            renderTeamCards(container);
          }
          runSimulation();
        });
      };
      bindChk("cfg-useAeonAha", "useAeonAha");
      bindChk("cfg-useTech", "useTech");
      bindChk("cfg-trace3Advance", "trace3Advance");

      const bindNum = (id, key) => {
        const el = container.querySelector(`#${id}`);
        if (!el) return;
        el.addEventListener("input", () => {
          state.config[key] = parseFloat(el.value) || 0;
          runSimulation();
        });
      };
      bindNum("cfg-ultAdvanceAha", "ultAdvanceAha");
      bindNum("cfg-ultSpdPct", "ultSpdPct");
      bindNum("cfg-sanduTeamSpdPct", "sanduTeamSpdPct");
      bindNum("cfg-ahaSpdPct", "ahaSpdPct");
      bindNum("cfg-ahaAdvancePct", "ahaAdvancePct");
      bindNum("cfg-maxAV", "maxAV");

      // 绑定阈值反推
      ["thr-targetAV", "thr-actions", "thr-advancePct"].forEach((id) => {
        const el = container.querySelector(`#${id}`);
        if (!el) return;
        el.addEventListener("input", () => {
          state.threshold.targetAV = parseFloat(container.querySelector("#thr-targetAV").value) || 150;
          state.threshold.actions = parseFloat(container.querySelector("#thr-actions").value) || 2;
          state.threshold.advancePct = parseFloat(container.querySelector("#thr-advancePct").value) || 0;
          runThreshold();
        });
      });

      // 绑定时间轴筛选按钮
      container.querySelectorAll(".aha-filter-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          state.filterType = btn.dataset.filter;
          container.querySelectorAll(".aha-filter-btn").forEach((b) =>
            b.classList.toggle("is-active", b.dataset.filter === state.filterType)
          );
          if (state.simResult) renderTimeline(container, state.simResult);
        });
      });

      // 绑定底部工具页签
      container.querySelectorAll(".aha-tool-tab").forEach((btn) => {
        btn.addEventListener("click", () => {
          state.toolsTab = btn.dataset.toolTab;
          container.querySelectorAll(".aha-tool-tab").forEach((b) =>
            b.classList.toggle("is-active", b.dataset.toolTab === state.toolsTab)
          );
          const thresholdPanel = container.querySelector("#aha-tool-threshold");
          const originalPanel = container.querySelector("#aha-tool-original");
          if (thresholdPanel) thresholdPanel.hidden = state.toolsTab !== "threshold";
          if (originalPanel) originalPanel.hidden = state.toolsTab !== "original";
          if (state.toolsTab === "original" && originalPanel && !originalPanel.dataset.mounted) {
            originalPanel.dataset.mounted = "1";
            mountOriginalIframe(originalPanel);
          }
        });
      });

      renderTeamCards(container);
      runSimulation();
      runThreshold();

      if (state.toolsTab === "original") {
        const originalPanel = container.querySelector("#aha-tool-original");
        if (originalPanel && !originalPanel.dataset.mounted) {
          originalPanel.dataset.mounted = "1";
          mountOriginalIframe(originalPanel);
        }
      }
    }

    function renderTeamCards(container) {
      const box = container.querySelector("#aha-team-list");
      if (!box) return;
      const rosterOpts = (catalog.roster || []).length
        ? catalog.roster
        : [
            { id: "1511", name: "星神★阿哈", elation: true, baseSpd: 94, traceSpd: 5, lcBaseSpd: 12 },
            { id: "1513", name: "砂金•戏浪", elation: true, baseSpd: 107, traceSpd: 9, lcBaseSpd: 0 },
            { id: "1503", name: "真珠", elation: true, baseSpd: 99, traceSpd: 9, lcBaseSpd: 0 },
            { id: "1502", name: "爻光", elation: true, baseSpd: 101, traceSpd: 9, lcBaseSpd: 0 },
            { id: "1501", name: "火花", elation: true, baseSpd: 107, traceSpd: 0, lcBaseSpd: 0 },
            { id: "8009", name: "开拓者•欢愉", elation: true, baseSpd: 106, traceSpd: 0, lcBaseSpd: 0 },
            { id: "1505", name: "绯英", elation: true, baseSpd: 104, traceSpd: 5, lcBaseSpd: 0 },
            { id: "1506", name: "银狼LV.999", elation: true, baseSpd: 110, traceSpd: 9, lcBaseSpd: 0 },
            { id: "1304", name: "砂金(存护)", elation: false, baseSpd: 106, traceSpd: 0, lcBaseSpd: 0 },
            { id: "1313", name: "星期日", elation: false, baseSpd: 96, traceSpd: 0, lcBaseSpd: 0 },
            { id: "1309", name: "知更鸟", elation: false, baseSpd: 102, traceSpd: 5, lcBaseSpd: 0 },
          ];

      box.innerHTML = state.team
        .map((unit, idx) => {
          const charOptions = rosterOpts
            .map(
              (r) =>
                `<option value="${esc(r.id)}" ${r.id === unit.id ? "selected" : ""}>${esc(r.name)} (${r.elation ? "欢愉" : r.path || "辅助"})</option>`
            )
            .join("");

          const targetOptions = state.team
            .map(
              (t, tIdx) =>
                `<option value="${tIdx}" ${Number(unit.targetSlot) === tIdx ? "selected" : ""}>${tIdx + 1}号位·${esc(t.name)}</option>`
            )
            .join("");

          const targetLabel = TARGET_LABELS[unit.id];
          const eidolonChoices = EIDOLON_CHOICES[unit.id];
          const lc = LIGHT_CONE_OPTIONS[unit.id];
          const showRotation = unit.id !== "1503";
          const showErr = errApplies(unit.id);
          const eq = unit.equipment || {};

          const eidolonHtml = eidolonChoices
            ? `<div class="aha-field">
                 <label>星魂</label>
                 <select class="aha-select unit-eidolon" data-slot="${idx}">
                   ${eidolonChoices
                     .map((e) => `<option value="${e}" ${Number(unit.eidolon) === e ? "selected" : ""}>E${e}</option>`)
                     .join("")}
                 </select>
               </div>`
            : `<div class="aha-advanced-note">该角色没有会影响排轴的星魂档位。</div>`;

          return `
            <div class="aha-unit-card ${unit.elation ? "is-elation" : ""}" data-slot="${idx}">
              <div class="aha-unit-top">
                <div class="aha-unit-identity">
                  <span class="aha-slot-badge">${idx + 1}号位</span>
                  <select class="aha-select unit-char-select" data-slot="${idx}" style="width:155px;font-weight:600;">
                    ${charOptions}
                  </select>
                  <label class="aha-equip-chk" title="勾选后计入【阿哈时刻】速度加权，并参与欢愉技结算">
                    <input type="checkbox" class="unit-elation-chk" data-slot="${idx}" ${unit.elation ? "checked" : ""}>
                    <span style="color:#f472b6;font-weight:600;">欢愉命途</span>
                  </label>
                </div>
                <div class="aha-unit-metrics" id="unit-metrics-${idx}"></div>
              </div>

              <div class="aha-unit-loadout">
                <span class="aha-loadout-title">光锥</span>
                ${
                  lc
                    ? `<label class="aha-equip-chk" title="勾选后启用该光锥的排轴效果">
                        <input type="checkbox" class="unit-eq" data-slot="${idx}" data-eq="${lc.key}" ${eq[lc.key] ? "checked" : ""}>
                        <span>${esc(lc.label)}</span>
                      </label>`
                    : `<span class="aha-muted">无专属光锥</span>`
                }
                <span class="aha-loadout-title">遗器</span>
                ${RELIC_OPTIONS.map(
                  (relic) => `<label class="aha-equip-chk" title="${esc(relic.title)}">
                    <input type="checkbox" class="unit-eq" data-slot="${idx}" data-eq="${relic.key}" ${eq[relic.key] ? "checked" : ""}>
                    <span>${relic.label}</span>
                  </label>`
                ).join("")}
              </div>

              <details class="aha-advanced">
                <summary>高级（星魂 / 出招 / 目标 / 速度明细）</summary>
                <div class="aha-form-grid">
                  <div class="aha-field">
                    <label>基础白值</label>
                    <input type="number" class="aha-input unit-num" data-slot="${idx}" data-key="baseSpd" value="${unit.baseSpd}" step="1">
                  </div>
                  <div class="aha-field">
                    <label>光锥白值</label>
                    <input type="number" class="aha-input unit-num" data-slot="${idx}" data-key="lcBaseSpd" value="${unit.lcBaseSpd || 0}" step="2">
                  </div>
                  <div class="aha-field">
                    <label>行迹速度</label>
                    <input type="number" class="aha-input unit-num" data-slot="${idx}" data-key="traceSpd" value="${unit.traceSpd || 0}" step="1">
                  </div>
                  <div class="aha-field">
                    <label>速度加成(%)</label>
                    <input type="number" class="aha-input unit-num" data-slot="${idx}" data-key="permPct" value="${unit.permPct || 0}" step="1">
                  </div>
                  <div class="aha-field">
                    <label>固定速度(+)</label>
                    <input type="number" class="aha-input unit-num" data-slot="${idx}" data-key="permFlat" value="${unit.permFlat || 0}" step="1">
                  </div>
                  <div class="aha-field">
                    <label>开局拉条(%)</label>
                    <input type="number" class="aha-input unit-num" data-slot="${idx}" data-key="initAdv" value="${unit.initAdv || 0}" step="5">
                  </div>
                  ${
                    showErr
                      ? `<div class="aha-field">
                          <label>充能效率(%)</label>
                          <input type="number" class="aha-input unit-num" data-slot="${idx}" data-key="err" value="${unit.err || 0}" step="0.1">
                        </div>`
                      : `<div class="aha-advanced-note">特殊能量，不吃 ERR。</div>`
                  }
                  ${eidolonHtml}
                  ${
                    showRotation
                      ? `<div class="aha-field">
                          <label>出招方式</label>
                          <select class="aha-select unit-rotation" data-slot="${idx}">
                            <option value="auto" ${unit.rotation === "auto" ? "selected" : ""}>智能出招</option>
                            <option value="skill" ${unit.rotation === "skill" ? "selected" : ""}>全程战技</option>
                            <option value="basic" ${unit.rotation === "basic" ? "selected" : ""}>全程普攻</option>
                          </select>
                        </div>`
                      : ""
                  }
                  ${
                    targetLabel
                      ? `<div class="aha-field">
                          <label>${esc(targetLabel)}</label>
                          <select class="aha-select unit-target" data-slot="${idx}">
                            ${targetOptions}
                          </select>
                        </div>`
                      : ""
                  }
                </div>
              </details>
            </div>
          `;
        })
        .join("");

      // 绑定角色下拉切换
      box.querySelectorAll(".unit-char-select").forEach((sel) => {
        sel.addEventListener("change", () => {
          const slot = Number(sel.dataset.slot);
          const cid = sel.value;
          const spec = rosterById[cid] || {};
          state.team[slot] = {
            id: cid,
            name: spec.name || cid,
            elation: spec.elation !== undefined ? Boolean(spec.elation) : true,
            baseSpd: spec.baseSpd ?? 100,
            lcBaseSpd: spec.lcBaseSpd ?? 0,
            traceSpd: spec.traceSpd ?? 0,
            permPct: 6,
            permFlat: 25,
            err: cid === "1511" ? 0 : 19.4,
            eidolon: 0,
            initAdv: 0,
            targetSlot: slot === 0 ? 1 : 0,
            rotation: spec.rotation || "skill",
            equipment: {
              vonwacq: false,
              godJoy: cid === "1511",
              windSet4: false,
              danceS5: false,
              hasSigLc: cid === "1511",
              hasSummerLc: cid === "1513",
            },
          };
          if (cid === "1511") {
            state.config.aeonAhaBaseSpd = state.team[slot].baseSpd;
            state.config.aeonAhaLcBaseSpd = state.team[slot].lcBaseSpd;
          }
          renderTeamCards(container);
          runSimulation();
        });
      });

      box.querySelectorAll(".unit-elation-chk").forEach((chk) => {
        chk.addEventListener("change", () => {
          const slot = Number(chk.dataset.slot);
          state.team[slot].elation = chk.checked;
          runSimulation();
        });
      });

      box.querySelectorAll(".unit-eidolon").forEach((sel) => {
        sel.addEventListener("change", () => {
          const slot = Number(sel.dataset.slot);
          state.team[slot].eidolon = Number(sel.value) || 0;
          runSimulation();
        });
      });

      box.querySelectorAll(".unit-rotation").forEach((sel) => {
        sel.addEventListener("change", () => {
          const slot = Number(sel.dataset.slot);
          state.team[slot].rotation = sel.value;
          runSimulation();
        });
      });

      box.querySelectorAll(".unit-target").forEach((sel) => {
        sel.addEventListener("change", () => {
          const slot = Number(sel.dataset.slot);
          state.team[slot].targetSlot = Number(sel.value) || 0;
          runSimulation();
        });
      });

      box.querySelectorAll(".unit-num").forEach((inp) => {
        inp.addEventListener("input", () => {
          const slot = Number(inp.dataset.slot);
          const key = inp.dataset.key;
          const value = parseFloat(inp.value) || 0;
          state.team[slot][key] = value;
          if (state.team[slot].id === "1511") {
            if (key === "baseSpd") state.config.aeonAhaBaseSpd = value;
            if (key === "lcBaseSpd") state.config.aeonAhaLcBaseSpd = value;
          }
          runSimulation();
        });
      });

      box.querySelectorAll(".unit-eq").forEach((chk) => {
        chk.addEventListener("change", () => {
          const slot = Number(chk.dataset.slot);
          const eqKey = chk.dataset.eq;
          state.team[slot].equipment = state.team[slot].equipment || {};
          state.team[slot].equipment[eqKey] = chk.checked;
          runSimulation();
        });
      });
    }

    async function runThreshold() {
      const box = root.querySelector("#aha-threshold-box");
      if (!box) return;
      try {
        const res = await callAction("threshold", state.threshold);
        state.thresholdResult = res;
        box.innerHTML = `
          <div class="aha-kv">
            <span>达成排轴所需最低实战速度：</span>
            <span class="val-big" style="color:#38bdf8;">${fmtNum(res.requiredSpeed, 2)}</span>
          </div>
          <div class="aha-formula-code">${esc(res.formula)}</div>
          <div style="font-size:11.5px;color:#94a3b8;">${esc(res.text)}（无拉条首轮2动 133.34 速；翁瓦克、或欢愉度达标时的神的瞬息欢愉 40% 拉条首轮2动 106.67 速；风套1大首轮3动 183.34 速）</div>
        `;
      } catch (err) {
        box.innerHTML = `<div style="color:#f87171;font-size:12px;">计算失败：${esc(err.message)}</div>`;
      }
    }

    async function runSimulation() {
      const payload = {
        ...state.config,
        team: state.team,
      };
      try {
        const res = await callAction("simulate", payload);
        state.simResult = res;
        const container = root.querySelector("#aha-body-container");
        if (!container) return;
        renderAhaSummary(container, res);
        renderUnitMetrics(container, res);
        renderTimeline(container, res);
      } catch (err) {
        const box = root.querySelector("#aha-summary-box");
        if (box) {
          box.innerHTML = `<div style="color:#f87171;font-size:12px;">模拟报错：${esc(err.message)}</div>`;
        }
      }
    }

    function renderAhaSummary(container, res) {
      const box = container.querySelector("#aha-summary-box");
      if (!box) return;
      const aha = res.aha || {};
      const units = res.units || [];
      const timeline = res.timeline || [];
      const maxAV = Number(res.maxAV ?? state.config.maxAV ?? 0);
      const speedChanged = Math.abs((aha.finalSpeed || 0) - (aha.speed || 0)) > 0.05;

      const countAhaAt = (limit) =>
        timeline.filter(
          (ev) => (ev.type === "aha" || ev.type === "aha_extra") && Number(ev.av) <= Number(limit) + 1e-6
        ).length;

      const node150 = countAhaAt(Math.min(150, maxAV));
      const node250 = maxAV >= 250 ? countAhaAt(250) : null;
      const node300 = maxAV >= 300 ? countAhaAt(300) : countAhaAt(maxAV);
      const node300Label = maxAV >= 300 ? "绝境 (300 AV)" : `上限 (${fmtNum(maxAV, 0)} AV)`;

      const rankBits = (aha.ranks || []).length
        ? aha.ranks.map((r) => `${fmtNum(r.speed, 1)}/${r.divisor}`).join(" + ")
        : "无欢愉队友";
      const flatBonus = Math.abs(Number(aha.flatBonus) || 0) > 0.001 ? ` + ${fmtNum(aha.flatBonus, 1)}` : "";
      const pct = Number(aha.pct) || 0;
      const formula =
        `终局加权：基础 ${fmtNum(aha.base, 1)} + ${rankBits}${flatBonus} = ${fmtNum(aha.raw, 2)}` +
        (pct ? ` × (1+${fmtNum(pct, 0)}%) = ${fmtNum(aha.finalSpeed, 2)}` : "");

      const rankHtml = (aha.ranks || []).length
        ? aha.ranks
            .map(
              (r) =>
                `<div>第${r.rank}快 <b>${esc(r.name)}</b>：${fmtNum(r.speed, 1)} / ${r.divisor} = <span style="color:#f472b6;font-weight:700;">+${fmtNum(r.add, 2)}</span></div>`
            )
            .join("")
        : `<div>未勾选任何欢愉角色，【阿哈时刻】仅保留底速 ${fmtNum(aha.base, 1)}。</div>`;

      const unitChips = units
        .map(
          (u) =>
            `<span class="aha-result-chip">${esc(u.name)} 大招 <b>${u.ultCount || 0}</b></span>`
        )
        .join("");
      const extraTurns = units.reduce((sum, u) => sum + (Number(u.extraTurnCount) || 0), 0);

      box.innerHTML = `
        <div class="aha-result-main">
          <div class="aha-result-stat is-primary">
            <span class="k">阿哈有效速度（开局）</span>
            <span class="v">${fmtNum(aha.speed, 2)}</span>
            <span class="sub">${speedChanged ? `终局 ${fmtNum(aha.finalSpeed, 2)}` : "全程不变"}</span>
          </div>
          <div class="aha-result-stat">
            <span class="k">单次【阿哈时刻】间隔</span>
            <span class="v mid">${fmtNum(aha.singleAV, 2)} AV</span>
            <span class="sub">${speedChanged ? `终局 ${fmtNum(aha.singleFinalAV, 2)} AV` : "按开局速度"}</span>
          </div>
          <div class="aha-node-grid">
            <div class="aha-node-cell">
              <div class="k">0T (150 AV)</div>
              <div class="v">${node150} 次</div>
            </div>
            <div class="aha-node-cell">
              <div class="k">1T (250 AV)</div>
              <div class="v">${node250 == null ? "—" : `${node250} 次`}</div>
            </div>
            <div class="aha-node-cell">
              <div class="k">${node300Label}</div>
              <div class="v" style="color:#f472b6;">${node300} 次</div>
            </div>
            <div class="aha-node-cell">
              <div class="k">模拟上限</div>
              <div class="v" style="color:#38bdf8;">${fmtNum(maxAV, 0)} AV</div>
            </div>
          </div>
        </div>

        <div class="aha-result-units">
          <span class="aha-result-chip is-aha">阿哈时刻 <b>${aha.triggerCount || 0}</b></span>
          <span class="aha-result-chip is-aha">阿哈额外回合 <b>${aha.extraTriggerCount || 0}</b></span>
          <span class="aha-result-chip">角色额外回合 <b>${extraTurns}</b></span>
          ${unitChips}
        </div>

        <div class="aha-formula-code">${esc(formula)}</div>
        <details class="aha-formula-details">
          <summary>速度构成明细</summary>
          <div class="aha-rank-list">${rankHtml}</div>
        </details>
      `;
    }

    function renderUnitMetrics(container, res) {
      (res.units || []).forEach((u, idx) => {
        const el = container.querySelector(`#unit-metrics-${idx}`);
        if (!el) return;
        const spdChanged = Math.abs((u.finalSpd || 0) - (u.initialSpd || 0)) > 0.05;
        const spdText = spdChanged
          ? `${fmtNum(u.initialSpd, 1)} → ${fmtNum(u.finalSpd, 1)}`
          : fmtNum(u.initialSpd, 1);

        el.innerHTML = `
          <span class="aha-metric-tag">速度 <b>${spdText}</b></span>
          <span class="aha-metric-tag">有效 ERR <b>${errText(u)}</b></span>
        `;
      });
    }

    function renderTimeline(container, res) {
      const listEl = container.querySelector("#aha-timeline-list");
      const subEl = container.querySelector("#aha-timeline-sub");
      if (!listEl) return;

      const allEvents = res.timeline || [];
      const textOf = (ev) =>
        `${ev.name || ""} ${ev.label || ""} ${(ev.details || []).join(" ")}`;

      const filtered = allEvents.filter((ev) => {
        if (state.filterType === "all") return true;
        if (state.filterType === "core") {
          return ["ultimate", "aha", "aha_extra", "extra_turn"].includes(ev.type);
        }
        if (state.filterType === "aha") {
          return ev.kind === "aha" || ev.type === "aha" || ev.type === "aha_extra";
        }
        if (state.filterType === "extra") {
          return ev.extra || ev.type === "extra_turn" || ev.type === "aha_extra";
        }
        if (state.filterType === "ultimate") return ev.type === "ultimate";
        if (state.filterType === "elation") return ev.type === "elation_skill";
        if (state.filterType === "pearl") {
          return /真珠|美学底本|艺术壁垒|鉴映灵魂的底色/.test(textOf(ev));
        }
        if (state.filterType === "aeon") {
          return /星神|阿哈|愿力|宇宙笑点大爆炸|欢愉令使|欢愉万相|盒中蕴藏的世界/.test(textOf(ev));
        }
        if (state.filterType === "aventurine") {
          return /砂金|戏浪|凌越飓浪|举杯|All in|纵享惊涛|三赌牌局|旧梦淘金|盲注/.test(textOf(ev));
        }
        return true;
      });

      if (subEl) {
        subEl.textContent = `在 ${fmtNum(res.maxAV, 0)} AV 内共记录 ${allEvents.length} 条事件（当前筛选显示 ${filtered.length} 条）｜ 累计产出笑点 ${fmtNum(res.summary?.punchlineGranted || 0, 0)}，消耗笑点 ${fmtNum(res.summary?.punchlineConsumed || 0, 0)}`;
      }

      let html = "";
      let lastCycle = -1;
      filtered.forEach((ev) => {
        const cycle = ev.t ?? 0;
        if (cycle !== lastCycle) {
          lastCycle = cycle;
          const limitAV = cycle === 0 ? 150 : 150 + cycle * 100;
          html += `
            <div class="aha-cycle-banner">
              <span>── 第 ${cycle} 轮 (${cycle}T) ──</span>
              <span>轮次边界：${limitAV} AV</span>
            </div>
          `;
        }

        const rowClass =
          ev.kind === "aha" || ev.type === "aha" || ev.type === "aha_extra"
            ? "ev-aha"
            : ev.type === "ultimate"
            ? "ev-ult"
            : ev.extra || ev.type === "extra_turn"
            ? "ev-extra"
            : ev.type === "elation_skill"
            ? "ev-elation"
            : "";

        const typeBadge =
          ev.type === "aha"
            ? "阿哈时刻"
            : ev.type === "aha_extra"
            ? "阿哈额外回合"
            : ev.type === "ultimate"
            ? "终结技"
            : ev.type === "extra_turn"
            ? "额外回合"
            : ev.type === "elation_skill"
            ? "欢愉技"
            : ev.type === "fua"
            ? "追加攻击"
            : ev.type === "skill"
            ? "战技"
            : ev.type === "basic" || ev.type === "enhanced_basic"
            ? "普攻"
            : ev.type === "tech"
            ? "秘技"
            : "机制";

        const detailsHtml = (ev.details || [])
          .map((d) => `<span class="aha-ev-chip">${esc(d)}</span>`)
          .join("");

        const resSnap = ev.res
          ? `<span class="aha-ev-chip" style="color:#f472b6;">笑点:${fmtNum(ev.res.punchline, 0)}</span>`
          : "";

        html += `
          <div class="aha-ev-row ${rowClass}">
            <div class="aha-ev-left">
              <span class="aha-ev-av">${fmtNum(ev.av, 2)} AV</span>
              <span class="aha-ev-type">${esc(typeBadge)}</span>
              <b>${esc(ev.label)}</b>
            </div>
            <div class="aha-ev-details">
              ${detailsHtml}
              ${resSnap}
            </div>
          </div>
        `;
      });

      listEl.innerHTML = html || `<div style="color:#64748b;padding:12px;">当前筛选条件下无事件。</div>`;
    }

    renderShell();
  },

  unmount() {},
};
