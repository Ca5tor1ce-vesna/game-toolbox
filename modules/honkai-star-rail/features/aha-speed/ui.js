/* 【阿哈时刻】与欢愉队配速排轴模拟 —— 前端界面
 *
 * 同时支持两种视图模式：
 *   1. 「🎭 欢愉队完整机制排轴模拟」（默认）：调用后端 `simulate` / `threshold` 引擎，
 *      完整模拟真珠【美学底本】拉人（10%/15%/30% + 4欢愉额外回合）与【艺术壁垒】90点固定回能、
 *      星神★阿哈【愿力】5大来源与终结技拉条【阿哈时刻】20%（及E6首大100%/额外回合）与【欢愉万相】升格、
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
    label: "🌟 四欢愉旗舰队（星神★阿哈 + 砂金•戏浪 + 真珠 + 爻光）",
    desc: "四欢愉满编：真珠【美学底本】锁定2号位砂金•戏浪，开大直接拉条30%并赋予1个额外回合（+60笑点），砂金•戏浪开大触发真珠【艺术壁垒】固定回能90点；星神★阿哈【欢愉令使】锁定砂金•戏浪，满8愿力开大拉条【阿哈时刻】20%并开启3回合【欢愉万相】；砂金•戏浪开大自身提速30%（4回合）并靠队友攻击叠满10点【热意】在回合外施放欢愉技《举杯！敬炽烈一夏》。",
    config: {
      maxAV: 300,
      useAeonAha: true,
      useTech: true,
      trace3Advance: true,
      ultAdvanceAha: 20,
      e1Wishpower: 5,
      e6FirstUltMode: "extra40",
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
    label: "🎲 三赌牌局双欢愉（砂金•戏浪 + 星神★阿哈 + 星期日 + 砂金·存护）",
    desc: "双欢愉三赌牌局体系：队内仅「砂金•戏浪 + 星神★阿哈」2名欢愉角色。星神★阿哈开大进入【欢愉万相】升格后，激活砂金•戏浪【欢愉万相★三赌牌局】使我方全体速度提高15%（可调25%），同时激活行迹【纵享惊涛】使队友每次攻击让【阿哈时刻】速度+25！星期日100%拉条砂金•戏浪，存护砂金套盾与7段追击触发星神★阿哈行迹2愿力+1。",
    config: {
      maxAV: 300,
      useAeonAha: true,
      useTech: true,
      trace3Advance: true,
      ultAdvanceAha: 20,
      e1Wishpower: 5,
      e6FirstUltMode: "extra40",
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
    label: "🌸 绯英四欢愉爆发队（绯英 + 星神★阿哈 + 真珠 + 爻光）",
    desc: "真珠【美学底本】与星神★阿哈【欢愉令使】双锁定1号位绯英：真珠开大拉条绯英30%并给1个额外回合，绯英获得好活当赏同步转化能量、每累计240能量触发【狐狸老师】追击，绯英满480能量开大时立即触发真珠【艺术壁垒】恢复90点固定能量！",
    config: {
      maxAV: 300,
      useAeonAha: true,
      useTech: true,
      trace3Advance: true,
      ultAdvanceAha: 20,
      e1Wishpower: 5,
      e6FirstUltMode: "extra40",
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
    label: "🎮 银狼火花高频队（银狼LV.999 + 火花 + 爻光 + 真珠）",
    desc: "无星神★阿哈（阿哈时刻底速80）：银狼LV.999同步全队笑点转化为【隐藏分】，满60点开大100%自拉条进入【无敌玩家】三连强化普攻；火花压过阿哈时刻产笑点（2魂阿哈时刻结束后获得额外回合）；真珠锁定银狼拉条30%+额外回合+艺术壁垒回能90点。",
    config: {
      maxAV: 300,
      useAeonAha: false,
      useTech: true,
      trace3Advance: false,
      ultAdvanceAha: 20,
      e1Wishpower: 5,
      e6FirstUltMode: "extra40",
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
      viewMode: "simulator", // "simulator" | "original"
      presetKey: "aha_quad",
      filterType: "all", // "all" | "aha" | "pull_extra" | "ult_elation"
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
              <h2>🎭 欢愉队配速与【阿哈时刻】完整排轴模拟器</h2>
              <p>实战速度 = (基础白值 + 光锥白值) × (1 + 速度%) + 固定速度 + 行迹速度 ｜ 阿哈速度 = 底速 + V1/5 + V2/10 + V3/20 + V4/40</p>
            </div>
            <div class="aha-mode-switch">
              <button type="button" class="aha-mode-btn ${state.viewMode === "simulator" ? "is-active" : ""}" data-mode="simulator">
                🎭 完整机制排轴模拟
              </button>
              <button type="button" class="aha-mode-btn ${state.viewMode === "original" ? "is-active" : ""}" data-mode="original">
                📄 原版静态工具 (original.html)
              </button>
            </div>
          </div>
          <div id="aha-body-container"></div>
        </div>
      `;

      root.querySelectorAll(".aha-mode-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          state.viewMode = btn.dataset.mode;
          renderShell();
        });
      });

      const body = root.querySelector("#aha-body-container");
      if (state.viewMode === "original") {
        mountOriginalIframe(body);
      } else {
        mountSimulatorView(body);
      }
    }

    async function mountOriginalIframe(container) {
      let html;
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

      const vendorUrl = `${base}/vendor/tailwind.js`;
      if (await exists(vendorUrl)) {
        const absolute = new URL(vendorUrl, location.origin).href;
        html = html.replace('src="https://cdn.tailwindcss.com"', `src="${absolute}"`);
      }

      container.innerHTML = `<iframe class="aha-original-frame" title="【阿哈时刻】配速（原版工具）"></iframe>`;
      const frame = container.querySelector("iframe");
      frame.setAttribute("srcdoc", html);
    }

    function mountSimulatorView(container) {
      const presetButtons = Object.entries(TEAM_PRESETS)
        .map(
          ([key, item]) =>
            `<button type="button" class="aha-preset-btn ${state.presetKey === key ? "is-active" : ""}" data-preset="${key}">${esc(item.label)}</button>`
        )
        .join("");

      const presetDesc = TEAM_PRESETS[state.presetKey]?.desc || "";

      container.innerHTML = `
        <div class="aha-preset-bar">
          <span class="aha-preset-label">阵容预设：</span>
          ${presetButtons}
          <div class="aha-preset-desc" id="aha-preset-desc">${esc(presetDesc)}</div>
        </div>

        <div class="aha-main-grid">
          <div class="aha-col">
            <div class="aha-card">
              <div class="aha-card-head">
                <h3>🎭 【阿哈时刻】与核心机制参数</h3>
                <span class="aha-pill">动态变速 & 拉条联动</span>
              </div>

              <div class="aha-switch-list">
                <label class="aha-switch-row">
                  <span>启用【阿哈时刻在】（底速 80 → 星神★阿哈基础速度）</span>
                  <input type="checkbox" id="cfg-useAeonAha" ${state.config.useAeonAha ? "checked" : ""}>
                </label>
                <label class="aha-switch-row">
                  <span>秘技进战（阿哈额外回合 / 真珠深度学习2层 / 砂金热意+2 / 爻光结界）</span>
                  <input type="checkbox" id="cfg-useTech" ${state.config.useTech ? "checked" : ""}>
                </label>
                <label class="aha-switch-row">
                  <span>星神★阿哈行迹3【盒中蕴藏的世界】（进战自身拉条 30%）</span>
                  <input type="checkbox" id="cfg-trace3Advance" ${state.config.trace3Advance ? "checked" : ""}>
                </label>
              </div>

              <div class="aha-form-grid">
                <div class="aha-field">
                  <label>星神★阿哈本体基础速度</label>
                  <input type="number" class="aha-input" id="cfg-aeonAhaBaseSpd" value="${state.config.aeonAhaBaseSpd}" step="1">
                  <small>未启用升格时底速固定为 80</small>
                </div>
                <div class="aha-field">
                  <label>阿哈专武基础速度白字</label>
                  <input type="number" class="aha-input" id="cfg-aeonAhaLcBaseSpd" value="${state.config.aeonAhaLcBaseSpd}" step="2">
                  <small>《当第一声「阿哈」响起》+12~+20</small>
                </div>
                <div class="aha-field">
                  <label>星神★阿哈大招拉条阿哈 (%)</label>
                  <input type="number" class="aha-input" id="cfg-ultAdvanceAha" value="${state.config.ultAdvanceAha}" step="5">
                  <small>施放终结技使【阿哈时刻】行动提前%</small>
                </div>
                <div class="aha-field">
                  <label>星神★阿哈 6魂首大模式</label>
                  <select class="aha-select" id="cfg-e6FirstUltMode">
                    <option value="extra40" ${state.config.e6FirstUltMode === "extra40" ? "selected" : ""}>额外回合(计40笑点)+后续拉20%</option>
                    <option value="advance100" ${state.config.e6FirstUltMode === "advance100" ? "selected" : ""}>首大拉条100%并+100笑点</option>
                  </select>
                  <small>仅在星神★阿哈星魂 = E6 时生效</small>
                </div>
                <div class="aha-field">
                  <label>砂金•戏浪大招自提速 (%)</label>
                  <input type="number" class="aha-input" id="cfg-ultSpdPct" value="${state.config.ultSpdPct}" step="3">
                  <small>10级 30% / 12级 33.6% / 15级 39%（4回合）</small>
                </div>
                <div class="aha-field">
                  <label>砂金•戏浪【三赌牌局】全队提速 (%)</label>
                  <input type="number" class="aha-input" id="cfg-sanduTeamSpdPct" value="${state.config.sanduTeamSpdPct}" step="5">
                  <small>仅砂金•戏浪+星神阿哈2欢愉且升格时生效</small>
                </div>
                <div class="aha-field">
                  <label>【阿哈时刻】额外速度加成 (%)</label>
                  <input type="number" class="aha-input" id="cfg-ahaSpdPct" value="${state.config.ahaSpdPct}" step="1">
                </div>
                <div class="aha-field">
                  <label>开局拉条【阿哈时刻】 (%)</label>
                  <input type="number" class="aha-input" id="cfg-ahaAdvancePct" value="${state.config.ahaAdvancePct}" step="5">
                </div>
              </div>

              <div class="aha-result-box" id="aha-summary-box"></div>
            </div>

            <div class="aha-card">
              <div class="aha-card-head">
                <h3>🎯 速度阈值反推 (N轮M动)</h3>
              </div>
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
          </div>

          <div class="aha-col">
            <div class="aha-card">
              <div class="aha-card-head">
                <h3>👥 欢愉队 4 人编队与配装参数</h3>
                <div style="display:flex;align-items:center;gap:8px;font-size:12px;">
                  <span>模拟上限 (AV)：</span>
                  <input type="number" class="aha-input" id="cfg-maxAV" value="${state.config.maxAV}" min="100" max="1000" step="50" style="width:82px;text-align:center;">
                </div>
              </div>
              <div class="aha-team-list" id="aha-team-list"></div>
            </div>

            <div class="aha-card">
              <div class="aha-card-head">
                <h3>🔍 核心机制触发追踪看板（真珠拉人 / 星神★阿哈拉条阿哈 / 砂金技能效果）</h3>
                <span class="aha-pill">实时排轴提取</span>
              </div>
              <div class="aha-mech-grid" id="aha-mech-grid"></div>
            </div>

            <div class="aha-card">
              <div class="aha-card-head">
                <div>
                  <h3>⏱️ 行动值与技能事件排轴时间线</h3>
                  <small id="aha-timeline-sub" style="color:var(--muted,#94a3b8);font-size:11.5px;"></small>
                </div>
                <div class="aha-filter-bar">
                  <button type="button" class="aha-filter-btn ${state.filterType === "all" ? "is-active" : ""}" data-filter="all">全部事件</button>
                  <button type="button" class="aha-filter-btn ${state.filterType === "aha" ? "is-active" : ""}" data-filter="aha">仅【阿哈时刻】</button>
                  <button type="button" class="aha-filter-btn ${state.filterType === "pull_extra" ? "is-active" : ""}" data-filter="pull_extra">拉条 / 额外回合</button>
                  <button type="button" class="aha-filter-btn ${state.filterType === "ult_elation" ? "is-active" : ""}" data-filter="ult_elation">终结技 / 欢愉技</button>
                </div>
              </div>
              <div class="aha-count-strip" id="aha-count-strip"></div>
              <div class="aha-timeline-list" id="aha-timeline-list"></div>
            </div>
          </div>
        </div>
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
            const bEl = container.querySelector("#cfg-aeonAhaBaseSpd");
            const lEl = container.querySelector("#cfg-aeonAhaLcBaseSpd");
            if (bEl) bEl.value = state.config.aeonAhaBaseSpd;
            if (lEl) lEl.value = state.config.aeonAhaLcBaseSpd;
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
      bindNum("cfg-aeonAhaBaseSpd", "aeonAhaBaseSpd");
      bindNum("cfg-aeonAhaLcBaseSpd", "aeonAhaLcBaseSpd");
      bindNum("cfg-ultAdvanceAha", "ultAdvanceAha");
      bindNum("cfg-ultSpdPct", "ultSpdPct");
      bindNum("cfg-sanduTeamSpdPct", "sanduTeamSpdPct");
      bindNum("cfg-ahaSpdPct", "ahaSpdPct");
      bindNum("cfg-ahaAdvancePct", "ahaAdvancePct");
      bindNum("cfg-maxAV", "maxAV");

      const e6Sel = container.querySelector("#cfg-e6FirstUltMode");
      if (e6Sel) {
        e6Sel.addEventListener("change", () => {
          state.config.e6FirstUltMode = e6Sel.value;
          runSimulation();
        });
      }

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

      renderTeamCards(container);
      runSimulation();
      runThreshold();
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

          const targetLabel =
            unit.id === "1503"
              ? "【美学底本】目标"
              : unit.id === "1511"
              ? "【欢愉令使】目标"
              : unit.id === "1313" || unit.id === "8009"
              ? "技能指定目标"
              : "指定目标槽位";

          const eq = unit.equipment || {};
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
                  <select class="aha-select unit-eidolon" data-slot="${idx}" style="width:72px;">
                    ${[0, 1, 2, 3, 4, 5, 6]
                      .map((e) => `<option value="${e}" ${Number(unit.eidolon) === e ? "selected" : ""}>E${e}魂</option>`)
                      .join("")}
                  </select>
                  <select class="aha-select unit-rotation" data-slot="${idx}" style="width:110px;">
                    <option value="auto" ${unit.rotation === "auto" ? "selected" : ""}>智能出招</option>
                    <option value="skill" ${unit.rotation === "skill" ? "selected" : ""}>全程战技</option>
                    <option value="basic" ${unit.rotation === "basic" ? "selected" : ""}>全程普攻</option>
                  </select>
                </div>
                <div class="aha-unit-metrics" id="unit-metrics-${idx}"></div>
              </div>

              <div class="aha-unit-inputs">
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
                  <label>充能效率(%)</label>
                  <input type="number" class="aha-input unit-num" data-slot="${idx}" data-key="err" value="${unit.err || 0}" step="0.1">
                </div>
                <div class="aha-field">
                  <label>开局拉条(%)</label>
                  <input type="number" class="aha-input unit-num" data-slot="${idx}" data-key="initAdv" value="${unit.initAdv || 0}" step="5">
                </div>
                <div class="aha-field">
                  <label>${esc(targetLabel)}</label>
                  <select class="aha-select unit-target" data-slot="${idx}">
                    ${targetOptions}
                  </select>
                </div>
              </div>

              <div class="aha-unit-equips">
                <span style="color:var(--muted,#94a3b8);">光锥/遗器排轴特效：</span>
                <label class="aha-equip-chk">
                  <input type="checkbox" class="unit-eq" data-slot="${idx}" data-eq="vonwacq" ${eq.vonwacq ? "checked" : ""}>
                  <span>翁瓦克(≥120速开局拉40%+5%ERR)</span>
                </label>
                <label class="aha-equip-chk">
                  <input type="checkbox" class="unit-eq" data-slot="${idx}" data-eq="godJoy" ${eq.godJoy ? "checked" : ""}>
                  <span>神的瞬息欢愉(速度+6%、开局拉40%)</span>
                </label>
                <label class="aha-equip-chk">
                  <input type="checkbox" class="unit-eq" data-slot="${idx}" data-eq="windSet4" ${eq.windSet4 ? "checked" : ""}>
                  <span>风套4件(开大自拉25%)</span>
                </label>
                <label class="aha-equip-chk">
                  <input type="checkbox" class="unit-eq" data-slot="${idx}" data-eq="danceS5" ${eq.danceS5 ? "checked" : ""}>
                  <span>叠5舞舞舞(开大全队拉24%)</span>
                </label>
                ${
                  unit.id === "1511"
                    ? `<label class="aha-equip-chk">
                        <input type="checkbox" class="unit-eq" data-slot="${idx}" data-eq="hasSigLc" ${eq.hasSigLc ? "checked" : ""}>
                        <span style="color:#f472b6;">阿哈专武(战技+10笑点)</span>
                      </label>`
                    : ""
                }
                ${
                  unit.id === "1513"
                    ? `<label class="aha-equip-chk">
                        <input type="checkbox" class="unit-eq" data-slot="${idx}" data-eq="hasSummerLc" ${eq.hasSummerLc ? "checked" : ""}>
                        <span style="color:#fbbf24;">《向浪花掷下盛夏》(欢愉技+24%速度)</span>
                      </label>`
                    : ""
                }
              </div>
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
          state.team[slot][key] = parseFloat(inp.value) || 0;
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
          <div style="font-size:11.5px;color:#94a3b8;">${esc(res.text)}（无拉条首轮2动 133.34 速；翁瓦克/神的瞬息欢愉 40% 拉条首轮2动 106.67 速；风套1大首轮3动 183.34 速）</div>
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
        renderMechanismHighlights(container, res);
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
      const counts = aha.counts || {};
      const speedChanged = Math.abs((aha.finalSpeed || 0) - (aha.speed || 0)) > 0.05;
      const rankHtml = (aha.ranks || []).length
        ? aha.ranks
            .map(
              (r) =>
                `<div>第${r.rank}快 <b>${esc(r.name)}</b>：${fmtNum(r.speed, 1)} / ${r.divisor} = <span style="color:#f472b6;font-weight:700;">+${fmtNum(r.add, 2)}</span></div>`
            )
            .join("")
        : `<div>未勾选任何欢愉角色，【阿哈时刻】仅保留底速 ${fmtNum(aha.base, 1)}。</div>`;

      box.innerHTML = `
        <div class="aha-kv">
          <span>【阿哈时刻】有效速度（开局 → 终局）：</span>
          <span class="val-big">${fmtNum(aha.speed, 2)}${speedChanged ? ` → ${fmtNum(aha.finalSpeed, 2)}` : ""}</span>
        </div>
        <div class="aha-kv">
          <span>单次【阿哈时刻】间隔：</span>
          <span class="val-mid">${fmtNum(aha.singleAV, 2)} AV${speedChanged ? `（终局 ${fmtNum(aha.singleFinalAV, 2)} AV）` : ""}</span>
        </div>
        <div class="aha-formula-code">${esc(aha.formula || "")}</div>
        <div class="aha-rank-list">${rankHtml}</div>
        <div class="aha-node-grid">
          <div class="aha-node-cell">
            <div class="k">0T (150 AV)</div>
            <div class="v">${counts["150"] ?? 0} 次</div>
          </div>
          <div class="aha-node-cell">
            <div class="k">1T (250 AV)</div>
            <div class="v">${counts["250"] ?? 0} 次</div>
          </div>
          <div class="aha-node-cell">
            <div class="k">绝境 (300 AV)</div>
            <div class="v" style="color:#f472b6;">${counts["300"] ?? 0} 次</div>
          </div>
          <div class="aha-node-cell">
            <div class="k">跑条 / 额外</div>
            <div class="v" style="color:#38bdf8;">${aha.triggerCount || 0} + ${aha.extraTriggerCount || 0}</div>
          </div>
        </div>
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
        const cmpHtml = !u.elation
          ? `<span style="color:#94a3b8;">非欢愉</span>`
          : u.fasterThanAha
          ? `<span style="color:#34d399;">比阿哈快 +${fmtNum(u.deltaVsAha, 1)}</span>`
          : `<span style="color:#fb7185;">比阿哈慢 ${fmtNum(Math.abs(u.deltaVsAha), 1)}</span>`;

        el.innerHTML = `
          <span class="aha-metric-tag">实战速度 <b>${spdText}</b></span>
          <span class="aha-metric-tag">单动 <b>${fmtNum(u.singleAV, 2)} AV</b></span>
          <span class="aha-metric-tag">${cmpHtml}</span>
          <span class="aha-metric-tag">出手 <b>${u.actionCount}</b>（大招 <b>${u.ultCount}</b>${u.extraTurnCount ? ` / 额外 <b>${u.extraTurnCount}</b>` : ""}）</span>
        `;
      });
    }

    function renderMechanismHighlights(container, res) {
      const grid = container.querySelector("#aha-mech-grid");
      if (!grid) return;
      const timeline = res.timeline || [];
      const units = res.units || [];
      const pearlUnit = units.find((u) => u.id === "1503");
      const aeonUnit = units.find((u) => u.id === "1511");
      const avenSpUnit = units.find((u) => u.id === "1513");
      const avenPresUnit = units.find((u) => u.id === "1304");

      // 1. 提取真珠相关事件
      const pearlEvents = timeline.filter(
        (ev) =>
          (ev.name && ev.name.includes("真珠")) ||
          (ev.label &&
            (ev.label.includes("真珠") ||
              ev.label.includes("鉴映灵魂的底色") ||
              ev.label.includes("美学底本") ||
              ev.label.includes("艺术壁垒")))
      );
      const aesteTarget =
        res.resources?.aesteSlot != null ? units[res.resources.aesteSlot]?.name : "未指定";

      // 2. 提取星神★阿哈相关事件
      const aeonEvents = timeline.filter(
        (ev) =>
          (ev.name && ev.name.includes("星神")) ||
          (ev.label &&
            (ev.label.includes("宇宙笑点大爆炸") ||
              ev.label.includes("欢愉令使") ||
              ev.label.includes("愿力") ||
              ev.label.includes("ABRACADABRA") ||
              ev.label.includes("欢愉万相") ||
              ev.label.includes("戏中人的异想国") ||
              ev.label.includes("盒中蕴藏的世界")))
      );
      const lingshiTarget =
        res.resources?.lingshiSlot != null ? units[res.resources.lingshiSlot]?.name : "未指定";

      // 3. 提取砂金（戏浪 + 存护）相关事件
      const avenEvents = timeline.filter(
        (ev) =>
          (ev.name && ev.name.includes("砂金")) ||
          (ev.label &&
            (ev.label.includes("砂金") ||
              ev.label.includes("凌越飓浪之上") ||
              ev.label.includes("举杯") ||
              ev.label.includes("All in") ||
              ev.label.includes("纵享惊涛") ||
              ev.label.includes("三赌牌局") ||
              ev.label.includes("旧梦淘金") ||
              ev.label.includes("盲注")))
      );

      const formatLogs = (list, emptyText) => {
        if (!list.length) {
          return `<div class="aha-mech-item" style="color:#64748b;">${esc(emptyText)}</div>`;
        }
        return list
          .map(
            (ev) => `
              <div class="aha-mech-item">
                <span class="av-tag">[${fmtNum(ev.av, 1)} AV]</span>
                <b>${esc(ev.label)}</b>
                ${
                  ev.details && ev.details.length
                    ? `<div style="color:#94a3b8;margin-top:2px;">→ ${esc(ev.details.join("；"))}</div>`
                    : ""
                }
              </div>
            `
          )
          .join("");
      };

      grid.innerHTML = `
        <div class="aha-mech-box is-pearl">
          <div class="aha-mech-title">
            <span style="color:#38bdf8;">🦪 真珠拉人 & 【艺术壁垒】</span>
            <span style="font-size:11px;color:#94a3b8;">底本：${esc(pearlUnit ? aesteTarget : "未编入")}</span>
          </div>
          <div style="font-size:11px;color:#94a3b8;">
            欢愉人数 1/2/3+ 拉条底本 10%/15%/30%；4欢愉额外给底本 1 个额外回合（+60笑点）；底本开大为真珠固定回能 90 点。
          </div>
          <div class="aha-mech-logs">
            ${formatLogs(pearlEvents, "当前编队未编入真珠，可在上方槽位选择「真珠」体验拉人与额外回合。")}
          </div>
        </div>

        <div class="aha-mech-box is-aeon">
          <div class="aha-mech-title">
            <span style="color:#f472b6;">🎭 星神★阿哈愿力 & 拉条阿哈</span>
            <span style="font-size:11px;color:#94a3b8;">令使：${esc(aeonUnit ? lingshiTarget : "未编入")}</span>
          </div>
          <div style="font-size:11px;color:#94a3b8;">
            满8点【愿力】开大：使【阿哈时刻】行动提前 ${fmtNum(state.config.ultAdvanceAha, 0)}%，开启3回合【欢愉万相】升格（阿哈时刻返还10%笑点）。
          </div>
          <div class="aha-mech-logs">
            ${formatLogs(aeonEvents, "当前编队未编入星神★阿哈，可在上方槽位选择「星神★阿哈」体验拉条阿哈。")}
          </div>
        </div>

        <div class="aha-mech-box is-aven">
          <div class="aha-mech-title">
            <span style="color:#fbbf24;">🎲 砂金技能效果（戏浪 / 存护）</span>
            <span style="font-size:11px;color:#94a3b8;">${
              avenSpUnit && avenPresUnit
                ? "双砂金在场"
                : avenSpUnit
                ? `戏浪终局 ${fmtNum(avenSpUnit.finalSpd, 1)} 速`
                : avenPresUnit
                ? "存护砂金在场"
                : "未编入"
            }</span>
          </div>
          <div style="font-size:11px;color:#94a3b8;">
            砂金•戏浪大招自身提速 +${fmtNum(state.config.ultSpdPct, 0)}%（4回合）；队友攻击叠热意满10点回合外放欢愉技；单欢愉/三赌牌局下阿哈速度+25、全队速度+${fmtNum(state.config.sanduTeamSpdPct, 0)}%。
          </div>
          <div class="aha-mech-logs">
            ${formatLogs(avenEvents, "当前编队未编入砂金•戏浪或砂金(存护)，可在上方槽位选择体验。")}
          </div>
        </div>
      `;
    }

    function renderTimeline(container, res) {
      const strip = container.querySelector("#aha-count-strip");
      const listEl = container.querySelector("#aha-timeline-list");
      const subEl = container.querySelector("#aha-timeline-sub");
      if (!strip || !listEl) return;

      const unitActions = res.summary?.unitActions || {};
      strip.innerHTML = Object.entries(unitActions)
        .map(([name, cnt]) => {
          const isAha = name.includes("阿哈时刻");
          return `
            <div class="aha-count-card ${isAha ? "is-aha" : ""}">
              <div style="font-size:11px;color:${isAha ? "#f472b6" : "#94a3b8"};font-weight:600;">${esc(name)}</div>
              <div style="font-size:15px;font-weight:800;color:${isAha ? "#f472b6" : "#f8fafc"};margin-top:2px;">${cnt} 次</div>
            </div>
          `;
        })
        .join("");

      const allEvents = res.timeline || [];
      const filtered = allEvents.filter((ev) => {
        if (state.filterType === "aha") {
          return ev.kind === "aha" || ev.type === "aha" || ev.type === "aha_extra" || (ev.label && ev.label.includes("阿哈时刻"));
        }
        if (state.filterType === "pull_extra") {
          return (
            ev.extra ||
            ev.type === "extra_turn" ||
            ev.type === "aha_extra" ||
            (ev.details && ev.details.some((d) => d.includes("拉条") || d.includes("额外回合"))) ||
            (ev.label && (ev.label.includes("拉条") || ev.label.includes("额外回合") || ev.label.includes("鉴映灵魂的底色") || ev.label.includes("宇宙笑点大爆炸")))
          );
        }
        if (state.filterType === "ult_elation") {
          return ev.type === "ultimate" || ev.type === "elation_skill" || ev.type === "aha" || ev.type === "aha_extra";
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
