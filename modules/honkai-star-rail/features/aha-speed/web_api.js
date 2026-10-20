/* 【阿哈时刻】配速 —— 浏览器端实现（`modules/honkai-star-rail/features/aha-speed/api.py` 的逐位移植）。
 *
 * 这是一个**经典脚本**：用 <script src> 直接加载会挂到 window.GT_AHA_SPEED_API；
 * 用 node 时走 module.exports，两边共用同一份代码。
 *
 *   const api = window.GT_AHA_SPEED_API.createApi();
 *   api.call("simulate", payload);   // 同步返回，不是 Promise
 *
 * 动作与 Python 的 @api(...) 一一对应：
 *   catalog   —— 角色表 / 装备开关 / 可调参数 / 行动值节点
 *   simulate  —— 4 人小队 + 【阿哈时刻】的行动值排轴
 *   threshold —— N 轮 M 动的速度阈值反推
 *
 * 底层公式（与 Python 端、与排轴数据库一致）
 * ------------------------------------------
 *   current_spd = (base_spd + lc_base_spd) × (1 + (perm_pct + buff_pct) / 100)
 *                 + perm_flat + buff_flat + trace_spd
 *   拉条：rem_dist = max(0, rem_dist − 10000 × aa_pct / 100)；剩余行动值 = rem_dist / spd。
 *   【阿哈时刻】速度 = (底速 + 0.2V1 + 0.1V2 + 0.05V3 + 0.025V4 + aha_flat_bonus)
 *                     × (1 + aha_spd_pct / 100)，V 是欢愉队友速度降序（不足补 0）。
 *   轮次：av ≤ 150 是 0T；150 < av ≤ 250 是 1T；250 < av ≤ 350 是 2T……
 *
 * 移植注意事项（这些地方和 Python 的差异最容易出结果不一致）
 * ----------------------------------------------------------
 *   * 数值比较全部在 IEEE754 double 上做，**不做任何额外 round**；
 *     文本里的数字一律走 fmt()（与 Python 的 fmt() 逐位一致：放大后 half-up 再拼串，
 *     不用 toFixed —— 它和 Python 的 ties-to-even 在 .5 边界上会差一个末位）。
 *   * 排序都要求稳定（Array.prototype.sort 在 ES2019+ 稳定，与 Python sorted 一致）。
 *   * Python 的 `or` 兜底链在 JS 用 `||` 时注意 0/"" 两边语义一致（这里全是字符串或布尔）。
 *   * Python `int(x)` 截断向零，JS 用 Math.trunc。
 *   * 数字串只认十进制（与 Python 同一条正则）：JS 的 Number() 认 "0x10"，Python 不认。
 *   * 详细机制说明与「数值假设」见 api.py 的模块文档，两边口径完全相同。
 */
(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  if (root) {
    root.GT_AHA_SPEED_API = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  // ----------------------------------------------------------------------- //
  // 常量
  // ----------------------------------------------------------------------- //

  const DIST_BASE = 10000.0;
  const CYCLE0_AV = 150.0;
  const CYCLE_AV = 100.0;
  const EPS = 1e-9;
  const NUM_LIMIT = 1e9;
  const MAX_TEAM = 4;
  const MAX_TIMELINE = 4000;
  const MAX_NEST = 24;
  const MAX_LOOP = 20000;
  const MAX_AV = 1000.0;

  const AHA_WEIGHTS = [0.2, 0.1, 0.05, 0.025];
  const AHA_DIVISORS = [5, 10, 20, 40];

  const FERVOR_THRESHOLDS = [
    [10.0],
    [10.0, 20.0, 30.0],
    [10.0, 20.0, 30.0, 40.0, 50.0],
  ];

  const TALENT_ATTACK_KINDS = ["basic", "skill", "enhanced_basic", "ultimate", "fua"];

  // 档案里写了欢愉技的角色（官方 sp_base=5，阿哈只 +1 愿力）。
  // nanoka 4.6.53: elation_priority_value; 1511 always acts last.
  const ELATION_NUMBERS = { "1511": 0, "1501": 144, "1502": 116, "1503": 104, "1505": 146, "1506": 999, "1513": 156, "8009": 120 };
  const ELATION_SKILL_UIDS = Object.fromEntries(Object.keys(ELATION_NUMBERS).map((id) => [id, true]));

  const PEARL_LC_ENERGY = 10.0;
  const YAO_LC_ERR = 12.0;
  const YAO_LC_WAVE_ENERGY = 15.0;
  const SUNDAY_LC_ENERGY = 6.0;
  const ROBIN_LC_ERR_PER_STACK = 3.0;
  const ROBIN_LC_MAX_STACKS = 5;
  const WOLF_LC_PUNCHLINE = 20.0;

  // ----------------------------------------------------------------------- //
  // 角色表（内置数据；payload 可逐项覆盖）
  // ----------------------------------------------------------------------- //

  const ROSTER = {
    "1511": {
      name: "星神★阿哈",
      aliases: ["xuzhao", "aeon_aha"],
      path: "欢愉",
      elation: true,
      baseSpd: 94.0,
      traceSpd: 5.0,
      lcBaseSpd: 12.0,
      maxSp: 8.0,
      energy: "wishpower",
      energyName: "愿力",
      rotation: "skill",
      mechanics: [
        "特殊能量【愿力】：上限 8（可溢出到 10），不受 ERR 加成",
        "专属被动【阿哈时刻在】：【阿哈时刻】底速 = 本体基础速度（含专武）",
        "行迹3【盒中蕴藏的世界】：进战自身拉条 30%（速度 ≥125/150 时欢愉度 +120%/+150%）",
        "战技：指定【「欢愉」令使】并发动量子欢愉追击（净耗 0 战技点）",
        "终结技：拉条【阿哈时刻】20%，进入【欢愉万相】3 回合；E6 首次改为拉条 100% 并获得 100 笑点",
        "固有行迹【欢愉万相★无中生有】：开大后的【欢愉万相】使欢愉命途升格，返还消耗笑点的 10%（E2 只加强暴击与无视防御）",
      ],
    },
    "1503": {
      name: "真珠",
      aliases: ["pearl"],
      path: "欢愉",
      elation: true,
      baseSpd: 99.0,
      traceSpd: 9.0,
      lcBaseSpd: 0.0,
      maxSp: 180.0,
      energy: "standard",
      energyName: "能量",
      rotation: "auto",
      mechanics: [
        "指定【美学底本】（不能是自己）",
        "战技：群疗 + 全队好活当赏 +15（基础回能 30 × ERR）",
        "有【深度学习】时自动打强化普攻（群攻群疗，基础回能 30 × ERR）",
        "终结技：真珠全体拉条 10%/15%/30%（按欢愉人数）；4 欢愉时给【美学底本】额外回合",
        "行迹3【艺术壁垒】：【美学底本】（欢愉）下一次开大时真珠 +90 固定能量",
        "固有行迹【欢愉万相★跃然纸上】：升格后好活当赏上限 75；终结技额外回合结束保留该次好活当赏与笑点的 10%",
      ],
    },
    "1513": {
      name: "砂金•戏浪",
      aliases: ["aventurine_sp"],
      path: "欢愉",
      elation: true,
      baseSpd: 107.0,
      traceSpd: 9.0,
      lcBaseSpd: 0.0,
      maxSp: 130.0,
      energy: "standard",
      energyName: "能量",
      rotation: "skill",
      mechanics: [
        "天赋：队友每次攻击 +1 热意 +1 笑点；行迹3【旧梦淘金】再 +2 热意（6 次/战技周期）",
        "战技：+4 笑点 +4 热意，【旧梦淘金】充能重置 6（基础回能 30 × ERR）",
        "终结技：+6 笑点 +8 热意，自身速度 +30%（4 回合）",
        "热意过阈值（E0 10，上限 30；E1 10/20/30；E2 10/20/30/40/50）立刻在回合外放《举杯！敬炽烈一夏》（好活当赏计入 20，不进笑点池），并把下一次阿哈时刻欢愉技升级为《All in！》",
        "行迹2【纵享惊涛】：单欢愉或三赌牌局时队友攻击 → 【阿哈时刻】+25 固定速度",
        "固有行迹【欢愉万相★三赌牌局】：升格且另一名欢愉只有星神★阿哈时，纵享惊涛加强为全队速度 +15%、攻击热意 +1、笑点 +1",
      ],
    },
    "1304": {
      name: "砂金(存护)",
      aliases: ["aventurine"],
      path: "存护",
      elation: false,
      baseSpd: 106.0,
      traceSpd: 0.0,
      lcBaseSpd: 0.0,
      maxSp: 110.0,
      energy: "standard",
      energyName: "能量",
      rotation: "skill",
      mechanics: [
        "战技/追击给全队护盾 → 触发阿哈行迹2（+1 愿力）",
        "【盲注】：每次攻击 +1 层，7 层触发 7 段追击（基础回能 7 × ERR）",
      ],
    },
    "1502": {
      name: "爻光",
      aliases: ["yaoguang"],
      path: "欢愉",
      elation: true,
      baseSpd: 101.0,
      traceSpd: 9.0,
      lcBaseSpd: 0.0,
      maxSp: 180.0,
      energy: "standard",
      energyName: "能量",
      rotation: "skill",
      mechanics: [
        "普攻基础回能 30（战技 30，终结技返还 5）",
        "秘技/战技：展开 3 回合结界；结界内自己普攻/战技 +3 笑点，E2 全队速度 +12%",
        "终结技：+5 笑点并给【阿哈时刻】1 个额外回合（20 笑点，E1 为 40）",
        "欢愉万相★心灵感应（命途升格）：【大吉大利】倍率提高原倍率的 20%（10 级 20%→24%）；终结技 +12 固定能量 +10 笑点",
      ],
    },
    "1501": {
      name: "火花",
      aliases: ["sparxie"],
      path: "欢愉",
      elation: true,
      baseSpd: 107.0,
      traceSpd: 0.0,
      lcBaseSpd: 0.0,
      maxSp: 160.0,
      energy: "standard",
      energyName: "能量",
      rotation: "skill",
      mechanics: [
        "战技/普攻 +4 笑点（基础回能 30）",
        "终结技：2 + (2/4/8 按其他欢愉人数) 笑点，E4 再 +5",
        "E2：【阿哈时刻】每次结束立刻获得 1 个额外回合",
        "固有行迹【欢愉万相★兔子戏法】：升格后欢愉技倍率提高原倍率的 50%，我方伤害无视 15% 防御；红红火火的额外笑点不模拟",
      ],
    },
    "8009": {
      name: "开拓者•欢愉",
      aliases: ["tb_elation"],
      path: "欢愉",
      elation: true,
      baseSpd: 106.0,
      traceSpd: 0.0,
      lcBaseSpd: 0.0,
      maxSp: 160.0,
      energy: "standard",
      energyName: "能量",
      rotation: "skill",
      mechanics: [
        "天赋：普攻/战技后 +10 固定能量 +3 笑点",
        "终结技：+5 笑点；指定目标拥有欢愉技则立刻放 1 次（好活当赏计入 20，不进笑点池），否则拉条 50%",
        "固有行迹【欢愉万相★主角光环】：升格后若终结技目标是星神★阿哈，先放一次开拓者欢愉技，再放阿哈欢愉技",
      ],
    },
    "1505": {
      name: "绯英",
      aliases: ["feiying"],
      path: "欢愉",
      elation: true,
      baseSpd: 104.0,
      traceSpd: 5.0,
      lcBaseSpd: 0.0,
      maxSp: 480.0,
      energy: "standard",
      energyName: "能量",
      rotation: "skill",
      mechanics: [
        "战技：+10 笑点、基础回能 30 × ERR",
        "能量与好活当赏双向同步（不循环互触发），单次同步好活当赏最多 100",
        "累计每 240 能量触发【狐狸老师】追击（基础回能 10 × ERR，单次累计最多 240）；E1 追击后施放欢愉技",
        "秘技自身好活当赏 +20；欢愉技额外 +5（E1 +15）；E6 好活当赏延长 1 回合",
        "瞰众乐/开不败：参演编号更小队友获得/任意队友到期的好活当赏转移 50%；E2 分别为 75%/100%",
        "能量上限 480，终结技每次消耗 240，能开即开且保留剩余能量；返还 5 × ERR",
        "E6：首次终结技固定 +120 能量，之后每 4 次终结技再触发",
        "固有行迹【欢愉万相★书中折花】：升格后溢出能量最多 60，开大后恢复且不触发天赋好活当赏",
      ],
    },
    "1506": {
      name: "银狼LV.999",
      aliases: ["silverwolf999"],
      path: "欢愉",
      elation: true,
      baseSpd: 110.0,
      traceSpd: 9.0,
      lcBaseSpd: 0.0,
      maxSp: 60.0,
      energy: "hidden",
      energyName: "隐藏分",
      rotation: "skill",
      mechanics: [
        "战技 +5 笑点；隐藏分 = 全队获得的笑点（只有自己的欢愉技再 +15）",
        "隐藏分 ≥ 60 开大：自身拉条 100%，进入【无敌玩家】打 3 次强化普攻；无敌期间不能再开大，退出时清空隐藏分（E1 保留 20%）",
        "行迹【真结局】：欢愉技计入笑点 ≥20 / ≥40 各 +20 隐藏分；【隐藏关卡】：进入无敌玩家 +20",
        "基础天赋隐藏分可溢出 240；升格【全息幻象】溢出至 360，获得好活当赏时隐藏分 +该次的 20%",
      ],
    },
    "1313": {
      name: "星期日",
      aliases: ["sunday"],
      path: "同谐",
      elation: false,
      baseSpd: 96.0,
      traceSpd: 0.0,
      lcBaseSpd: 0.0,
      maxSp: 130.0,
      energy: "standard",
      energyName: "能量",
      rotation: "skill",
      mechanics: [
        "战技：指定目标拉条 100%",
        "终结技：给指定目标回能 max(40, 20% 能量上限)（固定回能）",
        "行迹【崇高拂尘】：战斗开始 +25 能量；E4：回合开始 +8 能量",
      ],
    },
    "1309": {
      name: "知更鸟",
      aliases: ["robin"],
      path: "同谐",
      elation: false,
      baseSpd: 102.0,
      traceSpd: 5.0,
      lcBaseSpd: 0.0,
      maxSp: 160.0,
      energy: "standard",
      energyName: "能量",
      rotation: "skill",
      mechanics: [
        "天赋：我方每次攻击后恢复 2 点能量（E2 为 3）",
        "战技基础回能 35（30 + 行迹【模进乐段】5）",
        "秘技：每波次开始 +5 能量（本工具=战斗开始一次）",
        "终结技：其他队友全体拉条 100%，并召唤 90 速【协奏】倒计时；协奏期间本体不行动",
      ],
    },
  };

  const ALIASES = {};
  // JS 对象的整数型键（"1511" 这种）会按数值升序枚举，不是插入顺序 ——
  // catalog 的 roster 顺序要和 Python 的字典插入顺序一致，只能自己记一份。
  // 升格开始时写进 notes 的说明。和 api.py 的 ASCENSION_ALLY_NOTES 逐字相同。
  const ASCENSION_ALLY_NOTES = {
    "1501": "火花固有行迹【欢愉万相★兔子戏法】生效：欢愉技倍率提高原倍率的 50%，我方伤害无视 15% 防御；每 10 点好活当赏使【红红火火】额外 +1 笑点，最多 +8。本工具不掷互动陷阱，因此不加这份笑点",
    "1502": "爻光固有行迹【欢愉万相★心灵感应】生效：【大吉大利】倍率提高原倍率的 20%（20%→24%），终结技固定能量 +12、笑点 +10",
    "1503": "真珠固有行迹【欢愉万相★跃然纸上】生效：好活当赏持有上限 75；终结技额外回合结束时保留该次好活当赏与笑点的 10%",
    "1505": "绯英固有行迹【欢愉万相★书中折花】生效：1/2级溢出能量最多 60/240，开大后恢复且不触发天赋好活当赏；伤害无视 10%/24% 防御；每累计 480 点好活当赏，下次终结技倍率提高原倍率的 75%/150%",
    "1506": "银狼固有行迹【欢愉万相★全息幻象】生效：隐藏分可溢出至 360，暴击伤害 +40%；获得好活当赏时隐藏分 +该次的 20%",
    "1513": "砂金•戏浪固有行迹【欢愉万相★三赌牌局】：仅当队伍里另一名欢愉只有星神★阿哈时，纵享惊涛加强为全队速度 +15%、队友攻击热意 +1、笑点 +1",
    "8009": "开拓者•欢愉固有行迹【欢愉万相★主角光环】生效：终结技暴伤额外 +20% 且全队；触发阿哈欢愉技前先放一次开拓者欢愉技（倍率提高原倍率的 200%）；阿哈真实伤害改为该次的 20%",
  };
  const ASCENSION_TRACE_NAME = {
    "1501": "欢愉万相★兔子戏法",
    "1502": "欢愉万相★心灵感应",
    "1503": "欢愉万相★跃然纸上",
    "1505": "欢愉万相★书中折花",
    "1506": "欢愉万相★全息幻象",
    "1511": "欢愉万相★无中生有",
    "1513": "欢愉万相★三赌牌局",
    "8009": "欢愉万相★主角光环",
  };

  const ROSTER_ORDER = ["1511", "1503", "1513", "1304", "1502", "1501", "8009", "1505", "1506", "1313", "1309"];
  ROSTER_ORDER.forEach((uid) => {
    (ROSTER[uid].aliases || []).forEach((alias) => {
      ALIASES[alias.toLowerCase()] = uid;
    });
  });

  const EQUIPMENT_META = [
    { id: "vonwacq", name: "生命的翁瓦克 (2pc)", text: "ERR +5%；进战时速度 ≥ 120 则开局拉条 40%" },
    { id: "godJoy", name: "神的瞬息欢愉 (2pc)", text: "速度 +6%；开局 40% 拉条需要欢愉度 ≥ 40%（本工具不模拟欢愉度，因此不拉条）" },
    { id: "windSet4", name: "晨昏交界的翔鹰 (4pc)", text: "施放终结技后自身拉条 25%（回合内开大则回合结束再扣）" },
    { id: "danceS5", name: "叠5 舞！舞！舞！", text: "施放终结技后我方全体拉条 24%（可调 dancePct）" },
    { id: "hasSigLc", name: "星神★阿哈专武《当第一声「阿哈」响起》", text: "基础速度 +12；战技给笑点（每 2 回合 1 次）" },
    { id: "hasSummerLc", name: "《向浪花掷下盛夏》", text: "施放欢愉技获【风口】：自身速度 +24%~40%（按常驻处理）" },
    { id: "hasPearlLc", name: "真珠专武《献给明日的色彩》", text: "装备者对我方全体施放欢愉技时固定恢复 10 点能量（S1）" },
    { id: "hasYaoLc", name: "爻光/开拓者专武《当她决定看见》", text: "ERR +12%；每波次开始固定恢复 15 点能量（本工具=战斗开始一次）" },
    { id: "hasFeiyLc", name: "绯英专武《邂逅于下一个花季》", text: "ERR +10%，能量上限超过 120 时每 10 点再 +0.3%，最多计 360 点（480 上限时共 +20.8%）" },
    { id: "hasSundayLc", name: "星期日专武《回到大地的飞行》", text: "对我方单体施放战技/终结技后，自身恢复 6 点能量（S1）" },
    { id: "hasRobinLc", name: "知更鸟专武《夜色流光溢彩》", text: "我方每次攻击叠 1 层【歌咏】，每层 ERR +3%，最多 5 层；开大时清空" },
    { id: "hasWolfLc", name: "银狼专武《欢迎来到银河城》", text: "对自身施放终结技时获得 20 点笑点（S1），并同步为隐藏分" },
  ];

  const CONFIG_META = [
    { key: "maxAV", label: "模拟上限 (AV)", default: 300.0, type: "number", min: 1, max: 1000 },
    { key: "useAeonAha", label: "启用【阿哈时刻在】升格底速", default: null, type: "bool" },
    { key: "useTech", label: "计入秘技进战效果", default: true, type: "bool" },
    { key: "trace3Advance", label: "阿哈行迹3 进战自身拉条 30%", default: true, type: "bool" },
    { key: "ultAdvanceAha", label: "阿哈终结技拉条【阿哈时刻】%", default: 20.0, type: "number", min: 0, max: 100 },
    { key: "e1Wishpower", label: "阿哈 E1 开局愿力", default: 5.0, type: "number", min: 0, max: 10 },
    { key: "ultSpdPct", label: "砂金•戏浪终结技自提速%", default: 30.0, type: "number", min: 0, max: 200 },
    { key: "sanduTeamSpdPct", label: "三赌牌局全队提速%", default: 15.0, type: "number", min: 0, max: 200 },
    { key: "sanduFervorGain", label: "三赌牌局每次队友攻击热意", default: 1.0, type: "number", min: 0, max: 10 },
    { key: "sanduPunchlineGain", label: "三赌牌局每次队友攻击笑点", default: 1.0, type: "number", min: 0, max: 10 },
    { key: "dancePct", label: "舞！舞！舞！全队拉条%", default: 24.0, type: "number", min: 0, max: 100 },
    { key: "summerLcSpdPct", label: "【风口】自提速%", default: 24.0, type: "number", min: 0, max: 200 },
    { key: "sigLcPunchline", label: "阿哈专武战技笑点", default: 10.0, type: "number", min: 0, max: 100 },
    { key: "aeonAhaBaseSpd", label: "【阿哈时刻】底速", default: 94.0, type: "number", min: 0, max: 1000 },
    { key: "aeonAhaLcBaseSpd", label: "【阿哈时刻】专武基础速度", default: 12.0, type: "number", min: 0, max: 1000 },
    { key: "ahaSpdPct", label: "【阿哈时刻】额外速度%", default: 0.0, type: "number", min: -100, max: 1000 },
    { key: "ahaAdvancePct", label: "开局拉条【阿哈时刻】%", default: 0.0, type: "number", min: 0, max: 100 },
    { key: "feiyingHaohuoEnergyMode", label: "绯英好活当赏回能方式", default: "punchline", type: "choice", choices: ["punchline", "flat"] },
    { key: "feiyingHaohuoEnergy", label: "绯英好活当赏固定回能（flat）", default: 20.0, type: "number", min: 0, max: 480 },
  ];

  const AV_NODES = [
    { t: 0, av: 150.0, label: "0T 首轮 (150 AV)" },
    { t: 1, av: 250.0, label: "1T 次轮 (250 AV)" },
    { t: 2, av: 350.0, label: "2T 三轮 (350 AV)" },
    { t: 3, av: 450.0, label: "3T 四轮 (450 AV)" },
  ];

  // ----------------------------------------------------------------------- //
  // 小工具
  // ----------------------------------------------------------------------- //

  /** 数字格式化：与 Python 的 fmt() 逐位一致（放大后 half-up 再拼串）。 */
  function fmt(x, digits) {
    const d = digits === undefined ? 2 : digits;
    const neg = x < 0;
    const scaled = Math.abs(Number(x)) * Math.pow(10, d);
    const n = Math.floor(scaled + 0.5);
    const base = Math.pow(10, d);
    const ip = Math.floor(n / base);
    const fp = n % base;
    let s;
    if (d > 0) {
      s = ip + "." + String(fp).padStart(d, "0");
    } else {
      s = String(ip);
    }
    if (neg && n) {
      s = "-" + s;
    }
    return s;
  }

  /** Python 的 str()/int() 混合：1511.0 这种整数值浮点当成 "1511"。 */
  function idStr(value) {
    if (typeof value === "number" && Number.isInteger(value)) {
      return String(value);
    }
    return String(value);
  }

  function resolveUid(raw) {
    const key = idStr(raw === undefined || raw === null ? "" : raw).trim();
    if (!key) {
      throw new Error("队伍里有角色没给 id");
    }
    const low = key.toLowerCase();
    if (Object.prototype.hasOwnProperty.call(ALIASES, low)) {
      return ALIASES[low];
    }
    return key;
  }

  /** 数字串只认十进制写法（与 Python 同一条正则）。 */
  const NUM_RE = /^[+-]?([0-9]+(\.[0-9]*)?|\.[0-9]+)([eE][+-]?[0-9]+)?$/;

  function pyRepr(value) {
    if (value === undefined || value === null) return "None";
    if (typeof value === "string") return "'" + value + "'";
    return String(value);
  }

  /** 报错文案里的数字：整数不带小数点，其余保留 2 位（与 Python 的 fmt_auto 一致）。 */
  function fmtAuto(x) {
    const s = fmt(x, 2);
    return s.slice(-3) === ".00" ? s.slice(0, -3) : s;
  }

  function num(container, key, dflt, lo, hi) {
    const low = lo === undefined ? -NUM_LIMIT : lo;
    const high = hi === undefined ? NUM_LIMIT : hi;
    const value = container[key];
    if (value === undefined || value === null || value === "") {
      return Number(dflt);
    }
    let number;
    if (typeof value === "string") {
      const text = value.trim();
      if (!NUM_RE.test(text)) {
        throw new Error("参数 " + key + " 需要是数字，收到 " + pyRepr(value));
      }
      number = Number(text);
    } else {
      number = Number(value);
      if (typeof value === "boolean") {
        number = value ? 1 : 0; // 与 Python float(True) == 1.0 对齐
      }
    }
    if (!Number.isFinite(number) || Math.abs(number) > NUM_LIMIT) {
      throw new Error("参数 " + key + " 超出范围，收到 " + pyRepr(value));
    }
    if (number < low || number > high) {
      throw new Error(
        "参数 " + key + " 需要在 " + fmtAuto(low) + "~" + fmtAuto(high) + " 之间，收到 " + fmtAuto(number)
      );
    }
    return number;
  }

  /** Python 的 bool()：[] / {} 是假值，其余交给 JS 真值判断。 */
  function pyBool(value) {
    if (Array.isArray(value)) return value.length > 0;
    if (value !== null && typeof value === "object") return Object.keys(value).length > 0;
    return Boolean(value);
  }

  function boolOf(container, key, dflt) {
    const value = container[key];
    if (value === undefined || value === null) {
      return pyBool(dflt);
    }
    return pyBool(value);
  }

  /** 行动值 → MoC 轮次：av ≤ 150 是 0T，(150, 250] 是 1T，(250, 350] 是 2T…… */
  function cycleOf(av) {
    if (av <= CYCLE0_AV + EPS) {
      return 0;
    }
    return Math.trunc(Math.ceil((av - CYCLE0_AV) / CYCLE_AV - EPS));
  }

  function isDict(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  // ----------------------------------------------------------------------- //
  // 单位
  // ----------------------------------------------------------------------- //

  class Unit {
    constructor(slot, uid, name, spec, raw) {
      const equip = isDict(raw.equipment) ? raw.equipment : {};
      const hasSigLc = boolOf(equip, "hasSigLc", uid === "1511");
      this.slot = slot;
      this.uid = uid;
      this.name = name;
      this.elation = boolOf(raw, "elation", Boolean(spec.elation));
      this.baseSpd = num(raw, "baseSpd", Number(spec.baseSpd !== undefined ? spec.baseSpd : 100.0), 0.0, 10000.0);
      // 光锥基础速度在百分比乘区内：默认只在 hasSigLc 时算专武白值
      const lcDefault = hasSigLc ? Number(spec.lcBaseSpd !== undefined ? spec.lcBaseSpd : 0.0) : 0.0;
      this.lcBaseSpd = num(raw, "lcBaseSpd", lcDefault, 0.0, 10000.0);
      this.traceSpd = num(raw, "traceSpd", Number(spec.traceSpd !== undefined ? spec.traceSpd : 0.0), -1000.0, 10000.0);
      this.permPct = num(raw, "permPct", 0.0, -100.0, 10000.0);
      this.permFlat = num(raw, "permFlat", 0.0, -10000.0, 10000.0);
      this.buffPct = num(raw, "buffPct", 0.0, -100.0, 10000.0);
      this.buffFlat = num(raw, "buffFlat", 0.0, -10000.0, 10000.0);
      this.err = num(raw, "err", 0.0, -100.0, 10000.0);
      this.eidolon = Math.trunc(num(raw, "eidolon", 0.0, 0.0, 6.0));
      this.initAdv = num(raw, "initAdv", 0.0, 0.0, 100.0);
      this.maxSp = num(raw, "maxSp", Number(spec.maxSp !== undefined ? spec.maxSp : 120.0), 1.0, 100000.0);
      const rotation = String(raw.rotation || spec.rotation || "skill");
      if (rotation !== "auto" && rotation !== "basic" && rotation !== "skill") {
        throw new Error("参数 rotation 需要是 auto/basic/skill，收到 " + pyRepr(rotation));
      }
      this.rotation = rotation;
      this.energyType = String(spec.energy || "standard");
      this.energyName = String(spec.energyName || "能量");
      this.targetSlot = null;
      const target = raw.targetSlot;
      if (target !== undefined && target !== null && target !== "") {
        this.targetSlot = Math.trunc(num(raw, "targetSlot", 0.0, 0.0, 3.0));
      }

      // 遗器/光锥开关
      this.equip = {
        vonwacq: boolOf(equip, "vonwacq", false),
        godJoy: boolOf(equip, "godJoy", false),
        windSet4: boolOf(equip, "windSet4", false),
        danceS5: boolOf(equip, "danceS5", false),
        hasSigLc: hasSigLc,
        hasSummerLc: boolOf(equip, "hasSummerLc", false),
        hasPearlLc: boolOf(equip, "hasPearlLc", false),
        hasYaoLc: boolOf(equip, "hasYaoLc", false),
        hasFeiyLc: boolOf(equip, "hasFeiyLc", false),
        hasSundayLc: boolOf(equip, "hasSundayLc", false),
        hasRobinLc: boolOf(equip, "hasRobinLc", false),
        hasWolfLc: boolOf(equip, "hasWolfLc", false),
      };
      if (this.equip.vonwacq) {
        this.err += 5.0;
      }
      if (this.equip.godJoy) {
        this.permPct += 6.0;
      }
      if (this.equip.hasYaoLc) {
        this.err += YAO_LC_ERR;
      }
      if (this.equip.hasFeiyLc) {
        const extraCap = Math.min(Math.max(0.0, this.maxSp - 120.0), 360.0);
        this.err += 10.0 + (extraCap / 10.0) * 0.3;
      }

      // 行动条状态
      this.remDist = DIST_BASE;
      this.pendingAa = 0.0;
      this.inTurn = false;
      this.castingUlt = false;
      this.timed = []; // {"kind","value","turns"(null=常驻),"label"}
      this.haohuo = []; // {"turns","count","label"}
      this.notes = [];

      // 资源。标准能量角色进战 = 上限 50%；愿力/隐藏分等特殊资源仍从 0 开始。
      this.energy = this.energyType === "standard" ? this.maxSp * 0.5 : 0.0;
      this.initialEnergy = num(raw, "initialEnergy", this.energy, 0.0,
        this.energyType === "wishpower" ? 10.0 : this.maxSp);
      this.energy = this.initialEnergy;
      this.energyTotal = 0.0;
      this.actionCount = 0;
      this.turnCount = 0;
      this.ultCount = 0;
      this.extraCount = 0;
      this.fuaCount = 0;

      // 角色专属状态
      this.huanyu = 0;
      this.trace2Used = false;
      this.sigLcCd = 0;
      this.depth = 0;
      this.barrier = false;
      this.fervor = 0.0;
      this.fervorArmed = [false, false, false, false, false];
      this.allIn = false;
      this.jiumeng = 6;
      this.blind = 0;
      this.field = 0;
      this.feiyTotal = 0.0;
      this.feiyBanger = 0.0;
      this.feiyUltBonus = 0;
      this.invincible = 0;
      this.hiddenOverflow = 0.0;
      this.concerto = false;
      this.lcErStacks = 0;
      this.lcEr = 0.0;

      this.initialSpd = 0.0;
    }
  }

  // ----------------------------------------------------------------------- //
  // 模拟引擎
  // ----------------------------------------------------------------------- //

  class Sim {
    constructor(payload) {
      if (!isDict(payload)) {
        throw new Error("payload 需要是对象");
      }
      this.cfg = this.parseConfig(payload);
      this.units = this.buildUnits(payload);

      this.av = 0.0;
      this.punchline = 0.0;
      this.punchline40Done = false;
      this.punchlineConsumed = 0.0;
      this.punchlineGranted = 0.0;
      this.ahaFlat = 0.0;
      this.aha = { rem_dist: DIST_BASE, pending: 0.0, in_turn: false };
      this.summons = [];
      this.timeline = [];
      this.warnings = [];
      this.notes = [];
      this.depth = 0;
      this.truncated = false;
      this.ahaNormalCount = 0;
      this.ahaExtraCount = 0;
      this.extraDepth = 0;
      this.opening = false;
      this.resourceDepth = 0;

      // 指定目标
      const pearlChar = this.byUid("1503");
      this.aesteSlot = this.resolveTargetSlot(pearlChar, 0); // 真珠的【美学底本】
      this.lingshiSlot = null; // 阿哈的【「欢愉」令使】（战技指定）
      const ahaChar = this.byUid("1511");
      if (ahaChar !== null) {
        this.lingshiPrefer = this.resolveTargetSlot(ahaChar, 0);
      } else {
        this.lingshiPrefer = null;
      }

      // 【阿哈时刻】底速解析
      this.useAeonAha = this.cfg.use_aeon_aha;
      if (this.useAeonAha === null) {
        this.useAeonAha = ahaChar !== null;
      } else {
        this.useAeonAha = Boolean(this.useAeonAha) || ahaChar !== null;
      }
      if (this.cfg.aeon_aha_base_spd === null) {
        this.ahaBaseSpd = ahaChar !== null ? ahaChar.baseSpd : 94.0;
      } else {
        this.ahaBaseSpd = this.cfg.aeon_aha_base_spd;
      }
      if (this.cfg.aeon_aha_lc_base_spd === null) {
        this.ahaLcBaseSpd = ahaChar !== null ? ahaChar.lcBaseSpd : 12.0;
      } else {
        this.ahaLcBaseSpd = this.cfg.aeon_aha_lc_base_spd;
      }

      this.ahaInitialSpd = 0.0;
    }

    // ----------------------------- 配置与队伍 ----------------------------- #

    parseConfig(payload) {
      // e6FirstUltMode 是旧开关。nanoka 只有一种 E6 首大，传来就忽略。
      const feiMode = String(payload.feiyingHaohuoEnergyMode || "punchline");
      if (feiMode !== "punchline" && feiMode !== "flat") {
        throw new Error("参数 feiyingHaohuoEnergyMode 需要是 punchline/flat，收到 " + pyRepr(feiMode));
      }
      const useAeon = payload.useAeonAha;
      const baseSpd = payload.aeonAhaBaseSpd;
      const lcSpd = payload.aeonAhaLcBaseSpd;
      return {
        max_av: num(payload, "maxAV", 300.0, 1.0, MAX_AV),
        use_aeon_aha: useAeon === undefined || useAeon === null ? null : Boolean(useAeon),
        use_tech: boolOf(payload, "useTech", true),
        trace3_advance: boolOf(payload, "trace3Advance", true),
        ult_advance_aha: num(payload, "ultAdvanceAha", 20.0, 0.0, 100.0),
        e1_wishpower: num(payload, "e1Wishpower", 5.0, 0.0, 10.0),
        ult_spd_pct: num(payload, "ultSpdPct", 30.0, -100.0, 1000.0),
        sandu_team_spd_pct: num(payload, "sanduTeamSpdPct", 15.0, -100.0, 1000.0),
        sandu_fervor_gain: num(payload, "sanduFervorGain", 1.0, 0.0, 10.0),
        sandu_punchline_gain: num(payload, "sanduPunchlineGain", 1.0, 0.0, 10.0),
        dance_pct: num(payload, "dancePct", 24.0, 0.0, 100.0),
        summer_lc_spd_pct: num(payload, "summerLcSpdPct", 24.0, -100.0, 1000.0),
        sig_lc_punchline: num(payload, "sigLcPunchline", 10.0, 0.0, 100.0),
        aeon_aha_base_spd:
          baseSpd === undefined || baseSpd === null || baseSpd === ""
            ? null
            : num(payload, "aeonAhaBaseSpd", 94.0, 0.0, 1000.0),
        aeon_aha_lc_base_spd:
          lcSpd === undefined || lcSpd === null || lcSpd === ""
            ? null
            : num(payload, "aeonAhaLcBaseSpd", 12.0, 0.0, 1000.0),
        aha_spd_pct: num(payload, "ahaSpdPct", 0.0, -100.0, 1000.0),
        aha_advance_pct: num(payload, "ahaAdvancePct", 0.0, 0.0, 100.0),
        feiying_haohuo_mode: feiMode,
        feiying_haohuo_energy: num(payload, "feiyingHaohuoEnergy", 20.0, 0.0, 10000.0),
      };
    }

    buildUnits(payload) {
      const team = payload.team;
      if (!Array.isArray(team) || team.length === 0) {
        throw new Error("参数 team 需要是 1~4 个成员的列表");
      }
      if (team.length > MAX_TEAM) {
        throw new Error("参数 team 最多 " + MAX_TEAM + " 人，收到 " + team.length);
      }
      const units = [];
      for (let slot = 0; slot < team.length; slot += 1) {
        const raw = team[slot];
        if (!isDict(raw)) {
          throw new Error("参数 team[" + slot + "] 需要是对象");
        }
        const uid = resolveUid(raw.id);
        const spec = ROSTER[uid] || {};
        let name = raw.name;
        name =
          typeof name === "string" && name.trim()
            ? String(name).trim()
            : String(spec.name || uid);
        units.push(new Unit(slot, uid, name, spec, raw));
      }
      return units;
    }

    /** 指定目标：优先用户给的 targetSlot（不能是自己），默认 slot 0（是自己就顺延）。 */
    resolveTargetSlot(caster, prefer) {
      const n = this.units.length;
      if (caster !== null && caster !== undefined && caster.targetSlot !== null) {
        const requested = caster.targetSlot;
        if (requested >= 0 && requested < n && requested !== caster.slot) {
          return requested;
        }
      }
      const candidate = prefer === undefined || prefer === null ? 0 : prefer;
      if (candidate >= 0 && candidate < n && (caster === null || caster === undefined || candidate !== caster.slot)) {
        return candidate;
      }
      if (caster !== null && caster !== undefined) {
        for (let i = 0; i < this.units.length; i += 1) {
          if (this.units[i].slot !== caster.slot) {
            return this.units[i].slot;
          }
        }
        return caster.slot;
      }
      return 0;
    }

    // ----------------------------- 查询小工具 ----------------------------- #

    byUid(uid) {
      for (let i = 0; i < this.units.length; i += 1) {
        if (this.units[i].uid === uid) {
          return this.units[i];
        }
      }
      return null;
    }

    unitAt(slot) {
      if (slot === null || slot === undefined) {
        return null;
      }
      for (let i = 0; i < this.units.length; i += 1) {
        if (this.units[i].slot === slot) {
          return this.units[i];
        }
      }
      return null;
    }

    elationUnits() {
      return this.units.filter((u) => u.elation);
    }

    /** 当前可施放欢愉技的角色。星神★阿哈无视参演编号，始终最后。 */
    elationCasters() {
      const casters = this.units.filter((u) => u.elation && ELATION_SKILL_UIDS[u.uid]);
      const rest = casters.filter((u) => u.uid !== "1511")
        .sort((a, b) => ELATION_NUMBERS[a.uid] - ELATION_NUMBERS[b.uid]);
      const last = casters.filter((u) => u.uid === "1511");
      return rest.concat(last);
    }

    elationCount() {
      return this.elationUnits().length;
    }

    huanyuActive() {
      const a = this.byUid("1511");
      return a !== null && a.huanyu > 0;
    }

    singleElation1513() {
      const el = this.elationUnits();
      return el.length === 1 && el[0].uid === "1513";
    }

    /** 三赌牌局：队伍里只有 1511+1513 两名欢愉，且 1511 的【欢愉万相】生效。 */
    sanduActive() {
      if (this.byUid("1513") === null || this.byUid("1511") === null) {
        return false;
      }
      return this.elationCount() === 2 && this.huanyuActive();
    }

    /** 【纵享惊涛】：单欢愉（只有戏浪）或三赌牌局。 */
    trace2Condition() {
      return this.singleElation1513() || this.sanduActive();
    }

    // ----------------------------- 速度 ----------------------------- //

    teamPctExtra(unit) {
      let extra = 0.0;
      const yao = this.byUid("1502");
      if (yao !== null && yao.field > 0 && yao.eidolon >= 2) {
        extra += 12.0;
      }
      if (this.sanduActive()) {
        extra += this.cfg.sandu_team_spd_pct;
      }
      return extra;
    }

    unitSpd(unit) {
      let timedPct = 0.0;
      let timedFlat = 0.0;
      for (let i = 0; i < unit.timed.length; i += 1) {
        const buff = unit.timed[i];
        if (buff.kind === "pct") {
          timedPct += Number(buff.value);
        } else {
          timedFlat += Number(buff.value);
        }
      }
      const pct = unit.permPct + unit.buffPct + timedPct + this.teamPctExtra(unit);
      const flat = unit.permFlat + unit.buffFlat + timedFlat;
      const spd = (unit.baseSpd + unit.lcBaseSpd) * (1.0 + pct / 100.0) + flat + unit.traceSpd;
      return spd > 0 ? spd : 0.0001;
    }

    ahaSpd() {
      const spds = this.elationUnits()
        .map((u) => this.unitSpd(u))
        .sort((a, b) => b - a);
      let weighted = 0.0;
      for (let i = 0; i < 4; i += 1) {
        const v = i < spds.length ? spds[i] : 0.0;
        weighted += AHA_WEIGHTS[i] * v;
      }
      const base = this.useAeonAha ? this.ahaBaseSpd + this.ahaLcBaseSpd : 80.0;
      return (base + weighted + this.ahaFlat) * (1.0 + this.cfg.aha_spd_pct / 100.0);
    }

    ahaBaseValue() {
      return this.useAeonAha ? this.ahaBaseSpd + this.ahaLcBaseSpd : 80.0;
    }

    // ----------------------------- 行动条 ----------------------------- //

    advanceUnit(unit, pct, selfSource) {
      if (pct <= 0) {
        return;
      }
      if (unit.remDist <= 0 && unit.inTurn) {
        // 自己回合里触发的自身拉条挂起，回合结束重置 10000 后再扣；
        // 外部拉条打在正在行动的单位上不吃（舞！舞！舞！原文）。
        if (selfSource) {
          unit.pendingAa += pct;
        }
        return;
      }
      unit.remDist = Math.max(0.0, unit.remDist - (DIST_BASE * pct) / 100.0);
    }

    advanceAha(pct) {
      if (pct <= 0) {
        return;
      }
      const a = this.aha;
      if (a.rem_dist <= 0 && a.in_turn) {
        a.pending += pct;
        return;
      }
      a.rem_dist = Math.max(0.0, a.rem_dist - (DIST_BASE * pct) / 100.0);
    }

    /** 舞！舞！舞！这类全队拉条：正在自己行动的开大者不吃自己那口。 */
    advanceAllies(source, pct) {
      for (let i = 0; i < this.units.length; i += 1) {
        const unit = this.units[i];
        if (unit === source && unit.inTurn) {
          continue;
        }
        this.advanceUnit(unit, pct, unit === source);
      }
    }

    // ----------------------------- 资源 ----------------------------- //

    gainPunchline(amount) {
      if (amount === 0) {
        return;
      }
      const before = this.punchline;
      this.punchline += amount;
      this.punchlineGranted += amount;
      const wolf = this.byUid("1506");
      if (wolf !== null && amount > 0) {
        this.gainEnergy(wolf, amount, true);
      }
      this.checkPunchline40(before);
    }

    checkPunchline40(before) {
      // 这一次添加之前低于 40，添加之后不低于 40，才算首次达到。
      if (this.punchline40Done || before >= 40.0 || this.punchline < 40.0) {
        return;
      }
      this.punchline40Done = true;
      const a = this.byUid("1511");
      if (a !== null) {
        this.gainWishpower(a, 1.0);
        this.notes.push("笑点首达 40：星神★阿哈 +1 愿力，全队暴伤 +40%（3 回合，本工具不模拟伤害）");
      }
    }

    gainWishpower(unit, amount) {
      if (amount <= 0) {
        return;
      }
      unit.energy = Math.min(10.0, unit.energy + amount); // 愿力可溢出到 10
      unit.energyTotal += amount;
      this.maybeUlt(unit);
    }

    /** 【热意】上限：E0 30，E2 起 50（E1 只改阈值不改上限）。 */
    fervorCap(unit) {
      return unit.eidolon >= 2 ? 50.0 : 30.0;
    }

    gainFervor(unit, amount) {
      if (amount <= 0 || unit.uid !== "1513") {
        return;
      }
      unit.fervor = Math.min(this.fervorCap(unit), unit.fervor + amount);
      this.checkFervor(unit);
    }

    gainEnergy(unit, amount, fixed, fromHaohuo = false, reason = "") {
      if (amount === 0) {
        return;
      }
      if (unit.energyType === "wishpower") {
        this.gainWishpower(unit, amount);
        return;
      }
      let gain;
      if (unit.energyType === "hidden" || unit.energyType === "special") {
        gain = amount;
      } else {
        const err = unit.err + (unit.uid === "1309" ? unit.lcEr : 0.0);
        gain = fixed ? amount : amount * (1.0 + err / 100.0);
      }
      // 银狼：基础天赋可溢出 240（合计 300），升格后溢出至 360。
      if (unit.uid === "1506") {
        this.gainWolfOverflow(unit, gain);
        return;
      }
      let cap = Number(unit.maxSp);
      if (unit.uid === "1505" && this.huanyuActive()) {
        const aha = this.byUid("1511");
        cap += aha !== null && aha.eidolon >= 2 ? 240.0 : 60.0;
      }
      const before = unit.energy;
      unit.energy = Math.min(cap, unit.energy + gain);
      if (unit.uid === "1505") {
        const requested = gain;
        gain = Math.max(0.0, unit.energy - before);
        const details = [
          "能量 " + fmt(before) + " → " + fmt(unit.energy) + " / " + fmt(cap, 0),
          "实际 +" + fmt(gain),
        ];
        if (requested - gain > EPS) {
          details.push("上限截掉 " + fmt(requested - gain) + "（不计入天赋累计）");
        }
        this.event("energy_gain", unit, "绯英回能·" + (reason || "回能"), details, {
          resourceChange: { energyBefore: before, energyGain: gain, energyRequested: requested, energyCap: cap },
        });
        if (gain > 0 && !fromHaohuo) {
          this.grantHaohuo([unit], Math.min(gain, 100.0), "绯英·能量转好活当赏", true);
        }
        unit.feiyTotal += Math.min(gain, 240.0);
        this.checkFeiyingMilestone(unit);
      }
      unit.energyTotal += gain;
      this.maybeUlt(unit);
    }

    /** 隐藏分溢出：基础合计上限 300（60 + 240），升格后 360。超出 60 的部分不触发终结技。 */
    gainWolfOverflow(unit, gain) {
      const totalCap = this.huanyuActive() ? 360.0 : Number(unit.maxSp) + 240.0;
      const room = Math.max(0.0, totalCap - (unit.energy + unit.hiddenOverflow));
      const applied = Math.min(gain, room);
      const intoMeter = Math.min(Math.max(0.0, Number(unit.maxSp) - unit.energy), applied);
      const spill = applied - intoMeter;
      unit.energy += intoMeter;
      unit.hiddenOverflow += spill;
      unit.energyTotal += applied;
      if (spill > EPS) {
        this.event("note", unit, "隐藏分溢出",
          ["隐藏分溢出 +" + fmt(spill) + "（合计上限 " + fmt(totalCap, 0) + "）"]);
      }
      if (gain - applied > EPS) {
        this.event("note", unit, "隐藏分溢出",
          ["超出 " + fmt(totalCap, 0) + " 的隐藏分不再计入"]);
      }
      this.maybeUlt(unit);
    }

    haohuoSum(unit) {
      let total = 0.0;
      for (let i = 0; i < unit.haohuo.length; i += 1) {
        total += Number(unit.haohuo[i].count);
      }
      return total;
    }

    /** 绯英累计每 240 能量触发一次【狐狸老师】追击。 */
    checkFeiyingMilestone(unit) {
      if (unit.uid !== "1505") {
        return;
      }
      if (this.depth > MAX_NEST) {
        if (unit.feiyTotal >= 240.0) {
          this.truncated = true;
          this.warnings.push("狐狸老师回能连锁超过嵌套上限，结果已截断，请检查自定义充能效率");
        }
        return;
      }
      this.depth += 1;
      this.resourceDepth += 1;
      try {
        while (unit.feiyTotal >= 240.0 && !this.truncated) {
          unit.feiyTotal -= 240.0;
          unit.fuaCount += 1;
          this.event("fua", unit, "【狐狸老师】追加攻击", ["基础回能 10 × (1+ERR)"]);
          this.gainEnergy(unit, 10.0, false, false, "狐狸老师");
          this.onAttack(unit, "fua");
          if (unit.eidolon >= 1) {
            this.castElationSkill(unit);
          }
        }
      } finally {
        this.resourceDepth -= 1;
        this.depth -= 1;
      }
    }

    maybeUlt(unit) {
      if (this.depth > MAX_NEST || this.extraDepth > 0 || this.resourceDepth > 0
          || this.opening || unit.castingUlt) {
        return;
      }
      // 【无敌玩家】期间无法施放终结技。
      if (unit.uid === "1506" && unit.invincible > 0) {
        return;
      }
      const threshold = this.ultCost(unit);
      let guard = 0;
      while (unit.energy >= threshold - EPS && guard < 4) {
        guard += 1;
        this.castUlt(unit);
        // 银狼开大后进入【无敌玩家】，隐藏分不清空；这里必须停手，否则会连开。
        if (unit.uid === "1506" && unit.invincible > 0) {
          break;
        }
      }
    }

    // ----------------------------- Buff ----------------------------- #

    addTimedBuff(unit, kind, value, turns, label) {
      for (let i = 0; i < unit.timed.length; i += 1) {
        const buff = unit.timed[i];
        if (buff.label === label) {
          buff.value = Number(value);
          buff.turns = turns;
          buff.kind = kind;
          return;
        }
      }
      unit.timed.push({ kind: kind, value: Number(value), turns: turns, label: label });
    }

    grantHaohuo(targets, count, label, fromEnergy = false) {
      for (let i = 0; i < targets.length; i += 1) {
        const unit = targets[i];
        let applied = Number(count);
        // 真珠自己的持有上限。只在升格后夹到 75，且只夹新获得的那一份。
        if (unit.uid === "1503" && this.huanyuActive()) {
          const room = Math.max(0.0, 75.0 - this.haohuoSum(unit));
          applied = Math.min(applied, room);
          if (applied <= EPS) {
            continue;
          }
        }
        const turns = unit.uid === "1505" && unit.eidolon >= 6 ? 3 : 2;
        unit.haohuo.push({ turns: turns, count: applied, label: label });
        const fei = this.byUid("1505");
        if (fei !== null && fei !== unit && Object.hasOwn(ELATION_NUMBERS, unit.uid)
            && ELATION_NUMBERS[unit.uid] < ELATION_NUMBERS[fei.uid]) {
          const copied = applied * (fei.eidolon >= 2 ? 0.75 : 0.5);
          this.event("note", fei, "瞰众乐·好活当赏转移",
            [unit.name + "（编号 " + ELATION_NUMBERS[unit.uid] + "）→ 好活当赏 +" + fmt(copied)]);
          this.grantHaohuo([fei], copied, "瞰众乐");
        }
        if (unit.uid === "1506" && this.huanyuActive() && applied > EPS) {
          const bonus = applied * 0.2;
          this.event("note", unit, "欢愉万相★全息幻象", [
            "好活当赏 " + fmt(applied, 0) + " 的 20% → 隐藏分 +" + fmt(bonus),
          ]);
          this.gainEnergy(unit, bonus, true);
        }
        if (unit.uid === "1505") {
          if (this.huanyuActive() && applied > EPS) {
            unit.feiyBanger += applied;
            while (unit.feiyBanger >= 480.0 - EPS) {
              unit.feiyBanger -= 480.0;
              unit.feiyUltBonus += 1;
            }
          }
          if (fromEnergy) {
            continue;
          }
          let gain =
            this.cfg.feiying_haohuo_mode === "flat" ? this.cfg.feiying_haohuo_energy : Number(count);
          if (this.cfg.feiying_haohuo_mode !== "flat") {
            // 天赋：单次通过好活当赏计算的能量不超过 100 点。
            gain = Math.min(gain, 100.0);
          }
          if (gain > 0) {
            this.gainEnergy(unit, gain, true, true, "好活当赏·" + label);
          }
        }
      }
    }

    // ----------------------------- 事件 ----------------------------- //

    event(evType, unit, label, details, opt) {
      if (this.timeline.length >= MAX_TIMELINE) {
        this.truncated = true;
        return;
      }
      const kind = (opt && opt.kind) || "unit";
      const extra = Boolean(opt && opt.extra);
      const name = (opt && opt.name) || null;
      const a = this.byUid("1511");
      const sp = this.byUid("1513");
      const res = {
        punchline: this.punchline,
        wishpower: a !== null ? a.energy : null,
        fervor: sp !== null ? sp.fervor : null,
        energy: unit !== null && unit !== undefined && unit.energyType !== "wishpower" ? unit.energy : null,
      };
      if (opt && opt.resourceChange) {
        Object.assign(res, opt.resourceChange);
      }
      this.timeline.push({
        av: this.av,
        t: cycleOf(this.av),
        kind: kind,
        slot: unit !== null && unit !== undefined ? unit.slot : null,
        name: name || (unit !== null && unit !== undefined ? unit.name : "【阿哈时刻】"),
        type: evType,
        extra: extra,
        label: label,
        details: details ? details.slice() : [],
        res: res,
      });
    }

    // ----------------------------- 攻击钩子 ----------------------------- //

    onAttack(unit, kind) {
      // 开拓者•欢愉 天赋：自己的普攻/战技后 +10 固定能量 +3 笑点
      if (unit.uid === "8009" && (kind === "basic" || kind === "skill")) {
        this.gainEnergy(unit, 10.0, true);
        this.gainPunchline(3.0);
      }

      // 知更鸟天赋：我方目标每次攻击后知更鸟恢复 2 点能量（E2 为 3，吃 ERR）。
      const robin = this.byUid("1309");
      if (robin !== null && TALENT_ATTACK_KINDS.indexOf(kind) >= 0) {
        if (robin.equip.hasRobinLc && robin.lcErStacks < ROBIN_LC_MAX_STACKS) {
          robin.lcErStacks += 1;
          robin.lcEr = robin.lcErStacks * ROBIN_LC_ERR_PER_STACK;
        }
        const roger = robin.eidolon >= 2 ? 3.0 : 2.0;
        this.gainEnergy(robin, roger, false);
      }

      // 砂金（存护）【盲注】：每次攻击 +1 层（自己的追击不再叠层）
      const avent = this.byUid("1304");
      if (avent !== null && !(unit === avent && kind === "fua")) {
        avent.blind += 1;
        if (avent.blind >= 7) {
          avent.blind = 0;
          this.doAventurineFua(avent);
        }
      }

      // 砂金•戏浪 天赋 / 旧梦淘金 / 三赌牌局
      const sp = this.byUid("1513");
      if (sp !== null && unit !== sp && TALENT_ATTACK_KINDS.indexOf(kind) >= 0) {
        this.gainFervor(sp, 1.0);
        this.gainPunchline(1.0);
        if (sp.jiumeng > 0) {
          sp.jiumeng -= 1;
          this.gainFervor(sp, 2.0);
        }
        if (this.sanduActive()) {
          this.gainFervor(sp, this.cfg.sandu_fervor_gain);
          this.gainPunchline(this.cfg.sandu_punchline_gain);
        }
      }

      // 行迹2【纵享惊涛】：队友攻击 → 【阿哈时刻】+25 固定速度（到下一次阿哈时刻结束）
      if (sp !== null && unit !== sp && this.trace2Condition()) {
        if (this.ahaFlat < 25.0) {
          this.ahaFlat = 25.0;
          this.notes.push("【纵享惊涛】触发：【阿哈时刻】固定速度 +25（到下一次阿哈时刻结束）");
        }
      }

      // 爻光天赋【大吉大利】。命途升格后固有行迹把 10 级倍率 20% 提高为 24%。
      const yao = this.byUid("1502");
      const attack = TALENT_ATTACK_KINDS.indexOf(kind) >= 0 || kind === "elation_skill";
      if (yao !== null && yao.haohuo.length && this.huanyuActive() && attack) {
        this.event("note", yao, "大吉大利", [
          "【大吉大利】欢愉伤害 24%（原倍率 20% × 1.20）",
          "固有行迹【欢愉万相★心灵感应】：倍率提高原倍率的 20%",
          "不视为 1 次攻击",
        ]);
      }
    }

    /** 阿哈行迹2【戏中人的异想国】：受队友治疗/护盾 +1 愿力（每个终结技周期 1 次）。 */
    onHealOrShield(unit, label) {
      const a = this.byUid("1511");
      if (a === null || a.trace2Used) {
        return;
      }
      a.trace2Used = true;
      this.event("note", a, "戏中人的异想国", [label + " → 愿力 +1"]);
      this.gainWishpower(a, 1.0);
    }

    /** 【艺术壁垒】：【美学底本】（欢愉）开大时真珠 +90 固定能量。 */
    checkBarrier(unit) {
      const pearl = this.byUid("1503");
      if (pearl === null || !pearl.barrier || pearl === unit) {
        return;
      }
      if (unit.slot !== this.aesteSlot || !unit.elation) {
        return;
      }
      pearl.barrier = false;
      this.event("note", pearl, "艺术壁垒触发", ["真珠 +90 固定能量（不吃 ERR）"]);
      this.gainEnergy(pearl, 90.0, true);
    }

    // ----------------------------- 热意阈值 ----------------------------- //

    checkFervor(sp, depth) {
      const d = depth === undefined ? 0 : depth;
      if (sp.uid !== "1513" || d > MAX_NEST) {
        return;
      }
      const thresholds = FERVOR_THRESHOLDS[Math.min(sp.eidolon, 2)];
      for (let i = 0; i < 5; i += 1) {
        if (i < thresholds.length) {
          const t = thresholds[i];
          if (sp.fervor >= t && !sp.fervorArmed[i]) {
            sp.fervorArmed[i] = true;
            this.triggerJuban(sp, d + 1);
          } else if (sp.fervor < t) {
            sp.fervorArmed[i] = false;
          }
        }
      }
    }

    /** 热意过阈值：回合外欢愉技《举杯！》。好活当赏固定记 20，不进笑点池。 */
    triggerJuban(sp, depth) {
      this.event("elation_skill", sp, "举杯！敬炽烈一夏（回合外欢愉技）",
        ["好活当赏计入 20（不进笑点池）", "下一次【阿哈时刻】欢愉技升级为《All in！》",
          "基础回能 5 × (1+ERR)"], { extra: true });
      this.grantHaohuo(this.elationUnits(), 20.0, "举杯！敬炽烈一夏");
      sp.allIn = true;
      this.gainEnergy(sp, 5.0, false);
      this.elationSkillCommon(sp, "举杯！敬炽烈一夏");
      if (sp.eidolon >= 2) {
        this.gainFervor(sp, 4.0);
      }
      this.onAttack(sp, "elation_skill");
    }

    // ----------------------------- 欢愉技 ----------------------------- //

    /** 所有欢愉技共用的结算：银狼本人 +15 隐藏分、专武【风口】、真珠专武。 */
    elationSkillCommon(unit, label) {
      if (unit.uid === "1506") {
        this.event("note", unit, "隐藏分 +15", [unit.name + " 施放欢愉技"]);
        this.gainEnergy(unit, 15.0, true);
        // 行迹【真结局】：欢愉技计入笑点 ≥20 / ≥40 各 +20。
        const counted = Math.max(0.0, this.punchline);
        if (counted >= 20.0 - EPS) {
          this.gainEnergy(unit, 20.0, true);
        }
        if (counted >= 40.0 - EPS) {
          this.gainEnergy(unit, 20.0, true);
        }
      }
      if (unit.equip.hasSummerLc) {
        this.addTimedBuff(unit, "pct", this.cfg.summer_lc_spd_pct, null, "【风口】");
        this.notes.push(unit.name + " 施放欢愉技触发【风口】：速度 +" + fmt(this.cfg.summer_lc_spd_pct, 0) + "%");
      }
      if (unit.uid === "1503" && unit.equip.hasPearlLc) {
        this.event("note", unit, "献给明日的色彩", ["施放欢愉技：固定能量 +10"]);
        this.gainEnergy(unit, PEARL_LC_ENERGY, true);
      }
    }

    castElationSkill(unit) {
      if (this.depth > MAX_NEST) {
        return;
      }
      this.depth += 1;
      try {
        if (unit.uid === "1513") {
          let label;
          let details;
          let account;
          if (unit.allIn) {
            unit.allIn = false;
            unit.fervor = 0.0;
            for (let i = 0; i < 5; i += 1) {
              unit.fervorArmed[i] = false;
            }
            label = "All in！敬炽烈一夏（欢愉技）";
            account = "All in！敬炽烈一夏";
            details = ["好活当赏计入 20（不进笑点池）", "消耗全部热意",
              "基础回能 5 × (1+ERR)"];
          } else {
            label = "举杯！敬炽烈一夏（欢愉技）";
            account = "举杯！敬炽烈一夏";
            details = ["好活当赏计入 20（不进笑点池）", "基础回能 5 × (1+ERR)"];
          }
          this.event("elation_skill", unit, label, details);
          this.grantHaohuo(this.elationUnits(), 20.0, account);
          this.gainEnergy(unit, 5.0, false, false, "欢愉技");
          this.elationSkillCommon(unit, label);
          if (unit.eidolon >= 2) {
            this.gainFervor(unit, 4.0);
          }
          this.onAttack(unit, "elation_skill");
          return;
        }
        const label = "欢愉技";
        const plain = ["不产生笑点"];
        if (unit.uid === "1501" && this.huanyuActive()) {
          plain.push("欢愉万相★兔子戏法：欢愉技倍率提高原倍率的 50%（伤害不模拟）");
          plain.push("我方伤害无视 15% 防御（伤害不模拟）");
        }
        if (unit.uid !== "1511" && unit.uid !== "1506") {
          plain.push("基础回能 5 × (1+ERR)");
        }
        this.event("elation_skill", unit, unit.name + " 的欢愉技", plain);
        if (unit.uid === "1511") {
          this.event("note", unit, "自身动作回能", ["愿力 +1"]);
          this.gainWishpower(unit, 1.0);
        } else if (unit.uid !== "1506") {
          this.gainEnergy(unit, 5.0, false, false, "欢愉技");
        }
        if (unit.uid === "1505") {
          const count = unit.eidolon >= 1 ? 15.0 : 5.0;
          this.grantHaohuo([unit], count, "绯英欢愉技");
        }
        this.elationSkillCommon(unit, label);
        this.onAttack(unit, "elation_skill");
      } finally {
        this.depth -= 1;
      }
    }

    // ----------------------------- 出招 ----------------------------- //

    rotationOf(unit) {
      return unit.rotation;
    }

    doAction(unit, extra) {
      const isExtra = Boolean(extra);
      unit.actionCount += 1;
      if (unit.uid === "1506" && unit.invincible > 0) {
        // 先打强化普攻（此时仍在【无敌玩家】中，不能开大），再递减、退出后清隐藏分。
        this.doEnhancedBasic(unit, isExtra);
        unit.invincible -= 1;
        if (unit.invincible === 0) {
          this.exitInvincible(unit);
        }
        return;
      }
      if (unit.uid === "1503") {
        if (unit.depth > 0) {
          this.doPearlEnhancedBasic(unit, isExtra);
        } else {
          this.doSkill(unit, isExtra);
        }
        return;
      }
      if (this.rotationOf(unit) === "basic") {
        this.doBasic(unit, isExtra);
      } else {
        this.doSkill(unit, isExtra);
      }
    }

    doBasic(unit, extra) {
      const details = [];
      if (unit.energyType === "wishpower") {
        // 星神★阿哈的普攻是 +1 愿力，不是标准能量表上的 +20。
        details.push("愿力 +1");
        this.event("basic", unit, unit.name + " 的普攻", details, { extra: extra });
        this.gainWishpower(unit, 1.0);
        this.onAttack(unit, "basic");
        return;
      }
      const energyBase = unit.uid === "1502" ? 30.0 : 20.0;
      if (unit.uid === "1502") {
        details.push("基础回能 30（普攻）");
      } else {
        details.push("基础回能 20（普攻）");
      }
      if (unit.uid === "1502" && unit.field > 0) {
        this.gainPunchline(3.0);
        details.push("结界内 +3 笑点");
      }
      this.event("basic", unit, unit.name + " 的普攻", details, { extra: extra });
      this.gainEnergy(unit, energyBase, false, false, "普攻");
      this.onAttack(unit, "basic");
    }

    doSkill(unit, extra) {
      const details = [];
      const label = unit.name + " 的战技";
      if (unit.uid === "1511") {
        const target = this.unitAt(this.lingshiPrefer);
        if (this.lingshiSlot === null && target !== null) {
          this.lingshiSlot = target.slot;
          details.push("指定 " + target.name + " 为【「欢愉」令使】（欢愉度 +20%）");
        }
        if (unit.equip.hasSigLc && unit.sigLcCd <= 0) {
          unit.sigLcCd = 2;
          this.gainPunchline(this.cfg.sig_lc_punchline);
          details.push("专武：笑点 +" + fmt(this.cfg.sig_lc_punchline, 0));
        }
        details.push("愿力 +1");
        this.event("skill", unit, label, details, { extra: extra });
        this.gainWishpower(unit, 1.0);
        unit.fuaCount += 1;
        this.event("fua", unit, "此乃令使，阿哈认证™·量子欢愉追击",
          ["算队友攻击（砂金•戏浪天赋/纵享惊涛）"], { extra: extra });
        this.onAttack(unit, "fua");
        return;
      }
      if (unit.uid === "1503") {
        this.event("skill", unit, label,
          ["群疗", "全队好活当赏 +15", "基础回能 30 × (1+ERR)"], { extra: extra });
        this.grantHaohuo(this.units.slice(), 15.0, "真珠战技");
        this.gainEnergy(unit, 30.0, false);
        this.onHealOrShield(unit, "真珠战技群疗");
        this.onAttack(unit, "skill");
        return;
      }
      if (unit.uid === "1513") {
        this.event("skill", unit, label,
          ["笑点 +4", "热意 +4", "旧梦淘金充能重置 6", "基础回能 30 × (1+ERR)"], { extra: extra });
        this.gainPunchline(4.0);
        unit.jiumeng = 6;
        this.gainFervor(unit, 4.0);
        this.gainEnergy(unit, 30.0, false);
        this.onAttack(unit, "skill");
        return;
      }
      if (unit.uid === "1304") {
        this.event("skill", unit, label, ["全队护盾", "基础回能 30 × (1+ERR)"], { extra: extra });
        this.gainEnergy(unit, 30.0, false);
        this.onHealOrShield(unit, "砂金战技护盾");
        this.onAttack(unit, "skill");
        return;
      }
      if (unit.uid === "1502") {
        unit.field = 3;
        this.event("skill", unit, label,
          ["结界 3 回合", "结界内自己普攻/战技 +3 笑点", "基础回能 30 × (1+ERR)"], { extra: extra });
        this.gainPunchline(3.0);
        this.gainEnergy(unit, 30.0, false);
        this.onAttack(unit, "skill");
        return;
      }
      if (unit.uid === "1501") {
        this.event("skill", unit, label,
          ["笑点 +4", "战技本身 0 能量", "同回合接强化普攻《百花齐放》"], { extra: extra });
        this.gainPunchline(4.0);
        this.event("enhanced_basic", unit, "百花齐放，胜者独享！",
          ["基础回能 40 × (1+ERR)"], { extra: extra });
        this.gainEnergy(unit, 40.0, false);
        this.onAttack(unit, "enhanced_basic");
        return;
      }
      if (unit.uid === "8009") {
        this.event("skill", unit, label,
          ["基础回能 30 × (1+ERR)", "天赋：+10 固定能量 +3 笑点"], { extra: extra });
        this.gainEnergy(unit, 30.0, false);
        this.onAttack(unit, "skill");
        return;
      }
      if (unit.uid === "1505") {
        this.event("skill", unit, label, ["笑点 +10", "基础回能 30 × (1+ERR)"], { extra: extra });
        this.gainPunchline(10.0);
        this.gainEnergy(unit, 30.0, false, false, "战技");
        this.onAttack(unit, "skill");
        return;
      }
      if (unit.uid === "1506") {
        this.event("skill", unit, label, ["笑点 +5", "隐藏分同步全队笑点"], { extra: extra });
        this.gainPunchline(5.0);
        this.onAttack(unit, "skill");
        return;
      }
      if (unit.uid === "1309") {
        this.event("skill", unit, label,
          ["基础回能 35（战技 30 + 行迹【模进乐段】5）× (1+ERR)"], { extra: extra });
        this.gainEnergy(unit, 35.0, false);
        this.onAttack(unit, "skill");
        return;
      }
      if (unit.uid === "1313") {
        const target = this.unitAt(this.resolveTargetSlot(unit, undefined));
        if (target !== null) {
          this.advanceUnit(target, 100.0, false);
          details.push(target.name + " 拉条 100%");
        }
        if (unit.equip.hasSundayLc && target !== null) {
          this.gainEnergy(unit, SUNDAY_LC_ENERGY, false);
          details.push("专武：能量 +" + fmt(SUNDAY_LC_ENERGY) + " × (1+ERR)");
        }
        this.event("skill", unit, label, details.concat(["基础回能 30 × (1+ERR)"]), { extra: extra });
        this.gainEnergy(unit, 30.0, false);
        this.onAttack(unit, "skill");
        return;
      }
      // 其他/自定义角色
      this.event("skill", unit, label, ["基础回能 30 × (1+ERR)"], { extra: extra });
      this.gainEnergy(unit, 30.0, false, false, "战技");
      this.onAttack(unit, "skill");
    }

    /** 银狼LV.999【无敌玩家】强化普攻（+5 笑点按她的战技同值处理）。 */
    doEnhancedBasic(unit, extra) {
      this.event("enhanced_basic", unit, unit.name + " 的强化普攻（无敌玩家）", ["笑点 +5"], { extra: extra });
      this.gainPunchline(5.0);
      this.onAttack(unit, "enhanced_basic");
    }

    doPearlEnhancedBasic(unit, extra) {
      unit.depth -= 1;
      this.event("enhanced_basic", unit, "真珠的强化普攻《行笔，幻造星月》",
        ["消耗 1 层【深度学习】", "群攻群疗", "基础回能 30 × (1+ERR)"], { extra: extra });
      this.gainEnergy(unit, 30.0, false);
      this.onHealOrShield(unit, "真珠强化普攻群疗");
      this.onAttack(unit, "enhanced_basic");
    }

    doAventurineFua(unit) {
      unit.fuaCount += 1;
      const segments = unit.eidolon >= 4 ? 10.0 : 7.0;
      const label = unit.eidolon >= 4
        ? "砂金的 10 段追加攻击（盲注满层，E4 +3 段）"
        : "砂金的 7 段追加攻击（盲注满层）";
      this.event("fua", unit, label,
        ["基础回能 " + fmt(segments, 0) + " × (1+ERR)", "全队护盾"]);
      this.gainEnergy(unit, segments, false);
      this.onHealOrShield(unit, "砂金追击护盾");
      this.onAttack(unit, "fua");
    }

    // ----------------------------- 终结技 ----------------------------- //

    ultCost(unit) {
      if (unit.energyType === "wishpower") return 8.0;
      return unit.uid === "1505" ? Math.min(240.0, Number(unit.maxSp)) : Number(unit.maxSp);
    }

    castUlt(unit) {
      if (this.depth > MAX_NEST) {
        this.warnings.push("嵌套层数超过上限，跳过一次终结技结算");
        return;
      }
      this.depth += 1;
      unit.castingUlt = true;
      try {
        // 先扣资源再结算效果：嵌套事件（艺术壁垒回能、额外回合出招）里如果
        // 资源还没扣，会被满能量再次触发一次终结技（踩过：同一次行动连开两个大）。
        const details = [];
        const energyBefore = unit.energy;
        let feiyRestore = 0.0;
        let feiyStacks = 0;
        if (unit.uid === "1505" && this.huanyuActive()) {
          feiyRestore = Math.max(0.0, unit.energy - Number(unit.maxSp));
          feiyStacks = unit.feiyUltBonus;
          unit.feiyUltBonus = 0;
        }
        if (unit.energyType === "wishpower") {
          unit.energy = Math.max(0.0, unit.energy - 8.0);
          details.push("消耗 8 愿力");
        } else if (unit.uid === "1506") {
          // 官方：无敌玩家期间无法开大，隐藏分在退出【无敌玩家】时才清空。
          details.push("【无敌玩家】期间隐藏分不清空");
        } else if (unit.uid === "1505") {
          unit.energy = Math.max(0.0, unit.energy - feiyRestore - this.ultCost(unit));
        } else {
          unit.energy = 0.0;
        }
        let resources = null;
        if (unit.uid === "1505") {
          details.push("释放前能量 " + fmt(energyBefore) + "，消耗 " + fmt(this.ultCost(unit), 0));
          resources = { energyBefore, energyCost: this.ultCost(unit) };
        }
        unit.ultCount += 1;
        this.event("ultimate", unit, unit.name + " 的终结技", details, { resourceChange: resources });

        if (unit.uid === "1511") {
          this.ult1511(unit);
        } else if (unit.uid === "1503") {
          this.ult1503(unit);
        } else if (unit.uid === "1513") {
          this.ult1513(unit);
        } else if (unit.uid === "1502") {
          this.ult1502(unit);
        } else if (unit.uid === "1501") {
          this.ult1501(unit);
        } else if (unit.uid === "8009") {
          this.ult8009(unit);
        } else if (unit.uid === "1506") {
          this.ult1506(unit);
        } else if (unit.uid === "1304") {
          this.ult1304(unit);
        } else if (unit.uid === "1505") {
          this.ult1505(unit, feiyRestore, feiyStacks);
        } else if (unit.uid === "1313") {
          this.ult1313(unit);
        } else if (unit.uid === "1309") {
          this.ult1309(unit);
        }

        this.checkBarrier(unit);

        // 通用遗器：风套自身拉条 25%、舞舞舞全队拉条
        if (unit.equip.windSet4) {
          this.event("note", unit, "晨昏交界的翔鹰", ["自身拉条 25%"]);
          this.advanceUnit(unit, 25.0, true);
        }
        if (unit.equip.danceS5) {
          this.event("note", unit, "舞！舞！舞！", ["我方全体拉条 " + fmt(this.cfg.dance_pct, 0) + "%"]);
          this.advanceAllies(unit, this.cfg.dance_pct);
        }
        // 标准能量开大返还 +5（吃 ERR）
        if (unit.energyType === "standard") {
          this.gainEnergy(unit, 5.0, false, false, "终结技返还");
        }
      } finally {
        unit.castingUlt = false;
        this.depth -= 1;
      }
    }

    ult1511(u) {
      u.trace2Used = false;
      const details = [];
      // nanoka E6：首次终结技拉条 100% 并获得 100 笑点（进池）。
      if (u.eidolon >= 6 && u.ultCount === 1) {
        this.advanceAha(100.0);
        this.gainPunchline(100.0);
        details.push("E6 首次终结技：【阿哈时刻】拉条 100% + 笑点 +100");
      } else {
        this.advanceAha(this.cfg.ult_advance_aha);
        details.push("【阿哈时刻】拉条 " + fmt(this.cfg.ult_advance_aha, 0) + "%");
      }
      this.event("note", u, "啊哈！宇宙笑点大爆炸", details);
      u.huanyu = 3;
      this.notes.push("星神★阿哈进入【欢愉万相】3 回合（笑点升格爽点，阿哈时刻结束返还 10%）");
      this.noteAscensionTraces(u);
      if (this.sanduActive()) {
        this.notes.push(
          "三赌牌局生效：全队速度 +" + fmt(this.cfg.sandu_team_spd_pct, 0) + "%（固有行迹【欢愉万相★三赌牌局】1级）"
        );
      }
      this.onAttack(u, "ultimate");
    }

    /** 各欢愉角色的固有行迹在【欢愉万相】开始时记一笔。数值效果在对应结算里。 */
    noteAscensionTraces(aha) {
      const level = aha.eidolon >= 2 ? 2 : 1;
      const crit = level === 2 ? 20 : 12;
      const defn = level === 2 ? 60 : 30;
      this.notes.push(
        "固有行迹【欢愉万相★无中生有】" + level + "级：返还消耗笑点的 10%，暴击率 +"
        + crit + "%，无视防御 " + defn + "%（伤害不模拟；笑点与好活当赏改称爽点与绝活共赏，不另做强化）"
      );
      for (let i = 0; i < this.units.length; i += 1) {
        const text = ASCENSION_ALLY_NOTES[this.units[i].uid];
        if (text) {
          this.notes.push(text);
        }
      }
    }

    ult1505(u, restore, stacks) {
      const aha = this.byUid("1511");
      const level2 = aha !== null && aha.eidolon >= 2;
      if (this.huanyuActive() || restore > EPS || stacks > 0) {
        const details = [];
        if (restore > EPS) {
          this.gainEnergy(u, restore, true, true, "书中折花·溢出恢复");
          details.push("书中折花：溢出能量 " + fmt(restore) + " 在开大后恢复（不触发天赋好活当赏）");
        }
        if (stacks > 0) {
          details.push(
            "书中折花：本次终结技倍率提高原倍率的 " + fmt(stacks * (level2 ? 150 : 75), 0) + "%（" + stacks + " 层，伤害不模拟）"
          );
        }
        if (restore <= EPS && stacks <= 0) {
          details.push("书中折花：本次没有可恢复的溢出能量");
        }
        details.push("伤害无视 " + (level2 ? 24 : 10) + "% 防御（伤害不模拟）");
        this.event("note", u, "欢愉万相★书中折花", details);
      }
      // E6：首次终结技固定 +120，之后每再施放 4 次终结技触发 1 次。
      if (u.eidolon >= 6 && (u.ultCount - 1) % 4 === 0) {
        this.event("note", u, "E6 少女，见浮生入梦", ["固定能量 +120"]);
        this.gainEnergy(u, 120.0, true, false, "E6");
      }
      this.onAttack(u, "ultimate");
    }

    ult1503(u) {
      this.grantHaohuo(this.units.slice(), 20.0, "真珠终结技");
      u.depth = 3;
      u.barrier = true;
      const count = this.elationCount();
      const pct = count === 1 ? 10.0 : count === 2 ? 15.0 : 30.0;
      const target = this.unitAt(this.aesteSlot);
      const details = [
        "全队好活当赏 +20",
        "【深度学习】充能 3",
        "欢愉 " + count + " 人 → 【美学底本】拉条 " + fmt(pct, 0) + "%",
      ];
      if (count >= 4) {
        details.push("4 欢愉：【美学底本】额外回合（+60 笑点，E2 +120）");
      }
      this.event("note", u, "鉴映灵魂的底色", details);
      if (target !== null) {
        this.advanceUnit(target, pct, false);
      }
      if (count >= 4 && target !== null) {
        const grant = u.eidolon >= 2 ? 120.0 : 60.0;
        const haohuo = u.eidolon >= 2 ? 60.0 : 30.0;
        this.doExtraTurn(target, "真珠终结技·【美学底本】额外回合", grant, haohuo);
      }
      if (u.eidolon >= 2) {
        const el = this.elationUnits();
        for (let i = 0; i < el.length; i += 1) {
          const x = el[i];
          if (x !== u && x.slot !== this.aesteSlot) {
            this.advanceUnit(x, pct, false);
          }
        }
      }
    }

    ult1513(u) {
      this.event("note", u, "胜局，凌越飓浪之上",
        ["笑点 +6", "热意 +8",
          "自身速度 +" + fmt(this.cfg.ult_spd_pct, 0) + "%（4 回合）",
          "基础回能返还 +5 × (1+ERR)"]);
      this.gainPunchline(6.0);
      this.gainFervor(u, 8.0);
      this.addTimedBuff(u, "pct", this.cfg.ult_spd_pct, 4, "胜局，凌越飓浪之上");
      this.onAttack(u, "ultimate");
    }

    ult1502(u) {
      const fixed = u.eidolon >= 1 ? 40.0 : 20.0;
      const details = ["笑点 +5", "【阿哈时刻】额外回合（计入 " + fmt(fixed, 0) + " 笑点，不消耗笑点池）"];
      if (this.huanyuActive()) {
        details.push("欢愉万相★心灵感应：【大吉大利】倍率提高原倍率的 20%；+12 固定能量 +10 笑点");
      }
      this.event("note", u, "爻光终结技", details);
      this.gainPunchline(5.0);
      this.doAha(true, fixed);
      if (this.huanyuActive()) {
        this.gainEnergy(u, 12.0, true);
        this.gainPunchline(10.0);
      }
    }

    ult1501(u) {
      let others = 0;
      for (let i = 0; i < this.units.length; i += 1) {
        if (this.units[i].elation && this.units[i] !== u) {
          others += 1;
        }
      }
      const bonus = others >= 3 ? 8.0 : others === 2 ? 4.0 : others >= 1 ? 2.0 : 0.0;
      const gain = 2.0 + bonus + (u.eidolon >= 4 ? 5.0 : 0.0);
      this.event("note", u, "火花终结技", ["其他欢愉 " + others + " 人 → 笑点 +" + fmt(gain, 0)]);
      this.gainPunchline(gain);
    }

    ult8009(u) {
      const target = this.unitAt(this.resolveTargetSlot(u, undefined));
      const details = ["笑点 +5"];
      const canCast = target !== null && ELATION_SKILL_UIDS[target.uid];
      const halo = Boolean(canCast && target !== null && this.huanyuActive() && target.uid === "1511");
      if (canCast && target !== null) {
        details.push(target.name + " 立刻施放 1 次欢愉技（好活当赏计入 20，不进笑点池）");
        if (halo) {
          details.push("欢愉万相★主角光环：先施放开拓者欢愉技，再触发阿哈欢愉技");
        }
      } else if (target !== null) {
        details.push(target.name + " 拉条 50%");
      }
      this.event("note", u, "开拓者•欢愉终结技", details);
      this.gainPunchline(5.0);
      if (target !== null) {
        if (canCast) {
          if (halo) {
            this.event("note", u, "欢愉万相★主角光环", [
              "开拓者欢愉技倍率提高原倍率的 200%（按最高好活当赏计算，伤害不模拟）",
              "阿哈欢愉技真实伤害改为该次的 20%，由敌方全体均分（伤害不模拟）",
              "终结技暴伤额外 +20% 且对全队生效（伤害不模拟）",
            ]);
            this.castElationSkill(u);
          }
          this.castElationSkill(target);
          // 1513 的举杯 / All in 自己已经记了 20，这里不再叠一次。
          if (target.uid !== "1513") {
            this.grantHaohuo(this.elationUnits(), 20.0, "开拓者终结技·计入笑点");
          }
        } else {
          this.advanceUnit(target, 50.0, false);
        }
      }
    }

    ult1506(u) {
      this.event("note", u, "无敌玩家，启动！",
        ["自身拉条 100%", "【无敌玩家】：接下来 3 次强化普攻"]);
      u.invincible = 3;
      this.advanceUnit(u, 100.0, true);
      // 行迹【隐藏关卡】：进入【无敌玩家】+20 隐藏分。
      this.event("note", u, "隐藏关卡", ["进入【无敌玩家】：隐藏分 +20"]);
      this.gainEnergy(u, 20.0, true);
      // 专武《欢迎来到银河城》：对自身开大获得 20 笑点（同步转换为隐藏分）。
      if (u.equip.hasWolfLc) {
        this.event("note", u, "欢迎来到银河城", ["对自身开大：笑点 +20 → 隐藏分同步"]);
        this.gainPunchline(WOLF_LC_PUNCHLINE);
      }
    }

    /** 退出【无敌玩家】：清空隐藏分（E1 保留 20%）。 */
    exitInvincible(u) {
      const total = u.energy + u.hiddenOverflow;
      const kept = u.eidolon >= 1 ? total * 0.2 : 0.0;
      u.energy = Math.min(Number(u.maxSp), kept);
      u.hiddenOverflow = this.huanyuActive() ? Math.max(0.0, kept - Number(u.maxSp)) : 0.0;
      this.event("note", u, "退出【无敌玩家】",
        ["隐藏分清空" + (u.eidolon < 1 ? "" : "（E1 保留 20%）")]);
    }

    /** 存护砂金 E1：开大后为全队提供护盾 → 触发阿哈行迹2。 */
    ult1304(u) {
      if (u.eidolon >= 1) {
        this.event("note", u, "E1 囚徒博弈", ["终结技全队护盾"]);
        this.onHealOrShield(u, "砂金 E1 终结技护盾");
      }
    }

    ult1313(u) {
      const target = this.unitAt(this.resolveTargetSlot(u, undefined));
      let gain = 40.0;
      if (target !== null) {
        gain = Math.max(40.0, 0.2 * Number(target.maxSp));
      }
      const details = [target !== null ? "指定目标回复 " + fmt(gain) + " 固定能量（不吃 ERR）" : "没有合法目标"];
      if (target !== null && u.equip.hasSundayLc) {
        details.push("专武：自身能量 +" + fmt(SUNDAY_LC_ENERGY) + " × (1+ERR)");
      }
      this.event("note", u, "星期日终结技", details);
      if (target !== null) {
        this.gainEnergy(target, gain, true, false, "星期日终结技");
        if (u.equip.hasSundayLc) {
          this.gainEnergy(u, SUNDAY_LC_ENERGY, false);
        }
      }
    }

    ult1309(u) {
      this.event("note", u, "知更鸟终结技",
        ["其他队友全体拉条 100%", "召唤 90 速【协奏】倒计时",
          "【协奏】期间本体不行动，倒计时归零时立即行动"]);
      for (let i = 0; i < this.units.length; i += 1) {
        const x = this.units[i];
        if (x !== u) {
          this.advanceUnit(x, 100.0, false);
        }
      }
      // 专武：开大时移除【歌咏】。
      if (u.equip.hasRobinLc) {
        u.lcErStacks = 0;
        u.lcEr = 0.0;
      }
      u.concerto = true;
      this.summons = [{ name: "【协奏】倒计时", spd: 90.0, rem_dist: DIST_BASE }];
    }

    // ----------------------------- 额外回合 ----------------------------- //

    doExtraTurn(unit, label, grantPunchline, grantHaohuo) {
      const gp = grantPunchline === undefined ? 0.0 : grantPunchline;
      const gh = grantHaohuo === undefined ? 0.0 : grantHaohuo;
      if (this.depth > MAX_NEST) {
        return;
      }
      this.depth += 1;
      this.extraDepth += 1;
      try {
        unit.extraCount += 1;
        const details = ["不重置行动条距离、不递减常规 Buff 回合数"];
        if (gp > 0) {
          details.push("笑点 +" + fmt(gp, 0) + "（额外回合结束时结算）");
        }
        if (gh > 0) {
          details.push("好活当赏 +" + fmt(gh, 0));
        }
        this.event("extra_turn", unit, label, details, { extra: true });
        if (gh > 0) {
          this.grantHaohuo([unit], gh, label);
        }
        if (gp > 0) {
          this.gainPunchline(gp);
        }
        this.doAction(unit, true);
        if (gp > 0) {
          const removed = Math.min(this.punchline, gp);
          this.punchline -= removed;
          let tail = "";
          if (this.huanyuActive()) {
            this.punchline += removed * 0.1;
            tail = "（欢愉万相返还 10%）";
          }
          this.event("note", unit, "额外回合笑点结算",
            ["回收 " + fmt(removed, 0) + " 笑点" + tail], { extra: true });
        }
        // 笑点的 10% 就是上面的欢愉万相返还，不再加一次。这里只把该次好活当赏收到 10%。
        if (gh > 0 && this.huanyuActive() && label.indexOf("真珠终结技") >= 0 && this.byUid("1503") !== null) {
          let kept = 0.0;
          for (let i = unit.haohuo.length - 1; i >= 0; i -= 1) {
            if (unit.haohuo[i].label === label) {
              kept = Number(unit.haohuo[i].count) * 0.1;
              unit.haohuo[i].count = kept;
              break;
            }
          }
          this.event("note", unit, "欢愉万相★跃然纸上", [
            "额外回合结束保留该次好活当赏的 10%（" + fmt(kept) + "）",
            "笑点的 10% 已记在欢愉万相返还里，不再另加",
          ], { extra: true });
        }
      } finally {
        this.extraDepth -= 1;
        this.depth -= 1;
      }
      for (const ally of this.units) {
        this.maybeUlt(ally);
      }
    }

    // ----------------------------- 【阿哈时刻】 ----------------------------- //

    doAha(isExtra, fixed) {
      const extra = Boolean(isExtra);
      const fx = fixed === undefined ? 0.0 : fixed;
      if (this.depth > MAX_NEST) {
        return;
      }
      this.depth += 1;
      if (extra) {
        this.extraDepth += 1;
      }
      try {
        const a = this.aha;
        a.in_turn = true;
        const casters = this.elationCasters();
        const recipients = this.elationUnits();
        if (extra) {
          this.ahaExtraCount += 1;
          this.event("aha_extra", null,
            "【阿哈时刻】额外回合（计入 " + fmt(fx, 0) + " 笑点）",
            ["不消耗笑点池", "不重置【阿哈时刻】行动条距离"],
            { kind: "aha", extra: true });
        } else {
          this.ahaNormalCount += 1;
          this.event("aha", null, "【阿哈时刻】触发",
            ["解除欢愉角色负面",
              "可施放欢愉技的角色各施放 1 次（不产笑点）",
              "无人可施放则 Let There Be Laughter",
              "回合结束消耗全部笑点"],
            { kind: "aha" });
        }
        if (casters.length) {
          for (let i = 0; i < casters.length; i += 1) {
            this.castElationSkill(casters[i]);
          }
        } else {
          this.event("note", null, "Let There Be Laughter",
            ["场上没有可施放欢愉技的角色",
              "保底效果（文档未给数值，不产笑点、不改笑点池）"],
            { kind: "aha", extra: extra });
        }
        if (extra) {
          if (fx > 0) {
            this.grantHaohuo(recipients, fx, "阿哈时刻额外回合");
          }
        } else {
          const consumed = this.punchline;
          this.punchline = 0.0;
          this.punchlineConsumed += consumed;
          const details = ["消耗笑点 " + fmt(consumed, 0)];
          if (this.huanyuActive()) {
            const refund = consumed * 0.1;
            this.punchline += refund;
            details.push("欢愉万相返还 10%（+" + fmt(refund) + "）");
          }
          this.event("note", null, "【阿哈时刻】笑点结算", details, { kind: "aha" });
          if (consumed > 0) {
            this.grantHaohuo(recipients, consumed, "阿哈时刻");
          }
        }
        // 阿哈回合（含额外回合）结束后可再次触发。仍要笑点从低于 40 再升上去。
        this.punchline40Done = false;
        this.ahaFlat = 0.0;
        // 1501 火花 E2：阿哈时刻每次结束立刻额外回合
        const spark = this.byUid("1501");
        const hasE2 = spark !== null && spark.eidolon >= 2;
        if (!extra) {
          a.rem_dist = Math.max(0.0, DIST_BASE - (DIST_BASE * a.pending) / 100.0);
        } else {
          a.rem_dist = Math.max(0.0, a.rem_dist - (DIST_BASE * a.pending) / 100.0);
        }
        a.pending = 0.0;
        a.in_turn = false;
        if (hasE2) {
          this.doExtraTurn(spark, "火花 E2·【阿哈时刻】结束额外回合");
        }
      } finally {
        if (extra) {
          this.extraDepth -= 1;
        }
        this.depth -= 1;
      }
      if (extra) {
        for (const ally of this.units) {
          this.maybeUlt(ally);
        }
      }
    }

    // ----------------------------- 战斗开始 ----------------------------- //

    battleStart() {
      this.opening = true;
      this.event("battle", null, "进入战斗",
        ["模拟窗口 [0, " + fmt(this.cfg.max_av, 0) + "] AV"],
        { kind: "system", name: "战斗" });
      this.notes.push("不模拟敌方行动、受击/击杀回能；欢愉技按参演编号排序（阿哈最后），绯英按编号判断转移。");
      this.aha.rem_dist = Math.max(0.0, DIST_BASE - (DIST_BASE * this.cfg.aha_advance_pct) / 100.0);
      let ahaExtraFromTech = false;
      if (this.cfg.use_tech) {
        for (let i = 0; i < this.units.length; i += 1) {
          const unit = this.units[i];
          if (unit.uid === "1511") {
            this.event("tech", unit, "秘技《ABRACADABRA！》",
              ["【阿哈时刻】获得 1 个计入 20 笑点的额外回合"]);
            ahaExtraFromTech = true;
          } else if (unit.uid === "1503") {
            unit.depth = 2;
            unit.barrier = true;
            this.event("tech", unit, "真珠秘技",
              ["【深度学习】2 层", "全队好活当赏 +20", "【艺术壁垒】武装"]);
            this.grantHaohuo(this.units.slice(), 20.0, "真珠秘技");
          } else if (unit.uid === "1513") {
            this.event("tech", unit, "砂金•戏浪秘技", ["热意 +2", "全队好活当赏 +20"]);
            this.gainFervor(unit, 2.0);
            this.grantHaohuo(this.units.slice(), 20.0, "砂金•戏浪秘技");
          } else if (unit.uid === "1502") {
            this.event("tech", unit, "爻光秘技：自动施放战技", ["结界 3 回合（不吃战技点）"]);
            this.doSkill(unit, false);
          } else if (unit.uid === "1505") {
            this.event("tech", unit, "绯英秘技", ["自身好活当赏 +20"]);
            this.grantHaohuo([unit], 20.0, "绯英秘技");
          } else if (unit.uid === "1309") {
            this.event("tech", unit, "知更鸟秘技：酣醉序曲",
              ["每波次开始 +5 能量（本工具=战斗开始一次）"]);
            this.gainEnergy(unit, 5.0, false);
          }
        }
        // 秘技给的额外回合等全部秘技结算完再走（口径更接近进战顺序）
        if (ahaExtraFromTech) {
          this.doAha(true, 20.0);
        }
      }

      // 战斗开始触发的行迹/专武回能（与秘技无关）
      for (let i = 0; i < this.units.length; i += 1) {
        const unit = this.units[i];
        if (unit.uid === "1304") {
          this.event("note", unit, "行迹【热手】", ["战斗开始全队护盾"]);
          this.onHealOrShield(unit, "砂金【热手】开局护盾");
        }
        if (unit.uid === "1313") {
          this.event("note", unit, "行迹【崇高拂尘】", ["战斗开始能量 +25"]);
          this.gainEnergy(unit, 25.0, false);
        }
        if (unit.equip.hasYaoLc) {
          this.event("note", unit, "当她决定看见", ["每波次开始：固定能量 +15"]);
          this.gainEnergy(unit, YAO_LC_WAVE_ENERGY, true, false, "专武");
        }
      }

      for (let i = 0; i < this.units.length; i += 1) {
        this.units[i].initialSpd = this.unitSpd(this.units[i]);
      }
      this.ahaInitialSpd = this.ahaSpd();

      for (let i = 0; i < this.units.length; i += 1) {
        const unit = this.units[i];
        if (unit.equip.vonwacq) {
          if (unit.initialSpd >= 120.0) {
            this.event("note", unit, "生命的翁瓦克", ["速度 ≥ 120：开局拉条 40%"]);
            this.advanceUnit(unit, 40.0, false);
          } else {
            this.event("note", unit, "生命的翁瓦克",
              ["速度 " + fmt(unit.initialSpd, 1) + " < 120：开局拉条不触发"]);
          }
        }
        if (unit.equip.godJoy) {
          this.event("note", unit, "神的瞬息欢愉",
            ["速度 +6% 已计入",
              "开局 40% 拉条需要欢愉度 ≥ 40%（本工具不模拟欢愉度，因此不拉条）"]);
        }
        if (unit.initAdv > 0) {
          this.advanceUnit(unit, unit.initAdv, false);
        }
      }

      const aha = this.byUid("1511");
      if (aha !== null) {
        if (this.cfg.trace3_advance) {
          this.event("note", aha, "行迹3【盒中蕴藏的世界】", ["进战自身拉条 30%"]);
          this.advanceUnit(aha, 30.0, false);
        }
        if (aha.eidolon >= 1 && this.cfg.e1_wishpower > 0) {
          this.event("note", aha, "E1 开局回能", ["愿力 +" + fmt(this.cfg.e1_wishpower, 0)]);
          this.gainWishpower(aha, this.cfg.e1_wishpower);
        }
        if (aha.initialSpd >= 150.0) {
          aha.notes.push("实战速度 ≥ 150：欢愉度 +150%");
        } else if (aha.initialSpd >= 125.0) {
          aha.notes.push("实战速度 ≥ 125：欢愉度 +120%");
        }
        if (aha.notes.length) {
          this.event("note", aha, "行迹3 速度阈值", aha.notes.slice());
        }
      }

      this.opening = false;
      for (const unit of this.units) {
        this.maybeUlt(unit);
      }
    }

    // ----------------------------- 主循环 ----------------------------- //

    nextActor() {
      let best = null;
      let bestAv = 0.0;
      for (let i = 0; i < this.units.length; i += 1) {
        const unit = this.units[i];
        if (unit.concerto) {
          continue;
        }
        const av = this.av + unit.remDist / this.unitSpd(unit);
        if (best === null || av < bestAv) {
          best = ["unit", unit];
          bestAv = av;
        }
      }
      const a = this.aha;
      let av = this.av + a.rem_dist / this.ahaSpd();
      if (best === null || av < bestAv) {
        best = ["aha", null];
        bestAv = av;
      }
      for (let i = 0; i < this.summons.length; i += 1) {
        const summon = this.summons[i];
        av = this.av + summon.rem_dist / Number(summon.spd);
        if (best === null || av < bestAv) {
          best = ["summon", summon];
          bestAv = av;
        }
      }
      return [best, bestAv];
    }

    /** 时间前进到 av：所有跑条单位的剩余距离按各自速度同步消耗。 */
    advanceTime(av) {
      const dt = av - this.av;
      if (dt > 0) {
        for (let i = 0; i < this.units.length; i += 1) {
          const unit = this.units[i];
          if (unit.concerto) {
            continue;
          }
          unit.remDist = Math.max(0.0, unit.remDist - dt * this.unitSpd(unit));
        }
        const a = this.aha;
        a.rem_dist = Math.max(0.0, a.rem_dist - dt * this.ahaSpd());
        for (let i = 0; i < this.summons.length; i += 1) {
          const summon = this.summons[i];
          summon.rem_dist = Math.max(0.0, summon.rem_dist - dt * Number(summon.spd));
        }
      }
      this.av = av;
    }

    run() {
      this.battleStart();
      let guard = 0;
      while (guard < MAX_LOOP) {
        guard += 1;
        const [actor, av] = this.nextActor();
        if (actor === null) {
          break;
        }
        if (av > this.cfg.max_av + EPS) {
          break;
        }
        this.advanceTime(av);
        const kind = actor[0];
        const obj = actor[1];
        if (kind === "unit") {
          this.doTurn(obj);
        } else if (kind === "aha") {
          this.doAha(false, 0.0);
        } else {
          this.doSummon(obj);
        }
      }
      return this.buildOutput();
    }

    doTurn(unit) {
      this.depth += 1;
      try {
        unit.inTurn = true;
        unit.turnCount += 1;
        // 回合开始
        if (unit.uid === "1313" && unit.eidolon >= 4) {
          this.event("note", unit, "E4 雕塑的卷首语", ["回合开始能量 +8"]);
          this.gainEnergy(unit, 8.0, false);
        }
        if (unit.uid === "1511") {
          if (unit.huanyu > 0) {
            unit.huanyu -= 1;
            if (unit.huanyu === 0) {
              this.event("note", unit, "【欢愉万相】结束", []);
            }
          }
          if (unit.sigLcCd > 0) {
            unit.sigLcCd -= 1;
          }
        }
        if (this.lingshiSlot !== null && unit.slot === this.lingshiSlot) {
          const aha = this.byUid("1511");
          if (aha !== null) {
            this.event("note", unit, "【「欢愉」令使】回合开始", ["星神★阿哈愿力 +1"]);
            this.gainWishpower(aha, 1.0);
          }
        }
        this.doAction(unit, false);
        this.turnEnd(unit);
      } finally {
        unit.inTurn = false;
        this.depth -= 1;
      }
    }

    turnEnd(unit) {
      // Buff 递减（额外回合不走这里）
      let kept = [];
      let changed = false;
      for (let i = 0; i < unit.timed.length; i += 1) {
        const buff = unit.timed[i];
        if (buff.turns === null) {
          kept.push(buff);
          continue;
        }
        buff.turns = buff.turns - 1;
        if (buff.turns > 0) {
          kept.push(buff);
        } else {
          changed = true;
        }
      }
      unit.timed = kept;
      if (changed && unit.elation) {
        this.notes.push(unit.name + " 的速度加成到期，【阿哈时刻】速度已重算");
      }
      // 好活当赏递减
      kept = [];
      const expired = [];
      for (let i = 0; i < unit.haohuo.length; i += 1) {
        const item = unit.haohuo[i];
        item.turns = item.turns - 1;
        if (item.turns > 0) {
          kept.push(item);
        } else {
          expired.push(item);
        }
      }
      unit.haohuo = kept;
      const fei = this.byUid("1505");
      if (fei !== null && fei !== unit) {
        for (const item of expired) {
            const copied = Number(item.count) * (fei.eidolon >= 2 ? 1.0 : 0.5);
            this.event("note", fei, "开不败·好活当赏转移",
              [unit.name + " 状态结束 → 好活当赏 +" + fmt(copied)]);
            this.grantHaohuo([fei], copied, "开不败");
        }
      }
      // 1502 结界递减
      if (unit.uid === "1502" && unit.field > 0) {
        unit.field -= 1;
        if (unit.field === 0) {
          this.event("note", unit, "结界结束", []);
        }
      }
      // 行动条重置（挂起的自身拉条在这里生效）
      unit.remDist = Math.max(0.0, DIST_BASE - (DIST_BASE * unit.pendingAa) / 100.0);
      unit.pendingAa = 0.0;
    }

    doSummon(summon) {
      this.event("summon", null, summon.name + " 归零", ["【协奏】状态结束"], { kind: "summon", name: summon.name });
      this.summons = this.summons.filter((s) => s !== summon);
      const robin = this.byUid("1309");
      if (robin !== null && robin.concerto) {
        robin.concerto = false;
        robin.remDist = 0.0;
        this.event("note", robin, "退出【协奏】", ["立即行动"]);
        this.doTurn(robin);
      }
    }

    // ----------------------------- 输出 ----------------------------- //

    buildOutput() {
      const ahaSpdNow = this.ahaSpd();
      const el = this.elationUnits();
      const ranked = el.slice().sort((a, b) => this.unitSpd(b) - this.unitSpd(a));
      const ranks = [];
      let weighted = 0.0;
      for (let i = 0; i < 4; i += 1) {
        if (i < ranked.length) {
          const unit = ranked[i];
          const spd = this.unitSpd(unit);
          const add = AHA_WEIGHTS[i] * spd;
          weighted += add;
          ranks.push({
            rank: i + 1,
            name: unit.name,
            slot: unit.slot,
            speed: spd,
            weight: AHA_WEIGHTS[i],
            divisor: AHA_DIVISORS[i],
            add: add,
          });
        }
      }
      const base = this.ahaBaseValue();
      const raw = base + weighted + this.ahaFlat;
      const ahaOut = {
        useAeonAha: Boolean(this.useAeonAha),
        base: base,
        baseSpd: this.ahaBaseSpd,
        lcBaseSpd: this.ahaLcBaseSpd,
        weighted: weighted,
        flatBonus: this.ahaFlat,
        pct: this.cfg.aha_spd_pct,
        raw: raw,
        speed: this.ahaInitialSpd,
        finalSpeed: ahaSpdNow,
        singleAV: this.ahaInitialSpd > 0 ? DIST_BASE / this.ahaInitialSpd : 0.0,
        singleFinalAV: ahaSpdNow > 0 ? DIST_BASE / ahaSpdNow : 0.0,
        triggerCount: this.ahaNormalCount,
        extraTriggerCount: this.ahaExtraCount,
        ranks: ranks,
        formula: this.ahaFormula(base, ranks, raw),
      };
      const counts = {};
      for (let i = 0; i < AV_NODES.length; i += 1) {
        const node = AV_NODES[i];
        let n = 0;
        for (let j = 0; j < this.timeline.length; j += 1) {
          const ev = this.timeline[j];
          if ((ev.type === "aha" || ev.type === "aha_extra") && ev.av <= node.av + EPS) {
            n += 1;
          }
        }
        counts[String(Math.trunc(node.av))] = n;
      }
      const key = fmt(this.cfg.max_av, 0);
      let maxCount = 0;
      for (let j = 0; j < this.timeline.length; j += 1) {
        const ev = this.timeline[j];
        if ((ev.type === "aha" || ev.type === "aha_extra") && ev.av <= this.cfg.max_av + EPS) {
          maxCount += 1;
        }
      }
      counts[key] = maxCount;
      ahaOut.counts = counts;

      const unitsOut = [];
      for (let i = 0; i < this.units.length; i += 1) {
        const unit = this.units[i];
        const spd = this.unitSpd(unit);
        unitsOut.push({
          slot: unit.slot,
          id: unit.uid,
          name: unit.name,
          elation: unit.elation,
          energyType: unit.energyType,
          energyName: unit.energyName,
          baseSpd: unit.baseSpd,
          lcBaseSpd: unit.lcBaseSpd,
          traceSpd: unit.traceSpd,
          permPct: unit.permPct,
          permFlat: unit.permFlat,
          buffPct: unit.buffPct,
          buffFlat: unit.buffFlat,
          err: unit.err,
          eidolon: unit.eidolon,
          maxSp: unit.maxSp,
          initAdv: unit.initAdv,
          initialEnergy: unit.initialEnergy,
          targetSlot: unit.targetSlot,
          rotation: unit.rotation,
          equipment: Object.assign({}, unit.equip),
          initialSpd: unit.initialSpd,
          finalSpd: spd,
          singleAV: spd > 0 ? DIST_BASE / spd : 0.0,
          deltaVsAha: spd - this.ahaInitialSpd,
          fasterThanAha: spd > this.ahaInitialSpd + 0.05,
          actionCount: unit.actionCount,
          turnCount: unit.turnCount,
          ultCount: unit.ultCount,
          extraTurnCount: unit.extraCount,
          fuaCount: unit.fuaCount,
          finalEnergy: unit.energy,
          finalRemDist: unit.remDist,
          mechanics: this.unitMechanics(unit),
          notes: unit.notes.slice(),
        });
      }

      const unitActions = {};
      for (let i = 0; i < this.units.length; i += 1) {
        unitActions[this.units[i].name] = this.units[i].actionCount;
      }
      unitActions["【阿哈时刻】"] = this.ahaNormalCount + this.ahaExtraCount;

      const aha1511 = this.byUid("1511");
      return {
        maxAV: this.cfg.max_av,
        aha: ahaOut,
        units: unitsOut,
        timeline: this.timeline,
        summary: {
          totalEvents: this.timeline.length,
          unitActions: unitActions,
          ahaTriggers: this.ahaNormalCount,
          ahaExtraTriggers: this.ahaExtraCount,
          punchlineGranted: this.punchlineGranted,
          punchlineConsumed: this.punchlineConsumed,
          truncated: this.truncated,
        },
        resources: {
          punchline: this.punchline,
          ahaFlatBonus: this.ahaFlat,
          huanyuWanxiangTurns: aha1511 !== null ? aha1511.huanyu : null,
          sanduActive: this.sanduActive(),
          lingshiSlot: this.lingshiSlot,
          aesteSlot: this.aesteSlot,
        },
        warnings: this.warnings.slice(),
        notes: this.notes.slice(),
      };
    }

    ahaFormula(base, ranks, raw) {
      let bits;
      if (ranks.length) {
        bits = ranks.map((r) => fmt(r.speed, 1) + "/" + r.divisor).join(" + ");
      } else {
        bits = "无欢愉队友";
      }
      const pctText = this.cfg.aha_spd_pct ? " × (1+" + fmt(this.cfg.aha_spd_pct, 0) + "%)" : "";
      const flatText = this.ahaFlat ? " + " + fmt(this.ahaFlat, 1) : "";
      return (
        "基础 " + fmt(base, 1) + " + " + bits + flatText + " = " + fmt(raw) + pctText + " → " + fmt(this.ahaInitialSpd)
      );
    }

    unitMechanics(unit) {
      let out = {};
      if (unit.uid === "1511") {
        out = {
          wishpower: unit.energy,
          wishpowerTotal: unit.energyTotal,
          huanyuWanxiangTurns: unit.huanyu,
          trace2Used: unit.trace2Used,
          lingshiSlot: this.lingshiSlot,
        };
      } else if (unit.uid === "1503") {
        out = {
          depthCharges: unit.depth,
          barrierArmed: unit.barrier,
          aesteSlot: this.aesteSlot,
        };
      } else if (unit.uid === "1513") {
        out = {
          fervor: unit.fervor,
          jiumengLeft: unit.jiumeng,
          allInArmed: unit.allIn,
        };
      } else if (unit.uid === "1304") {
        out = { blindStacks: unit.blind };
      } else if (unit.uid === "1502") {
        const bonus = this.huanyuActive() ? 0.20 : 0.0;
        out = {
          fieldTurns: unit.field,
          dajiElationDamage: 0.20 * (1.0 + bonus),
          mindLinkActive: this.huanyuActive(),
        };
      } else if (unit.uid === "1505") {
        out = {
          energySinceFuA: unit.feiyTotal,
          energyOverflow: Math.max(0.0, unit.energy - Number(unit.maxSp)),
          feiyUltBonus: unit.feiyUltBonus,
        };
      } else if (unit.uid === "1506") {
        out = {
          invincibleTurns: unit.invincible,
          hiddenOverflow: unit.hiddenOverflow,
        };
      } else if (unit.uid === "1309") {
        out = {
          concerto: unit.concerto,
          lcErStacks: unit.lcErStacks,
        };
      } else if (unit.uid === "1313") {
        out = { emblem: false };
      }
      out.ascensionTrace = ASCENSION_TRACE_NAME[unit.uid] || null;
      out.ascensionActive = Boolean(out.ascensionTrace) && this.huanyuActive();
      out.haohuo = unit.haohuo.map((item) => ({
        turns: item.turns,
        count: item.count,
        label: item.label,
      }));
      return out;
    }
  }

  // ----------------------------------------------------------------------- //
  // 接口
  // ----------------------------------------------------------------------- //

  /** 角色表、装备开关、可调参数、行动值节点 —— 给界面建表用。 */
  function catalog(payload) {
    const roster = ROSTER_ORDER.map((uid) => {
      const spec = ROSTER[uid];
      return {
        id: uid,
        aliases: (spec.aliases || []).slice(),
        name: spec.name,
        path: spec.path,
        elation: Boolean(spec.elation),
        baseSpd: spec.baseSpd,
        traceSpd: spec.traceSpd,
        lcBaseSpd: spec.lcBaseSpd,
        maxSp: spec.maxSp,
        energy: spec.energy,
        energyName: spec.energyName,
        rotation: spec.rotation,
        mechanics: (spec.mechanics || []).slice(),
      };
    });
    return {
      roster: roster,
      equipment: EQUIPMENT_META,
      config: CONFIG_META,
      avNodes: AV_NODES,
      cycles: {
        distBase: DIST_BASE,
        cycle0AV: CYCLE0_AV,
        cycleAV: CYCLE_AV,
      },
      ahaWeights: [0, 1, 2, 3].map((i) => ({
        rank: i + 1,
        weight: AHA_WEIGHTS[i],
        divisor: AHA_DIVISORS[i],
      })),
      defaultTeam: [
        { id: "1511", elation: true },
        { id: "1513", elation: true },
        { id: "1503", elation: true, targetSlot: 0 },
        { id: "1501", elation: true },
      ],
    };
  }

  /** 跑 4 人小队 + 【阿哈时刻】的行动值排轴。 */
  function simulate(payload) {
    return new Sim(payload || {}).run();
  }

  /** 速度阈值反推：N 轮 M 动（含累计拉条）需要的最低实战速度。 */
  function threshold(payload) {
    const p = payload || {};
    let targetAv = num(p, "targetAV", 0.0, 0.0, NUM_LIMIT);
    const tIn = p.t;
    if (targetAv <= 0 && tIn !== undefined && tIn !== null && tIn !== "") {
      const tVal = Math.trunc(num(p, "t", 0.0, 0.0, 1000.0));
      targetAv = CYCLE0_AV + tVal * CYCLE_AV;
    }
    if (targetAv <= 0) {
      throw new Error("需要 targetAV（或 t）指定目标行动值");
    }
    const actions = num(p, "actions", 2.0, 1.0, 200.0);
    const advancePct = num(p, "advancePct", 0.0, 0.0, 10000.0);
    const effective = actions - advancePct / 100.0;
    const required = (DIST_BASE * effective) / targetAv;
    return {
      targetAV: targetAv,
      t: cycleOf(targetAv),
      actions: actions,
      advancePct: advancePct,
      effectiveTurns: effective,
      distance: DIST_BASE,
      requiredSpeed: required,
      cycleBoundary: CYCLE0_AV + cycleOf(targetAv) * CYCLE_AV,
      formula:
        "10000 × (" + fmt(actions, 0) + " − " + fmt(advancePct, 0) + "%) ÷ " + fmt(targetAv, 0) +
        " = " + fmt(required),
      text:
        fmt(targetAv, 0) + " AV 内打 " + fmt(actions, 0) + " 动" +
        (advancePct ? "（累计拉条 " + fmt(advancePct, 0) + "%）" : "") +
        "需要 " + fmt(required) + " 速",
    };
  }

  function createApi() {
    const ACTIONS = {
      catalog: catalog,
      simulate: simulate,
      threshold: threshold,
    };
    return {
      /** 同步执行一个动作；名字和 Python 的 @api(...) 一一对应。 */
      call(action, payload) {
        const handler = ACTIONS[action];
        if (typeof handler !== "function") {
          throw new Error("未知动作 " + pyRepr(action));
        }
        return handler(payload || {});
      },
    };
  }

  return {
    createApi: createApi,
    catalog: catalog,
    simulate: simulate,
    threshold: threshold,
    // 调试/自检用：把关键内部函数露出来，方便和 Python 对拍。
    _internals: {
      fmt: fmt,
      cycleOf: cycleOf,
      Sim: Sim,
    },
  };
});
