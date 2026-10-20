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
    desc: "本预设将绯英开局能量设为 480（试算配置，并非角色固有满能机制），先结算秘技与阿哈额外回合，再在 0 AV 连开两次终结技；之后每次达到 240 即在合法时点开大，每次消耗 240 并保留余能。真珠【美学底本】与星神★阿哈【欢愉令使】均锁定绯英。转移按参演编号判断，与站位无关；只累计实际获得的能量，满能截掉的部分不触发狐狸老师。点击「绯英能量」可核对逐次回能，不模拟敌方行动与受击回能。",
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
        id: "1505", name: "绯英", initialEnergy: 480, elation: true, baseSpd: 104, lcBaseSpd: 0, traceSpd: 5,
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
  return uid !== "1511" && uid !== "1506";
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
          if (localApi && ["catalog", "simulate", "threshold"].includes(action)) return localApi.call(action, payload);
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
      filterType: "actions", // 默认行动序列；可切换关键事件或全部记账事件
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
    let simulationRequest = 0;
    let disposed = false;
    this.unmount = () => { disposed = true; simulationRequest += 1; };
    let library = { presets: {}, teams: {}, characters: [], lightcones: [], relicSets: [] };
    let libraryError = "";
    let selectedTeam = "";
    try { library = await callAction("library"); }
    catch (err) { libraryError = `存档读取失败：${err.message}`; }
    const characters = () => new Map((library.characters || []).map(c => [String(c.id), c]));
    function avatar(id, name, extra = "") {
      const source = characters().get(String(id))?.icon;
      const url = source && (/^(\/|data:)/.test(source) || window.GT_STANDALONE ? source : `/api/asset?url=${encodeURIComponent(source)}`);
      return `<span class="aha-avatar ${extra}" aria-label="${esc(name)}"><span>${esc(Array.from(name || "🎭")[0])}</span>${url ? `<img src="${esc(url)}" alt="" loading="lazy" onerror="this.remove()">` : ""}</span>`;
    }

    // 配速页与完整模拟器的速度公式不同；以原 plan 的 S0 校准固定值，
    // 装备仍由模拟器在真实事件时点触发，不把累计拉条当成开局拉条。
    function unitFromBuild(cid, resolved, slot) {
      const { entry, result } = resolved;
      const cfg = entry.config, spd = result.speed, spec = rosterById[cid];
      const lc = (library.lightcones || []).find(x => String(x.id) === String(cfg.lightconeId));
      const coneName = lc?.name || "";
      const sets = (library.relicSets || []).filter(x => [cfg.relic?.fourPieceId, ...(cfg.relic?.ornamentIds || [])].map(String).includes(String(x.id)));
      const hasSet = name => sets.some(x => x.name === name);
      const equipment = Object.fromEntries(RELIC_OPTIONS.map(x => [x.key, false]));
      equipment.vonwacq = hasSet("生命的翁瓦克");
      equipment.godJoy = hasSet("神的瞬息欢愉");
      equipment.windSet4 = hasSet("晨昏交界的翔鹰");
      equipment.danceS5 = coneName === "舞！舞！舞！" && Number(cfg.superimpose) === 5;
      const known = LIGHT_CONE_OPTIONS[cid];
      if (known) equipment[known.key] = Number(cfg.superimpose || 1) === 1 && coneName.includes(known.label.match(/《(.+)》/)?.[1] || known.label);
      const baseSpd = Number(spec.baseSpd), traceSpd = Number(spec.traceSpd || 0);
      const lcBaseSpd = cid === "1511" && equipment.hasSigLc ? Number(spec.lcBaseSpd || 0) : 0;
      const pct = Number(spd.pct || 0);
      const unit = {
        id: cid, name: spec.name, elation: spec.elation, baseSpd, traceSpd, lcBaseSpd,
        permPct: pct - (equipment.godJoy ? 6 : 0),
        permFlat: Number(spd.final) - (baseSpd + lcBaseSpd) * (1 + pct / 100) - traceSpd,
        err: Number(cfg.aha?.err || 0), eidolon: cfg.eidolon || 0,
        initialEnergy: cfg.aha?.initialEnergy ?? "", rotation: cfg.aha?.rotation || spec.rotation || "auto",
        initAdv: Number(cfg.advance?.custom || 0), targetSlot: slot === 0 ? 1 : 0, equipment,
        sourceBuild: {
          characterId: cid, config: structuredClone(cfg),
          name: entry.name, savedAt: entry.savedAt, lightcone: coneName, sets: sets.map(x => x.name), speed: spd.final,
          note: coneName && !equipment.danceS5 && !(known && equipment[known.key])
            ? "此光锥的动态特效或叠影档位尚未支持；仅导入未加速速度，请核对充能与拉条。"
            : "动态特效按本模拟器结算；专武仅支持叠1，舞舞舞仅支持叠5。",
        },
      };
      return unit;
    }

    function notice(message, error = false) {
      const el = root.querySelector("#aha-library-note");
      if (el) { el.textContent = message; el.classList.toggle("is-error", error); }
    }

    async function refreshLibrary(container) {
      library = await callAction("library");
      if (disposed) return;
      libraryError = "";
      renderLibrary(container);
      renderTeamCards(container);
      if (state.simResult) renderUnitMetrics(container, state.simResult);
    }

    function renderLibrary(container) {
      const box = container.querySelector("#aha-library");
      if (!box) return;
      box.innerHTML = `
        <div class="aha-card-head"><h3>我的队伍</h3><button class="ghost small" id="aha-refresh-library">刷新存档</button></div>
        <div class="aha-team-preview" id="aha-team-preview"></div>
        <div class="aha-save-row"><select class="aha-select" id="aha-saved-team" aria-label="已保存队伍"><option value="">选择已保存的队伍</option>${Object.entries(library.teams || {}).map(([id, t]) => `<option value="${esc(id)}" ${id === selectedTeam ? "selected" : ""}>${esc(t.name)}</option>`).join("")}</select><button class="ghost small" id="aha-load-team">加载</button></div>
        <input class="aha-input" id="aha-team-name" aria-label="队伍名称" maxlength="80" placeholder="给队伍起个名字" value="${esc(library.teams?.[selectedTeam]?.name || "")}">
        <div class="aha-save-row"><button class="btn small" id="aha-save-team">另存队伍</button><button class="ghost small" id="aha-overwrite-team" ${selectedTeam ? "" : "disabled"}>覆盖</button><button class="ghost small" id="aha-delete-team" ${selectedTeam ? "" : "disabled"}>删除</button></div>
        <p class="aha-library-note ${libraryError ? "is-error" : ""}" id="aha-library-note" role="status">${esc(libraryError || "角色配装来自「配速查询」；队伍存档保留四人参数与全局设置。")}</p>
        <a class="ghost small" id="aha-manage-builds" href="#/honkai-star-rail/speed-plan">管理角色配装 ↗</a>`;
      renderTeamPreview(container);
      if (window.GT_STANDALONE) box.querySelector("#aha-manage-builds").onclick = event => {
        event.preventDefault(); document.querySelector('[data-view="view"]')?.click();
      };
      box.querySelector("#aha-refresh-library").onclick = async () => {
        try { await refreshLibrary(container); notice("存档已刷新，当前队伍参数保持不变。"); }
        catch (err) { notice(err.message, true); }
      };
      box.querySelector("#aha-saved-team").onchange = event => { selectedTeam = event.target.value; renderLibrary(container); };
      box.querySelector("#aha-load-team").onclick = () => {
        const saved = library.teams?.[selectedTeam];
        if (!saved) return notice("请先选择队伍存档。", true);
        state.team = structuredClone(saved.team); state.config = structuredClone(saved.config);
        state.presetKey = ""; mountSimulatorView(container);
      };
      const save = async overwrite => {
        try {
          const result = await callAction("save_team", { id: overwrite ? selectedTeam : "", name: box.querySelector("#aha-team-name").value, team: structuredClone(state.team), config: structuredClone(state.config) });
          if (disposed) return;
          selectedTeam = result.id; library.teams = result.teams; renderLibrary(container); notice("队伍已保存。");
        } catch (err) { notice(err.message, true); }
      };
      box.querySelector("#aha-save-team").onclick = () => save(false);
      box.querySelector("#aha-overwrite-team").onclick = () => save(true);
      box.querySelector("#aha-delete-team").onclick = async () => {
        if (!confirm("删除所选队伍存档？当前队伍和角色配装会保留。")) return;
        try { const result = await callAction("delete_team", { id: selectedTeam }); library.teams = result.teams; selectedTeam = ""; renderLibrary(container); notice("队伍存档已删除。"); }
        catch (err) { notice(err.message, true); }
      };
    }

    function renderTeamPreview(container) {
      const preview = container.querySelector("#aha-team-preview");
      if (!preview) return;
      preview.innerHTML = state.team.map((u, i) => `<button type="button" data-jump-slot="${i}" title="${i + 1}号位 ${esc(u.name)}">${avatar(u.id, u.name)}<span>${esc(u.name)}</span></button>`).join("");
      preview.querySelectorAll("[data-jump-slot]").forEach(button => {
        button.onclick = () => container.querySelector(`#aha-unit-${button.dataset.jumpSlot}`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
      });
    }

    function renderShell() {
      root.innerHTML = `
        <div class="aha-sim-wrap">
          <div class="aha-topbar">
            <div class="aha-title-block">
              <h2>🎭 欢愉队配速与【阿哈时刻】排轴模拟器</h2>
              <p>选取角色存档组成队伍，按真实模拟事件查看行动顺序与回能。</p>
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
        ["actions", "行动顺序"],
        ["core", "关键事件"],
        ["all", "显示全部行动"],
        ["ultimate", "终结技"],
        ["feiying", "绯英能量"],
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
              <p class="aha-advanced-note" id="aha-model-scope">能开即开（开局秘技及额外回合先结算，期间不能插大）；标准能量默认半能开局。升格仅在星神★阿哈开大后的【欢愉万相】状态期间生效，阿哈时刻不触发升格。绯英能量上限 480，每次终结技消耗 240 并保留剩余能量，合法时点立即开大，不等待满能或蓄满溢出。按 nanoka 4.6.53 的参演编号处理欢愉技与绯英转移，不按站位。暂不模拟敌方行动、受击/击杀回能，真实战斗时序仍需实测校准。</p>

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

      // 沿用原有表单和事件绑定，只重组信息区域。
      const left = container.querySelector(".aha-col-left");
      const right = container.querySelector(".aha-col:not(.aha-col-left)");
      const teamCard = container.querySelector("#aha-team-list").closest(".aha-card");
      const globalCard = left.querySelector(".aha-card");
      const globals = document.createElement("details");
      globals.className = "aha-global-details";
      globals.innerHTML = "<summary>全局机制与模拟范围</summary>";
      globals.append(globalCard);
      const libraryCard = document.createElement("div");
      libraryCard.className = "aha-card"; libraryCard.id = "aha-library";
      const presets = document.createElement("details");
      presets.className = "aha-preset-details aha-example-teams";
      presets.innerHTML = "<summary>示例阵容与机制说明</summary>";
      presets.append(container.querySelector(".aha-preset-bar"), container.querySelector(".aha-preset-details"));
      left.replaceChildren(libraryCard, presets, teamCard, globals);
      right.prepend(container.querySelector("#aha-summary-box"));
      renderLibrary(container);

      // 绑定预设切换
      container.querySelectorAll(".aha-preset-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          const key = btn.dataset.preset;
          if (!TEAM_PRESETS[key]) return;
          state.presetKey = key;
          selectedTeam = "";
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
          const eidolonChoices = EIDOLON_CHOICES[unit.id]
            ? [...new Set([...EIDOLON_CHOICES[unit.id], Number(unit.eidolon || 0)])].sort((a, b) => a - b)
            : null;
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
            <div class="aha-unit-card ${unit.elation ? "is-elation" : ""}" data-slot="${idx}" id="aha-unit-${idx}">
              <div class="aha-unit-top">
                <div class="aha-unit-identity">
                  ${avatar(unit.id, unit.name)}
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

              <div class="aha-build-picker">
                <select class="aha-select unit-build" data-slot="${idx}" aria-label="${idx + 1}号位角色存档">
                  <option value="">从角色配装存档选择…</option>
                  ${Object.entries(library.presets || {}).map(([cid, saved]) => `<option value="${esc(cid)}" ${rosterById[cid] ? "" : "disabled"}>${esc(saved.name)}${rosterById[cid] ? "" : "（尚未支持机制）"}</option>`).join("")}
                </select>
                <button class="ghost small unit-apply-build" data-slot="${idx}">读取</button>
              </div>
              ${unit.sourceBuild ? `<p class="aha-build-source">已读取 ${esc(unit.sourceBuild.name)} · ${esc(unit.sourceBuild.lightcone || "无光锥")} · ${esc(unit.sourceBuild.sets.join(" / ") || "无套装")}<br>存档 S0 ${fmtNum(unit.sourceBuild.speed)} · ${esc(unit.sourceBuild.savedAt || "")}；下方参数可继续调整<br>${esc(unit.sourceBuild.note || "")}</p>` : ""}
              <details class="aha-loadout-details"><summary>光锥与遗器特效</summary>
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
              </details>

              <details class="aha-advanced">
                <summary>高级（星魂 / 出招 / 开局能量 / 目标 / 速度明细）</summary>
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
                    <input type="number" class="aha-input unit-num" data-slot="${idx}" data-key="permFlat" value="${unit.permFlat || 0}" step="0.01">
                  </div>
                  <div class="aha-field">
                    <label>开局拉条(%)</label>
                    <input type="number" class="aha-input unit-num" data-slot="${idx}" data-key="initAdv" value="${unit.initAdv || 0}" step="5">
                  </div>
                  <div class="aha-field">
                    <label>开局${unit.id === "1511" ? "愿力" : unit.id === "1506" ? "隐藏分" : "能量"}（留空用默认值）</label>
                    <input type="number" class="aha-input unit-num" data-slot="${idx}" data-key="initialEnergy" value="${unit.initialEnergy ?? ""}" min="0" step="1">
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

      renderTeamPreview(container);

      box.querySelectorAll(".unit-apply-build").forEach(button => {
        button.onclick = async () => {
          const slot = Number(button.dataset.slot);
          const cid = box.querySelector(`.unit-build[data-slot="${slot}"]`).value;
          if (!cid) return notice("请选择一个已保存的角色配装。", true);
          button.disabled = true;
          // 若等待期间换了队伍，丢弃旧读取结果。
          const originalTeam = state.team;
          try {
            const resolved = await callAction("resolve_build", { characterId: cid });
            if (disposed || originalTeam !== state.team || !button.isConnected) return;
            state.team[slot] = unitFromBuild(cid, resolved, slot);
            if (cid === "1511") {
              state.config.aeonAhaBaseSpd = state.team[slot].baseSpd;
              state.config.aeonAhaLcBaseSpd = state.team[slot].lcBaseSpd;
            }
            renderTeamCards(container); runSimulation();
            notice("已读取未加速速度 S0、星魂及可识别装备。动态效果沿用本模拟器；非叠5舞舞舞等未支持效果需手动核对。累计拉条不会作为开局拉条导入。");
          } catch (err) { notice(err.message, true); }
          finally { button.disabled = false; }
        };
      });

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
          const value = key === "initialEnergy" ? inp.value : parseFloat(inp.value) || 0;
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
      const request = ++simulationRequest;
      const payload = {
        ...state.config,
        team: structuredClone(state.team),
      };
      try {
        const res = await callAction("simulate", payload);
        if (disposed || request !== simulationRequest) return;
        state.simResult = res;
        const container = root.querySelector("#aha-body-container");
        if (!container) return;
        renderAhaSummary(container, res);
        renderUnitMetrics(container, res);
        renderTimeline(container, res);
      } catch (err) {
        if (request !== simulationRequest) return;
        state.simResult = null;
        const box = root.querySelector("#aha-summary-box");
        if (box) {
          box.innerHTML = `<div style="color:#f87171;font-size:12px;">模拟报错：${esc(err.message)}</div>`;
        }
        const timeline = root.querySelector("#aha-timeline-list");
        if (timeline) timeline.textContent = "模拟失败，请修正参数后重试；不显示上一次结果。";
        const subtitle = root.querySelector("#aha-timeline-sub");
        if (subtitle) subtitle.textContent = "";
        root.querySelectorAll(".aha-unit-metrics").forEach((el) => { el.textContent = ""; });
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
        ${(res.warnings || []).map((warning) => `<p class="aha-advanced-note" role="alert">${esc(warning)}</p>`).join("")}
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

        <details class="aha-formula-details">
          <summary>速度构成明细</summary>
          <div class="aha-formula-code">${esc(formula)}</div>
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
        if (state.filterType === "actions") return ["tech", "basic", "enhanced_basic", "skill", "ultimate", "aha", "aha_extra", "extra_turn", "elation_skill", "fua"].includes(ev.type);
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
        if (state.filterType === "feiying") {
          return ev.slot != null && state.team[ev.slot]?.id === "1505";
        }
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
      const eventIndices = new Map(allEvents.map((ev, index) => [ev, index + 1]));
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
            : ev.type === "energy_gain"
            ? "回能"
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
          <details class="aha-ev-row ${rowClass}" data-event-index="${eventIndices.get(ev)}" data-av="${esc(ev.av)}">
            <summary class="aha-event-summary" title="点击展开或收起详细数据">
            <span class="aha-event-order" title="原始模拟事件序号">#${eventIndices.get(ev)}</span>
            ${ev.slot != null ? avatar(state.team[ev.slot]?.id, ev.name) : avatar(null, "🎭", "is-system")}
            <div class="aha-ev-left">
              <span class="aha-ev-av">${fmtNum(ev.av, 2)} AV</span>
              <span class="aha-ev-type">${esc(typeBadge)}</span>
              <span class="aha-event-name">${esc(ev.name)}</span>
              <b class="aha-event-label">${esc(ev.label)}</b>
            </div>
            <span class="aha-event-expand" aria-hidden="true">⌄</span>
            </summary>
            <div class="aha-ev-details">
              ${detailsHtml}
              ${resSnap}
            </div>
          </details>
        `;
      });

      listEl.innerHTML = html || `<div style="color:#64748b;padding:12px;">当前筛选条件下无事件。</div>`;
    }

    renderShell();
  },

  unmount() {},
};
