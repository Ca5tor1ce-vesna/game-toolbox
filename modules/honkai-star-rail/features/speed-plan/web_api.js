/* 崩坏：星穹铁道 配速查询 —— 浏览器端实现（`modules/honkai-star-rail/features/speed-plan/api.py` 的逐位移植）。
 *
 * 这是一个**经典脚本**：用 <script src> 直接加载会挂到 window.GT_WEB_API；
 * 用 node 时走 module.exports，两边共用同一份代码。
 *
 *   const api = window.GT_WEB_API.createApi(data, storage);
 *   api.call("plan", payload);   // 同步返回，不是 Promise
 *
 * data    = {characters, lightcones, relic_sets, modes, sources}
 * storage = {load: () => object, save: (obj) => void}
 *           「我的配装」用它读写；不传就用内存对象。
 *           **刻意不直接用 localStorage**：node 里没有 window.localStorage，
 *           浏览器里由调用方（网页版外壳）注入一个包了 localStorage 的 storage。
 *
 * 速度合成（游戏规则）
 * --------------------
 *     最终速度 = 基础速度 × (1 + 速度百分比之和) + 固定速度之和
 *
 * 百分比只作用在**基础速度**上，固定速度加在最后 —— 顺序搞反结果会差很多。
 *
 * 需求速度（与「配速排轴」「阿哈时刻配速」同一套模型）
 * ----------------------------------------------------
 *     需求速度 = (动数 × 10000 − 拉条总量) ÷ (150 + T × 100)
 *     拉条总量 = Σ(拉条% × 10000)
 *
 * 拉条来源：风套 4 件套每次开大 25%、舞！舞！舞！每次开大全队 16~24%（看叠影）、
 * 翁瓦克（生命的翁瓦克）进战一次 40%、以及自定义。
 *
 * 数据来源
 * --------
 * 角色基础速度、光锥/星魂/技能/行迹/遗器的速度与拉条效果，全部由
 * `tools/import_hsr_data.py` 从米游社官方图鉴 + StarRailRes 抓取并**自动抽取**。
 * 自动抽取出来的是「候选」，条件是否成立要看实战，所以界面上要你自己勾选 ——
 * 工具负责把原文摆在你面前，不替你判断。
 *
 * 移植注意事项（这些地方和 Python 的差异最容易出结果不一致）
 * ----------------------------------------------------------
 *   * Python 的 `or` 返回「第一个真值，否则最后一个操作数」，JS 的 `||` 只返回布尔语义上
 *     的真值，所以凡是原文用 `or` 兜底的地方（`char.get("traceSpeed") or 0`）都要用
 *     pyOr() 逐字照抄，否则 0 和 None 的走向会不一样。
 *   * 数值比较必须都在 IEEE754 double 上做：**不做任何额外 round**，
 *     格式化交给界面（ui.js 里自己 toFixed）。
 *   * 排序键是 Python 元组比较，JS 只能自己写比较器（见 cmpBy）。
 *   * 推荐去重用的 `round(speed, 1)` 是 Python 的**银行家舍入**（.5 取偶），
 *     和 JS 的 Math.round（.5 远离零）在边界上不同，所以自己实现了 pyRound1()。
 */
(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  if (root) {
    root.GT_WEB_API = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const DEFAULT_CYCLES = { firstCycleAV: 150, cycleAV: 100, distancePerAction: 10000 };
  const SPEED_BOOTS_FLAT = 25; // 遗器主词条「速度」鞋

  const CONDITION_MARKERS = ["若", "当", "大于", "小于", "每", "层", "触发", "持续", "叠影", "受到", "消灭"];
  const PRESET_KEY = "speed-plan-presets";

  // ------------------------------------------------------------------------- #
  // 通用小工具（都是为了让 JS 的语义和 Python 对上）
  // ------------------------------------------------------------------------- #

  /** Python 的 `or`：返回第一个真值，全为假值时返回最后一个操作数。 */
  function pyOr() {
    let last = arguments[0];
    for (let i = 0; i < arguments.length; i += 1) {
      last = arguments[i];
      if (last) return last;
    }
    return last;
  }

  /**
   * Python 的 bool()：JS 里字符串 "0"/"false" 是真值、0 和 "" 是假值，
   * 数字和对象/数组两边一致，所以只要把数值 0 之外的情况交给 JS 的真值判断即可。
   * （效果数据是导入器写出来的纯 JSON，没有 "false" 这种字符串字段。）
   */
  function pyBool(value) {
    return Boolean(value);
  }

  function isList(value) {
    return Object.prototype.toString.call(value) === "[object Array]";
  }

  function isDict(value) {
    return value !== null && typeof value === "object" && !isList(value);
  }

  /** Python 的 f"{value!r}"：只用于报错文案。 */
  function pyRepr(value) {
    if (value === undefined || value === null) return "None";
    if (typeof value === "string") return "'" + value + "'";
    if (typeof value === "boolean") return value ? "True" : "False";
    return String(value);
  }

  /** Python 的 str(value)：None → "None"。 */
  function pyStr(value) {
    return value === undefined || value === null ? "None" : String(value);
  }

  /**
   * 把 toPrecision(精度) 给出的数字串摊成十进制数字串。
   * toPrecision 的写法不固定：可能是 '1.65400e+2'（有指数），也可能是
   * '0.0000123000'（小数形式，没有指数）——后一种必须靠数前导零才能知道首位在哪，
   * 否则 1e-5 会被当成 0.0000123 输出（这是移植时踩过的坑）。
   *
   * 返回 { digits, exp }：数值 = 0.digits × 10^(exp+1)，
   * 也就是 digits 的第一位是十进制的第 exp+1 位（1 表示个位）。
   */
  function decomposePrecision(text) {
    const parts = String(text).split("e");
    const mantissa = parts[0];
    const exp = parts.length > 1 ? parseInt(parts[1], 10) : 0;
    const dot = mantissa.indexOf(".");
    const intLen = dot === -1 ? mantissa.length : dot;
    const all = dot === -1 ? mantissa : mantissa.slice(0, dot) + mantissa.slice(dot + 1);

    let lead = 0;
    while (lead < all.length - 1 && all.charAt(lead) === "0") lead += 1;
    const digits = all.slice(lead).replace(/0+$/, "") || "0";
    const exp10 = exp + intLen - 1 - lead; // 首位在十进制的第 exp10+1 位
    return { digits: digits, exp: exp10 };
  }

  /**
   * Python f-string 的 `:g`（默认精度 6）：按 6 位有效数字取最短表示，
   * 指数小于 -4 或大于等于精度时用科学计数法，否则定点输出并去掉尾零。
   * 用 JS 的 toPrecision 拿到合法十进制串再规范化，避免手写 dtoa 引入误差。
   */
  function pyG(value) {
    const x = Number(value);
    if (Number.isNaN(x)) return "nan";
    if (x === Infinity) return "inf";
    if (x === -Infinity) return "-inf";
    if (x === 0) return Object.is(x, -0) ? "-0" : "0";

    const negative = x < 0;
    const { digits, exp } = decomposePrecision(Math.abs(x).toPrecision(6));
    const pointPos = exp + 1; // 小数点落在 digits 的第几位之前

    let out;
    if (exp < -4 || exp >= 6) {
      const tail = digits.slice(1);
      out = digits.slice(0, 1) + (tail ? "." + tail : "") + "e" + (exp < 0 ? "-" : "+") + String(Math.abs(exp)).padStart(2, "0");
    } else if (pointPos <= 0) {
      out = "0." + "0".repeat(-pointPos) + digits;
    } else if (pointPos >= digits.length) {
      out = digits + "0".repeat(pointPos - digits.length);
    } else {
      out = digits.slice(0, pointPos) + "." + digits.slice(pointPos);
    }
    return negative ? "-" + out : out;
  }

  /**
   * 把一个 double 摊成十进制数字串。
   *
   * 用 toPrecision(20)：先按 Python 的 repr（最短表示）拿到它，再往后补到 20 位有效数字，
   * 这样既保留了 .5 这类「十进制上整齐」的边界（round(0.05, 1) == 0.1），
   * 又能拿到足够多的后续位来判断是不是真的恰好一半
   * （2.675 的真实二进制值略小于 2.675，所以 format(2.675, ".2f") == "2.67"）。
   *
   * 返回 { negative, digits, pointPos }，含义是 0.digits × 10^pointPos。
   */
  function decimalParts(value) {
    const x = Number(value);
    const negative = x < 0 || Object.is(x, -0);
    const text = Math.abs(x).toPrecision(20);
    const parts = text.split("e");
    const mantissa = parts[0];
    const exp = parts.length > 1 ? parseInt(parts[1], 10) : 0;
    const dot = mantissa.indexOf(".");
    const intLen = dot === -1 ? mantissa.length : dot;
    const all = dot === -1 ? mantissa : mantissa.slice(0, dot) + mantissa.slice(dot + 1);
    // 0.digits × 10^pointPos：小数点前有 intLen 位，每去掉一个前导零首位就往下挪一位。
    // 注意 pointPos 必须在去掉**尾**零之前算好（1 写成 1.000…0 时位数会变）。
    let lead = 0;
    while (lead < all.length - 1 && all.charAt(lead) === "0") lead += 1;
    const pointPos = exp + intLen - lead;
    const digits = all.slice(lead).replace(/0+$/, "") || "0";
    return { negative: negative, digits: digits, pointPos: pointPos };
  }

  /**
   * 在十进制数字串的第 `places` 位小数上做**银行家舍入**（.5 取偶）。
   *
   * 做法：先把数字串右补零，让小数点正好落在 digits.length - places 处，
   * 于是「保留前 keepLen 位、看第 keepLen 位决定是否进位」。
   * 返回 { digits, exp }，数值 = 0.digits × 10^(exp+1)。
   */
  function decimalRound(digits, pointPos, places) {
    let padded = digits;
    const needed = pointPos + places; // 小数点落在 padded 的第 needed 位之后
    if (needed > padded.length) padded = padded + "0".repeat(needed - padded.length);
    // 保留 needed 位（整数部分 + 要保留的小数位），后面那位决定是否进位
    const keepLen = needed > 0 ? needed : 0;

    const head = padded.charCodeAt(keepLen) - 48;
    const restNonZero = /[1-9]/.test(padded.slice(keepLen + 1));
    let roundUp = false;
    if (head > 5) roundUp = true;
    else if (head === 5) {
      // 恰好一半：取偶（Python 的「四舍六入五取偶」）
      roundUp = restNonZero || (keepLen > 0 ? (padded.charCodeAt(keepLen - 1) - 48) % 2 === 1 : false);
    }

    let kept = padded.slice(0, keepLen);
    let newPointPos = pointPos;
    if (roundUp) {
      // 手工进位，避免大整数丢精度
      const chars = kept.split("");
      let i = chars.length - 1;
      let carry = 1;
      while (i >= 0 && carry) {
        const digit = chars[i].charCodeAt(0) - 48 + carry;
        chars[i] = String(digit % 10);
        carry = digit >= 10 ? 1 : 0;
        i -= 1;
      }
      kept = chars.join("");
      if (carry) {
        // 全部进位出界：整数部分变成 1（0.999… → 1.0）
        kept = "1" + kept;
        newPointPos += 1;
      }
    }
    kept = kept.replace(/^0+/, "") || "0";
    return { digits: kept, exp: newPointPos - 1 };
  }

  /** 把十进制数字串补足到 `places` 位小数（定点输出）。 */
  function decimalFixed(digits, exp, places) {
    const pointPos = exp + 1;
    let whole;
    let fraction;
    if (pointPos <= 0) {
      whole = "0";
      fraction = "0".repeat(-pointPos) + digits;
    } else if (pointPos >= digits.length) {
      whole = digits + "0".repeat(pointPos - digits.length);
      fraction = "";
    } else {
      whole = digits.slice(0, pointPos);
      fraction = digits.slice(pointPos);
    }
    if (whole === "") whole = "0";
    fraction = (fraction + "0".repeat(places)).slice(0, places);
    return places > 0 ? whole + "." + fraction : whole;
  }

  /**
   * Python 的 format(value, ".Nf")：定点输出，舍入用最短表示上的银行家舍入。
   * 127.5 → "128"、2.5 → "2"、6.5 → "6"，和 Python 完全一致。
   */
  function pyFixed(value, digits) {
    const x = Number(value);
    if (Number.isNaN(x)) return "nan";
    if (x === Infinity) return "inf";
    if (x === -Infinity) return "-inf";
    const { negative, digits: rawDigits, pointPos } = decimalParts(x);
    const rounded = decimalRound(rawDigits, pointPos, digits);
    const out = decimalFixed(rounded.digits, rounded.exp, digits);
    return (negative ? "-" : "") + out;
  }

  /**
   * Python 的 round(value, 1)：同样是最短表示上的银行家舍入。
   * 推荐结果去重的签名用的是它，直接用 Math.round（.5 远离零）在
   * 0.05 / 0.15 / 123456.7 这些值上会和 Python 分叉。
   */
  function round1(value) {
    const x = Number(value);
    if (!Number.isFinite(x)) return x;
    const { negative, digits, pointPos } = decimalParts(x);
    const rounded = decimalRound(digits, pointPos, 1);
    const text = decimalFixed(rounded.digits, rounded.exp, 1);
    const result = Number(text);
    return negative ? -result : result;
  }

  /**
   * 按 Python 元组比较的规则排序（JS 的 sort 在 V8/SpiderMonkey 上都是稳定排序，
   * 和 CPython 一样，所以相等元素的相对顺序一致）。
   */
  function cmpBy(keys) {
    return function (a, b) {
      for (let i = 0; i < keys.length; i += 1) {
        const left = keys[i](a);
        const right = keys[i](b);
        if (left < right) return -1;
        if (left > right) return 1;
      }
      return 0;
    };
  }

  /** Python 的 int(value)：向零截断。 */
  function toInt(value) {
    const x = Number(value);
    if (!Number.isFinite(x)) return 0;
    return x < 0 ? Math.ceil(x) : Math.floor(x);
  }

  /**
   * Python 的 str(x)：数值部分和 JS 的 String() 一致（NaN→'nan'、Infinity→'inf'、
   * -0.0→'0.0'、整数 float→'3.0' 这些都得对上），bool 是 'True'/'False'，None 是 'None'。
   * 参数里的 id 要拿它做比较（`str(1005.0) == "1005.0"`，不能被 JS 压成 "1005"）。
   */
  function pyStrNum(value) {
    if (value === undefined || value === null) return "None";
    if (typeof value === "boolean") return value ? "True" : "False";
    if (typeof value === "number") {
      if (Number.isNaN(value)) return "nan";
      if (value === Infinity) return "inf";
      if (value === -Infinity) return "-inf";
      if (Object.is(value, -0)) return "0.0";
      return String(value);
    }
    return String(value);
  }

  /**
   * Python 的 float(value)：和 JS 的 Number() 有几处会分叉——
   * 十六进制/二进制前缀（'0x2'）Python 不接受，下划线分隔（'1_0'）Python 接受。
   */
  function pyFloat(value) {
    if (typeof value === "number") return value;
    if (typeof value === "boolean") return value ? 1 : 0;
    if (typeof value !== "string") {
      if (value === undefined || value === null) return 0;
      return NaN;
    }
    const text = value.replace(/^[\s\u3000]+/, "").replace(/[\s\u3000]+$/, "");
    if (text === "") return NaN;
    const normalized = text.replace(/_/g, "");
    if (/^[+-]?0[xXbBoO]/.test(normalized)) return NaN; // Python 的 float() 不认进制前缀
    if (normalized.length !== text.length && !/^[+-]?(\d[\d_]*)?(\.\d[\d_]*)?([eE][+-]?\d+)?$/.test(text)) {
      return NaN;
    }
    if (!/^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$|^[+-]?(inf|infinity|nan)$/i.test(normalized)) return NaN;
    if (/^[+-]?(inf|infinity)$/i.test(normalized)) return normalized.charAt(0) === "-" ? -Infinity : Infinity;
    if (/^[+-]?nan$/i.test(normalized)) return NaN;
    return Number(normalized);
  }

  /** Python 的 int(float(value))：先按 float 解析再向零截断。 */
  function pyInt(value) {
    return toInt(pyFloat(value));
  }

  /** 参数取值：None 和空串按缺省处理，其余按 float 解析（对应 Python 的 _num）。 */
  function num(payload, key, fallback) {
    const def = fallback === undefined ? 0.0 : fallback;
    const value = payload ? payload[key] : undefined;
    if (value === undefined || value === null || value === "") return Number(def);
    // 只认 ASCII 数字串（与 Python 版一致）
    if (typeof value === "string" && /[^\x00-\x7f]/.test(value.replace(/^\s+|\s+$/g, ""))) {
      throw new Error("参数 " + key + " 需要是数字，收到 " + pyRepr(value));
    }
    const x = pyFloat(value);
    if (Number.isNaN(x) && !(typeof value === "string" && /^[\s]*[+-]?nan[\s]*$/i.test(value))) {
      throw new Error("参数 " + key + " 需要是数字，收到 " + pyRepr(value));
    }
    if (!Number.isFinite(x) || Math.abs(x) > NUM_LIMIT) {
      throw new Error("参数 " + key + " 超出范围，收到 " + pyRepr(value));
    }
    return x;
  }

  function validateSubstatSpeed(relic) {
    const value = num(relic, "substatSpeed", 0);
    const limit = pyBool(relic.speedBoots) ? 78 : 93.6;
    if (value < 0 || value > limit + 1e-9) throw new Error(`副词条速度合计须在 0 到 ${limit} 之间（按是否使用速度鞋计算理论上限）。`);
    return value;
  }

  function find(items, itemId) {
    const wanted = pyStrNum(itemId);
    for (let i = 0; i < items.length; i += 1) {
      if (pyStrNum(items[i] && items[i].id) === wanted) return items[i];
    }
    return null;
  }

  /** Python 的 str(value) 后 strip()。 */
  function pyStrip(value) {
    return pyStr(value).replace(/^\s+/, "").replace(/\s+$/, "");
  }

  // ------------------------------------------------------------------------- #
  // 遗器套装的触发方式
  // ------------------------------------------------------------------------- #

  /**
   * 判断一条效果什么时候生效——这决定了它能不能自动计入。
   * 判定顺序不能改：先看「每次开大」，再看「进战」，然后才是有条件/常驻。
   */
  function triggerOf(text) {
    const source = text === undefined || text === null ? "" : String(text);
    if (source.indexOf("施放终结技") !== -1) {
      // 信使 4 件套是「对我方目标施放终结技」，对敌人开大不会触发。
      if (source.indexOf("对我方目标") !== -1 || source.indexOf("对队友") !== -1) return "allyUlt";
      return "perUlt"; // 每次开大触发：风套这类，要乘以开大次数
    }
    if (source.indexOf("进入战斗") !== -1 || source.indexOf("战斗开始时") !== -1) {
      return "onEnter"; // 进战一次性：翁瓦克这类
    }
    for (const marker of ["若", "大于", "每回合", "持续", "层", "消灭"]) {
      if (source.indexOf(marker) !== -1) return "conditional"; // 有条件，交给用户判断
    }
    return "passive"; // 无条件常驻
  }

  // ------------------------------------------------------------------------- #
  // 行动模拟内核（速度随时间生效）—— 与 api.py 逐位对应
  // ------------------------------------------------------------------------- #
  //
  // 为什么需要它：静态公式「最终速度 = 基础 × (1+pct) + flat」默认所有加速从第 1 次
  // 行动就生效。但游戏里有两类加速不是这样：
  //   * 开大触发的加速（信使 4 件套、棺的回响）——第一次开大之前根本没有；
  //   * 叠层类的加速（只需等待「每次施放攻击后速度提高 4.8%，最多叠 3 层」）——
  //     第 1 次行动 0 层、第 2 次行动 1 层……逐层往上叠。
  // 这两类必须真的把角色的行动一次一次走出来。
  const SIM_TIMELINE_LIMIT = 12; // timeline 最多给界面 12 条
  const SIM_MAX_STEPS = 100000; // 模拟的硬上限（只防死循环）
  const SIM_MAX_ACTIONS = 200; // 目标动数上限
  const MAX_WINDOW_AV = 100000.0; // 行动值节点上限
  const NUM_LIMIT = 1e9; // 数字参数绝对值上限

  const CUSTOM_ID = "__custom__";
  const CUSTOM_NAME_MAX = 20;

  /** 「自定义角色」：只有名字 / 基础速度 / 行迹速度，没有角色自带效果、不限命途（对应 api.py）。 */
  function customCharacter(p) {
    const raw = p.customCharacter;
    if (!isDict(raw)) throw new Error("自定义角色需要 customCharacter 对象");
    let name = raw.name;
    if (name !== undefined && name !== null && typeof name !== "string") {
      throw new Error("自定义角色名字需要是文字");
    }
    name = (name || "").replace(/^\s+|\s+$/g, "") || "自定义角色";
    if (Array.from(name).length > CUSTOM_NAME_MAX) {
      throw new Error("自定义角色名字最多 " + CUSTOM_NAME_MAX + " 个字");
    }
    const base = num(raw, "baseSpeed", 0);
    if (!(base >= 1 && base <= 1000)) {
      throw new Error("参数 customCharacter.baseSpeed 需要在 1–1000 之间，收到 " + pyG(base));
    }
    const trace = num(raw, "traceSpeed", 0);
    if (!(trace >= 0 && trace <= 200)) {
      throw new Error("参数 customCharacter.traceSpeed 需要在 0–200 之间，收到 " + pyG(trace));
    }
    return {
      id: CUSTOM_ID,
      name: name,
      baseSpeed: base,
      traceSpeed: trace,
      path: null,
      pathName: "自定义",
      elementName: null,
      rarity: null,
      effects: [],
      custom: true,
    };
  }

  function checkTarget(actions, windowAv) {
    if (actions > SIM_MAX_ACTIONS) {
      throw new Error("目标动数最多 " + SIM_MAX_ACTIONS + "，收到 " + actions);
    }
    if (windowAv > MAX_WINDOW_AV) {
      throw new Error("行动值节点最多 " + pyG(MAX_WINDOW_AV) + "，收到 " + pyG(windowAv));
    }
  }

  /** 把一条速度效果整理成模拟内核认识的形式（semantics 三选一）。 */
  function modifierOf(opts) {
    const stacks = Math.max(0, toInt(opts.maxStacks || 0));
    const duration = Math.max(0, toInt(opts.durationTurns || 0));
    let semantics;
    if (stacks > 0) semantics = "stack";
    else if (opts.trigger === "perUlt" || opts.trigger === "allyUlt") semantics = "perUlt";
    else if (duration > 0 && opts.trigger !== "onEnter") semantics = "timed";
    else semantics = "constant";
    return {
      label: opts.label,
      kind: opts.kind,
      value: Number(opts.value || 0),
      trigger: opts.trigger,
      apply: opts.apply || "self",
      durationTurns: duration,
      maxStacks: stacks,
      semantics: semantics,
    };
  }

  /**
   * 第 step 次行动时还在生效的加速（step 从 1 开始）。
   * 叠层的条目返回的是**按层数放大后**的副本（第 k 次行动前 min(k-1, N) 层），
   * 所以调用方直接累加 value 就是当前这一动的加成。
   */
  function activeModifiers(modifiers, step, firstUltAction) {
    const out = [];
    for (const item of modifiers) {
      const semantics = item.semantics || "constant";
      if (semantics === "constant") {
        out.push(item);
        continue;
      }
      if (semantics === "stack") {
        const stacks = Math.min(Math.max(step - 1, 0), item.maxStacks || 0);
        if (stacks <= 0) continue;
        out.push(Object.assign({}, item, { value: Number(item.value || 0) * stacks, stacks: stacks }));
        continue;
      }
      if (semantics === "timed") {
        const duration = item.durationTurns || 0;
        if (!(duration > 0) || step > duration) continue;
        out.push(item);
        continue;
      }
      if (semantics === "perUlt") {
        // firstUltAction = 第一次开大发生在自己第几次行动**之后**
        const begin = (firstUltAction || 0) + 1;
        if (step < begin) continue;
        const duration = item.durationTurns || 0;
        if (duration > 0 && step >= begin + duration) continue;
      }
      out.push(item);
    }
    return out;
  }

  /** 生效增益的简写标签（界面 timeline 里显示这个）。 */
  function activeLabel(item, step) {
    const semantics = item.semantics || "constant";
    if (semantics === "stack") {
      const stacks = Math.min(Math.max(step - 1, 0), item.maxStacks || 0);
      return "层数 " + stacks + "/" + item.maxStacks;
    }
    if (semantics === "constant") {
      return pyStrip("常驻 " + (item.label || ""));
    }
    return item.label || "";
  }

  /** 当前这一步的速度 = base × (1 + 生效百分比之和/100) + 生效固定值之和。 */
  function stepSpeed(base, active, percentBase) {
    let pct = 0.0;
    let flat = 0.0;
    for (const item of active) {
      if (item.kind === "pct") pct += Number(item.value || 0);
      else flat += Number(item.value || 0);
    }
    // percentBase 有值时，base 已是 S0。额外百分比只乘真正的基础速度。
    if (percentBase === undefined || percentBase === null) return base * (1 + pct / 100.0) + flat;
    return base + Number(percentBase) * (pct / 100.0) + flat;
  }

  /**
   * 从 AV=0 开始一次次行动，直到窗口结束。
   * 返回 achieved（旧公式口径）/ completed（真实行动值口径）/ timeline。
   */
  function simulate(baseSpeed, modifiers, opts) {
    const o = opts || {};
    const speed0 = o.speed0 === undefined || o.speed0 === null ? null : Number(o.speed0);
    const windowAv = Number(o.windowAv);
    const firstUltAction = o.firstUltAction === undefined ? 1 : o.firstUltAction;
    const distance = o.distance === undefined ? 10000.0 : Number(o.distance);
    const advanceDistance = o.advanceDistance === undefined ? 0.0 : Number(o.advanceDistance);
    const timelineLimit = o.timelineLimit === undefined ? SIM_TIMELINE_LIMIT : o.timelineLimit;
    const actionCap = o.actionCap === undefined || o.actionCap === null ? null : o.actionCap;
    const base = speed0 === null ? Number(baseSpeed) : speed0;
    let distanceLeft = 0.0;
    // 拉条 = 总路程减少 advanceDistance（与闭式公式同口径），从最早的行动开始抵扣
    let advanceLeft = Math.max(0.0, advanceDistance || 0.0);
    let av = 0.0;
    let achieved = 0;
    let completed = 0;
    const timeline = [];
    const maxSteps = actionCap === null ? SIM_MAX_STEPS : toInt(actionCap);
    while (achieved < maxSteps) {
      const step = achieved + 1;
      const active = activeModifiers(modifiers, step, firstUltAction);
      const speed = speed0 === null ? stepSpeed(baseSpeed, active) : stepSpeed(base, active, baseSpeed);
      if (!(speed > 0)) break; // 速度非正 → 永远动不了
      const use = Math.min(distance, advanceLeft);
      const nextAv = av + (distance - use) / speed;
      if (av > windowAv + 1e-9 * Math.max(1.0, Math.abs(av))) break; // 开始时间已出窗口
      // 与旧公式同一个阈值：这一次行动打完还在窗口内
      if (distanceLeft + distance - advanceDistance <= windowAv * speed + 1e-9 * Math.max(1.0, Math.abs(windowAv * speed))) {
        achieved += 1;
      } else {
        // 按「当前速度恒定」推已经超了，但真实行动值未必：继续走完，由 completed 说话
        achieved = Math.max(achieved, completed + 1);
      }
      if (nextAv <= windowAv + 1e-9 * Math.max(1.0, Math.abs(nextAv))) completed += 1;
      if (timeline.length < timelineLimit) {
        let pct = 0.0;
        let flat = 0.0;
        for (const item of active) {
          if (item.kind === "pct") pct += Number(item.value || 0);
          else flat += Number(item.value || 0);
        }
        const labels = active.map((item) => activeLabel(item, step));
        timeline.push({
          action: step,
          speed: speed,
          av: av,
          pct: pct,
          flat: flat,
          active: labels.length ? labels : ["（无增益）"],
        });
      }
      distanceLeft += distance;
      advanceLeft -= use;
      av = nextAv;
      if (!Number.isFinite(av)) break;
    }
    return { av: av, achieved: achieved, completed: completed, timeline: timeline };
  }

  /** 二分「未加速速度 S0」，使得窗口内正好能打出 actions 次行动。 */
  function requiredSpeed(baseSpeed, modifiers, opts) {
    const o = opts || {};
    const actions = toInt(o.actions);
    const avLimit = Number(o.avLimit);
    const advanceDistance = Number(o.advanceDistance || 0);
    const distance = Number(o.distance || 10000.0);
    const firstUltAction = o.firstUltAction === undefined ? 1 : o.firstUltAction;
    if (!actions || !(avLimit > 0)) return 0.0;
    // 没有随行动变化的加速 → 闭式解，与旧算法逐位一致（兼容性红线）
    if (!anyTimeline(modifiers)) {
      return Math.max(0.0, (actions * distance - advanceDistance) / avLimit);
    }
    let low = o.low === undefined ? 0.0 : Number(o.low);
    let high = o.high === undefined || o.high === null ? Math.max(1000.0, baseSpeed * 50.0) : Number(o.high);
    const cap = actions + 1;
    const done = (s0) =>
      simulate(baseSpeed, modifiers, {
        speed0: s0,
        windowAv: avLimit,
        firstUltAction: firstUltAction,
        distance: distance,
        advanceDistance: advanceDistance,
        timelineLimit: 0,
        actionCap: cap,
      }).completed >= actions;
    // 上界不够就翻倍（旧版直接把上界当答案返回）
    let grown = false;
    for (let i = 0; i < 80; i += 1) {
      if (done(high)) {
        grown = true;
        break;
      }
      low = high;
      high = high * 2.0;
    }
    if (!grown) return Infinity;
    for (let i = 0; i < 200; i += 1) {
      const mid = (low + high) / 2.0;
      const result = simulate(baseSpeed, modifiers, {
        speed0: mid,
        windowAv: avLimit,
        firstUltAction: firstUltAction,
        distance: distance,
        advanceDistance: advanceDistance,
        timelineLimit: 0,
        actionCap: cap,
      });
      if (result.completed >= actions) high = mid;
      else low = mid;
      // 收敛到相邻浮点数就停：再二分下去也没有更细的解了
      if (nextAfter(low, high) >= high) break;
    }
    return high;
  }

  /** JS 版 math.nextafter（只用来判断两个 double 是否已经相邻）。 */
  function nextAfter(value, toward) {
    const x = Number(value);
    const y = Number(toward);
    if (Number.isNaN(x) || Number.isNaN(y)) return NaN;
    if (x === y) return y;
    if (x === 0) return y > 0 ? Number.MIN_VALUE : -Number.MIN_VALUE;
    const buffer = new ArrayBuffer(8);
    const view = new DataView(buffer);
    view.setFloat64(0, x);
    let bits = view.getBigUint64(0);
    if ((x > 0) === (y > x)) bits += 1n;
    else bits -= 1n;
    view.setBigUint64(0, bits);
    return view.getFloat64(0);
  }

  /** 有没有「随行动变化」的加速（开大触发 / 叠层）。 */
  function anyTimeline(modifiers) {
    return modifiers.some((item) => (item.semantics || "constant") !== "constant");
  }

  /** 把「哪条加速从第几次行动起生效」写成一句人话。 */
  function simulationNotes(modifiers, firstUltAction) {
    const notes = [];
    for (const item of modifiers) {
      const semantics = item.semantics || "constant";
      const label = item.label || "速度效果";
      if (semantics === "perUlt") {
        const begin = (firstUltAction || 0) + 1;
        const duration = item.durationTurns || 0;
        const tail =
          duration > 0
            ? "，持续 " + duration + " 次行动（第 " + (begin + duration) + " 次行动起失效）"
            : "，一直有效到窗口结束";
        const when = !firstUltAction ? "进战即开大" : "第 " + firstUltAction + " 次行动后开大";
        notes.push(when + "，「" + label + "」从第 " + begin + " 次行动起生效" + tail);
      } else if (semantics === "timed") {
        const duration = item.durationTurns || 0;
        notes.push(
          "「" + label + "」从第 1 次行动起生效，持续 " + duration + " 次行动（第 " + (duration + 1) + " 次行动起失效）",
        );
      } else if (semantics === "stack") {
        notes.push(
          "「" +
            label +
            "」每次行动叠 1 层，最多 " +
            item.maxStacks +
            " 层（第 k 次行动前有 min(k−1, " +
            item.maxStacks +
            ") 层）",
        );
      }
    }
    return notes;
  }

  /**
   * 把遗器套装拆成「可作 4 件套的」和「可作位面饰品的」两组。
   *
   * 两组都是**全量**：没有速度效果的套装照样能选（比如为了它的攻击/伤害效果），
   * 只是计算时不会产生任何速度贡献。分类依据是套装文案条数
   * （遗器 = 2 件套 + 4 件套两条；位面饰品只有 2 件套一条）。
   */
  function relicEffectOptions(relicList) {
    const fourPiece = [];
    const ornaments = [];

    for (const relic of relicList) {
      const effects = [];
      for (const effect of relic.effects || []) {
        const kind = effect ? effect.kind : undefined;
        if (kind !== "pct" && kind !== "flat" && kind !== "advance") continue;
        const source = effect.source || "";
        const slot = source.indexOf("4件套") !== -1 ? "4件套" : source.indexOf("2件套") !== -1 ? "2件套" : source;
        const text = effect.text || "";
        effects.push({
          slot: slot,
          kind: kind,
          value: effect.value,
          apply: effect.apply,
          text: text,
          trigger: triggerOf(text),
        });
      }
      const desc = [];
      for (const line of relic.desc || []) desc.push(String(line));
      const entry = {
        id: relic.id,
        name: relic.name,
        contentId: relic.contentId,
        icon: relic.icon || relic.iconSmall, // 本地 webp 优先
        releaseOrder: relic.releaseOrder,
        effects: effects,
        hasSpeedEffect: Boolean(effects.length),
        summary: desc.join(" ／ ").slice(0, 100),
      };
      if (desc.length >= 2) fourPiece.push(entry);
      else ornaments.push(entry);
    }

    // 遗器池按推出顺序排（新的在前），和角色列表一致
    const orderKey = (item) => [item.releaseOrder === undefined || item.releaseOrder === null, item.releaseOrder || 0];
    fourPiece.sort(cmpBy([(i) => orderKey(i)[0], (i) => orderKey(i)[1]]));
    ornaments.sort(cmpBy([(i) => orderKey(i)[0], (i) => orderKey(i)[1]]));
    return { fourPiece: fourPiece, ornaments: ornaments };
  }

  // ------------------------------------------------------------------------- #
  // 效果与勾选
  // ------------------------------------------------------------------------- #

  function effectId(scope, index) {
    return scope + "#" + index;
  }

  /**
   * 返回 (速度类效果, 拉条类效果)，都带稳定 id 与默认勾选状态。
   * 注意 scope 编号是**全局递增**的：角色的效果即使被星魂过滤掉也会占号，
   * 这样光锥效果的 id 不会因为星魂档位变化而改变。
   */
  function collectEffects(character, cone, superimpose) {
    const speed = [];
    const advance = [];

    const push = (scope, index, raw, origin) => {
      const kind = raw.kind;
      const text = raw.text || "";
      // 触发方式要摆到界面上：有些加速不是开局就生效的（开大后 / 进战 / 有条件），
      // 用户得知道自己在勾什么。判定逻辑和遗器套装共用 triggerOf()。
      const trigger = triggerOf(text);
      const entry = {
        id: effectId(scope, index),
        origin: origin,
        name: raw.name || "",
        kind: kind,
        value: raw.value,
        apply: raw.apply || "self",
        text: text,
        rank: raw.rank,
        superimpose: raw.superimpose,
        trigger: trigger,
        // 持续回合 / 叠层上限：模拟内核要靠它们决定加速什么时候生效、什么时候到期
        durationTurns: toInt(raw.durationTurns || 0),
        maxStacks: toInt(raw.maxStacks || 0),
        // 自动判断「看起来是否无条件（开局就生效）」。有条件的一律默认不勾，避免高估速度；
        // 只有 trigger 是 passive 的才算常驻，开大 / 进战触发的默认不勾。
        defaultEnabled:
          ((kind === "pct" || kind === "flat") &&
            raw.apply === "self" &&
            trigger === "passive" &&
            !CONDITION_MARKERS.some((marker) => text.indexOf(marker) !== -1)) ||
          // 星魂是用户主动选的（调到 2 魂就是要它的效果），星魂来源默认勾上；
          // 否则界面上选了星魂却看不到任何变化。与 api.py 逐位一致。
          ((kind === "pct" || kind === "flat") && raw.source === "星魂" && raw.apply !== "enemy"),
      };
      if (kind === "pct" || kind === "flat") speed.push(entry);
      else if (kind === "advance") advance.push(entry);
    };

    let scopeIndex = 0;
    for (const raw of character.effects || []) {
      push("char" + scopeIndex, scopeIndex, raw, "角色·" + (raw.source || "技能"));
      scopeIndex += 1;
    }

    if (cone) {
      for (const raw of cone.effects || []) {
        if (!(raw.superimpose === undefined || raw.superimpose === null || raw.superimpose === superimpose)) continue;
        push("cone" + scopeIndex, scopeIndex, raw, "光锥");
        scopeIndex += 1;
      }
    }

    // 同一套数据里 2 件套/4 件套可能抽出完全相同的条目，去重免得重复计入
    const dedup = (items) => {
      const seen = {};
      const out = [];
      for (const item of items) {
        const key = JSON.stringify([item.kind, item.value, item.apply, item.text]);
        if (seen[key]) continue;
        seen[key] = true;
        out.push(item);
      }
      return out;
    };

    return { speed: dedup(speed), advance: dedup(advance) };
  }

  /** 星魂效果只保留 rank <= 当前星魂档位的。 */
  function filterByEidolon(character, eidolon) {
    const out = [];
    for (const raw of character.effects || []) {
      if (raw.source === "星魂") {
        const rank = raw.rank;
        if (rank === undefined || rank === null || toInt(rank) > eidolon) continue;
      }
      out.push(raw);
    }
    return out;
  }

  // ------------------------------------------------------------------------- #
  // 数据读取
  // ------------------------------------------------------------------------- #

  function makeReaders(data) {
    const store = data || {};

    const characters = () => {
      const value = store.characters;
      if (!isList(value) || !value.length) {
        throw new Error("角色数据为空：先跑一次 `python tools/import_hsr_data.py` 把米游社数据抓下来");
      }
      return value;
    };

    const lightcones = () => {
      const value = store.lightcones;
      if (!isList(value)) {
        throw new Error("光锥数据缺失，先跑 `python tools/import_hsr_data.py`");
      }
      return value;
    };

    const relics = () => (isList(store.relic_sets) ? store.relic_sets : []);

    const modes = () => {
      const value = store.modes || {};
      const defaults = Object.assign({}, DEFAULT_CYCLES, value.cycles || {});
      const list = [];
      for (const mode of value.modes || []) {
        // 每个模式可以有自己的首轮/每轮行动值（异相仲裁首轮是 300，不是 150）
        const entry = Object.assign({}, mode);
        entry.firstCycleAV = Number(mode.firstCycleAV === undefined ? defaults.firstCycleAV : mode.firstCycleAV);
        entry.cycleAV = Number(mode.cycleAV === undefined ? defaults.cycleAV : mode.cycleAV);
        list.push(entry);
      }
      return {
        modes: list,
        cycles: defaults,
        targets: value.targets || { minActions: 1, maxActions: 8 },
        meta: value.meta || {},
      };
    };

    return { characters: characters, lightcones: lightcones, relics: relics, modes: modes };
  }

  function modeById(modes, modeId) {
    for (const mode of modes.modes) {
      if (mode.id === modeId) return mode;
    }
    return null;
  }

  // ------------------------------------------------------------------------- #
  // 我的配装
  // ------------------------------------------------------------------------- #

  function makeStorage(storage) {
    if (storage && typeof storage.load === "function" && typeof storage.save === "function") {
      return storage;
    }
    // 不传 storage 时用内存对象兜底（node 里没有 localStorage，所以**不能**直接用）
    let memory = {};
    return {
      load: () => JSON.parse(JSON.stringify(memory)),
      save: (value) => {
        memory = JSON.parse(JSON.stringify(value));
      },
    };
  }

  /** Python 的 datetime.now().strftime("%Y-%m-%d %H:%M")。 */
  function nowStamp() {
    const now = new Date();
    const pad = (value) => String(value).padStart(2, "0");
    return (
      String(now.getFullYear()) +
      "-" +
      pad(now.getMonth() + 1) +
      "-" +
      pad(now.getDate()) +
      " " +
      pad(now.getHours()) +
      ":" +
      pad(now.getMinutes())
    );
  }

  // ------------------------------------------------------------------------- #
  // 接口
  // ------------------------------------------------------------------------- #

  function createApi(data, storage) {
    const readers = makeReaders(data);
    const characters = readers.characters;
    const lightconesData = readers.lightcones;
    const relics = readers.relics;
    const modesData = readers.modes;
    const presetStore = makeStorage(storage);

    const loadPresets = () => {
      const value = presetStore.load();
      return isDict(value) ? value : {};
    };

    /** 角色列表、模式、遗器速度套装、数据来源。 */
    function catalog(payload) {
      const chars = characters();
      const modes = modesData();
      const sources = (data && data.sources) || {};

      // 2 件套给速度百分比的遗器，供「套装」下拉用（手动兜底，主路径是下面两组）
      const speedSets = [];
      for (const relic of relics()) {
        for (const effect of relic.effects || []) {
          if (effect.source === "遗器·2件套" && effect.kind === "pct") {
            speedSets.push({
              id: relic.id,
              name: relic.name,
              pct: effect.value,
              text: effect.text,
            });
            break;
          }
        }
      }

      const options = relicEffectOptions(relics());
      const sorted = chars.slice().sort(
        cmpBy([
          (item) => item.releaseOrder === undefined || item.releaseOrder === null,
          (item) => item.releaseOrder || 0,
        ]),
      );

      const pathNames = [];
      const seenPath = {};
      for (const char of chars) {
        if (char.pathName && !seenPath[char.pathName]) {
          seenPath[char.pathName] = true;
          pathNames.push(char.pathName);
        }
      }
      pathNames.sort();

      return {
        fourPieceSets: options.fourPiece,
        ornamentSets: options.ornaments,
        characters: sorted.map((char) => ({
          id: char.id,
          name: char.name,
          rarity: char.rarity,
          path: char.path,
          pathName: char.pathName,
          elementName: char.elementName,
          baseSpeed: char.baseSpeed,
          // 行迹里的速度是角色自带的，界面上显示的「初始速度」要带上它
          traceSpeed: char.traceSpeed || 0,
          // effectiveBaseSpeed 缺失或恰好为 0 时回落到白值
          effectiveBaseSpeed: char.effectiveBaseSpeed || char.baseSpeed,
          effectCount: (char.effects || []).length,
          contentId: char.contentId,
          // 官方图：小图给下拉列表用，立绘给左侧展示用；都是远程地址，
          // 由工具箱的 /api/asset 按需下载并缓存到本地
          icon: char.icon || char.iconSmall, // 本地 webp 优先
          iconLarge: char._remote?.icon || char.icon,
          // 立绘优先用游戏内预览图（没有「首发/复刻」角标），失败时界面回退到米游社那张
          splash: char.splash || char.splashSmall || char.splashFallback,
          splashLarge: char._remote?.splash || null,
          splashFallback: char.splashFallback,
          releaseOrder: char.releaseOrder,
        })),
        paths: pathNames,
        modes: modes.modes,
        cycles: modes.cycles,
        targets: modes.targets,
        speedSets: speedSets,
        sources: sources,
      };
    }

    /** 按命途筛选光锥（角色只能用同命途的光锥）。 */
    function lightcones(payload) {
      const cones = lightconesData();
      const p = payload || {};
      const path = p.path;
      const rarity = pyInt(num(p, "rarity", 0));
      const out = [];
      for (const cone of cones) {
        if (pyBool(path) && cone.path !== path) continue;
        if (rarity && toInt(cone.rarity || 0) < rarity) continue;
        out.push({
          id: cone.id,
          name: cone.name,
          rarity: cone.rarity,
          path: cone.path,
          pathName: cone.pathName,
          effectCount: (cone.effects || []).length,
          icon: cone.icon || cone.iconSmall, // 本地 webp 优先
          releaseOrder: cone.releaseOrder,
          speedRelated: (cone.effects || []).some(
            (effect) => effect.kind === "pct" || effect.kind === "flat" || effect.kind === "advance",
          ),
        });
      }
      // Python 里 payload.get("path") 缺省就是 None，导出成 JSON 是 null
      return { lightcones: out, path: path === undefined ? null : path };
    }

    function resolveCharacter(p) {
      if (pyStrNum(p.characterId) === CUSTOM_ID) return customCharacter(p);
      const character = find(characters(), p.characterId);
      if (character === null) throw new Error("找不到角色 " + pyRepr(p.characterId));
      return character;
    }

    /** 算实际速度 + 各模式各 T 数各动数的需求速度。 */
    function plan(payload) {
      const p = payload || {};
      const character = resolveCharacter(p);

      const eidolon = Math.max(0, Math.min(pyInt(num(p, "eidolon", 0)), 6));
      const superimpose = Math.max(1, Math.min(pyInt(num(p, "superimpose", 1)), 5));

      let cone = null;
      const coneId = p.lightconeId;
      if (pyBool(coneId)) {
        cone = find(lightconesData(), coneId);
        if (cone === null) {
          throw new Error("找不到光锥 " + pyRepr(coneId));
        }
        if (pyBool(cone.path) && pyBool(character.path) && cone.path !== character.path) {
          throw new Error(
            character.name +
              "（" +
              (character.pathName === undefined ? undefined : character.pathName) +
              "）不能装备" +
              cone.name +
              "（" +
              (cone.pathName === undefined ? undefined : cone.pathName) +
              "）",
          );
        }
      }

      // 效果清单（星魂按档位过滤后再抽取）
      const filtered = Object.assign({}, character);
      filtered.effects = filterByEidolon(character, eidolon);
      const collected = collectEffects(filtered, cone, superimpose);
      const speedEffects = collected.speed;
      const advanceEffects = collected.advance;

      // enabledEffects 没给、或者给了一个**空数组**，就走「默认勾选」那一套 ——
      // Python 的 `if not enabled:` 对 None 和 [] 一视同仁，网页版必须照抄，
      // 否则界面上「勾掉所有效果」会得到和 Python 不一样的裸速度。
      // null/undefined = 默认勾选；[] = 用户全勾掉了，照办
      let enabled = p.enabledEffects === undefined || p.enabledEffects === null ? null : p.enabledEffects;
      if (enabled !== null && !Array.isArray(enabled)) {
        throw new Error("参数 enabledEffects 需要是列表");
      }
      if (enabled === null) {
        enabled = speedEffects.filter((effect) => effect.defaultEnabled).map((effect) => effect.id);
      } else {
        enabled = Array.from(new Set(enabled.map((id) => pyStrNum(id))));
      }
      const enabledSet = {};
      for (const id of enabled) enabledSet[String(id)] = true;

      const gameBase = Number(character.baseSpeed || 0);
      if (gameBase <= 0) {
        throw new Error(character.name + " 没有基础速度数据，请重新跑导入器");
      }

      // 初始速度供展示；行迹固定速度不参与百分比乘区。
      const traceFlat = Number(character.traceSpeed || 0);
      const tracePct = Number(character.traceSpeedPct || 0);
      const baseSpeed = gameBase + traceFlat;

      const breakdown = [];
      if (pyBool(traceFlat) || pyBool(tracePct)) {
        breakdown.push({ label: "角色基础速度（游戏白值）", kind: "base", value: gameBase });
        const detail = (character.traceSpeedDetails || [])
          .map((item) => (item.name === undefined ? undefined : item.name) + "+" + pyG(item.value))
          .join("、");
        if (traceFlat) {
          breakdown.push({
            label: "行迹速度加成（自带，不参与百分比）",
            kind: "flat",
            value: traceFlat,
            text: detail,
          });
        }
      }

      // ---- 遗器与手填 ----
      const relicIn = p.relic || {};
      const advanceIn = p.advance || {};
      // 「轴底开大」：最后一次开大的拉条发生在收尾，帮不到前面几动，勾了就把它扣掉
      const excludeLastUlt = pyBool(advanceIn.excludeLastUlt);
      const ultNote = excludeLastUlt ? "（轴底那次开大不计）" : "";

      /** 按「轴底开大」把每次开大触发的拉条次数减一。 */
      const effectiveUlts = (count) => {
        let value = Math.max(0.0, Number(count));
        if (!excludeLastUlt || value <= 0) return value;
        return Math.max(0.0, value - 1);
      };

      let pctTotal = tracePct;
      let flatTotal = 0.0;
      // 手填项的「修饰形态」，只给模拟时间线算每一步速度用，不重复累加
      const manualModifiers = [];

      if (traceFlat) manualModifiers.push(modifierOf({ label: "行迹速度", kind: "flat", value: traceFlat, trigger: "passive" }));

      if (tracePct) {
        // 行迹里的百分比作为百分比修饰参与时间线计算。
        manualModifiers.push(modifierOf({ label: "行迹速度%", kind: "pct", value: tracePct, trigger: "passive" }));
      }

      if (relicIn.speedBoots) {
        flatTotal += SPEED_BOOTS_FLAT;
        breakdown.push({ label: "遗器主词条·速度鞋", kind: "flat", value: SPEED_BOOTS_FLAT });
        manualModifiers.push(
          modifierOf({ label: "遗器主词条·速度鞋", kind: "flat", value: SPEED_BOOTS_FLAT, trigger: "passive" }),
        );
      }

      const setPct = num(relicIn, "setSpeedPct", 0);
      if (setPct) {
        pctTotal += setPct;
        breakdown.push({
          label: relicIn.setSpeedName || "遗器 2 件套速度",
          kind: "pct",
          value: setPct,
        });
        manualModifiers.push(
          modifierOf({
            label: relicIn.setSpeedName || "遗器 2 件套速度",
            kind: "pct",
            value: setPct,
            trigger: "passive",
          }),
        );
      }

      const substat = validateSubstatSpeed(relicIn);
      if (substat) {
        flatTotal += substat;
        breakdown.push({ label: "遗器副词条速度", kind: "flat", value: substat });
        manualModifiers.push(modifierOf({ label: "遗器副词条速度", kind: "flat", value: substat, trigger: "passive" }));
      }

      const customPct = num(relicIn, "customPct", 0);
      if (customPct) {
        pctTotal += customPct;
        breakdown.push({ label: "其它速度%", kind: "pct", value: customPct });
        manualModifiers.push(modifierOf({ label: "其它速度%", kind: "pct", value: customPct, trigger: "passive" }));
      }

      const customFlat = num(relicIn, "customFlat", 0);
      if (customFlat) {
        flatTotal += customFlat;
        breakdown.push({ label: "其它固定速度", kind: "flat", value: customFlat });
        manualModifiers.push(modifierOf({ label: "其它固定速度", kind: "flat", value: customFlat, trigger: "passive" }));
      }

      // ---- 遗器套装 / 位面饰品：从套装数据自动带出加速与拉条 ----
      // 规则：
      //   * 拉条 + 每次开大触发（风套）→ 自动 × 开大次数
      //   * 拉条 + 进入战斗触发（翁瓦克）→ 自动一次性
      //   * 速度% / 固定速度 + 无条件 → 自动
      //   * 其它（带条件、按回合、依赖层数）→ 只列出来给你看，不自动计入
      const conditionalEffects = [];
      const pendingAdvance = [];
      const appliedSets = [];
      // 遗器套装里带速度的条目也交给模拟内核（触发方式 + 持续回合 + 层数一起带过去）
      const relicModifiers = [];

      const applySet = (relicId, label, ults, slots) => {
        const relic = find(relics(), relicId);
        if (relic === null) {
          throw new Error("找不到遗器套装 " + pyRepr(relicId));
        }
        const applied = [];
        for (const effect of relic.effects || []) {
          const kind = effect.kind;
          if (kind !== "pct" && kind !== "flat" && kind !== "advance") continue;
          const source = effect.source || "";
          const slot = source.indexOf("4件套") !== -1 ? "4件套" : source.indexOf("2件套") !== -1 ? "2件套" : source;
          if (slots.indexOf(slot) === -1) continue;
          const text = effect.text || "";
          let trigger = triggerOf(text);
          const value = Number(effect.value || 0);
          const record = {
            setId: relic.id,
            setName: relic.name,
            slot: slot,
            kind: kind,
            value: value,
            trigger: trigger,
            text: text,
          };
          if (trigger === "allyUlt" && !relicIn.ultTargetsAlly) {
            conditionalEffects.push(
              Object.assign({}, record, {
                note: "只在对队友施放终结技时触发。勾选「开大目标是队友」后才计入。",
              }),
            );
            continue;
          }
          if (trigger === "allyUlt") {
            trigger = "perUlt";
            record.trigger = "perUlt";
          }
          if (kind === "advance") {
            if (trigger === "perUlt") {
              const countedUlts = effectiveUlts(ults);
              const percent = value * countedUlts;
              if (percent > 0) {
                pendingAdvance.push([
                  relic.name + "·" + slot + " × " + pyG(countedUlts) + " 次开大" + ultNote,
                  percent,
                ]);
                applied.push(Object.assign({}, record, { counted: percent }));
              }
            } else if (trigger === "onEnter") {
              pendingAdvance.push([relic.name + "·" + slot + "（进战触发）", value]);
              applied.push(Object.assign({}, record, { counted: value }));
            } else {
              conditionalEffects.push(record);
            }
          } else if (trigger === "passive") {
            if (kind === "pct") pctTotal += value;
            else flatTotal += value;
            applied.push(Object.assign({}, record, { counted: value }));
            breakdown.push({ label: relic.name + "·" + slot, kind: kind, value: value, text: text });
            relicModifiers.push(
              modifierOf({
                label: relic.name + "·" + slot,
                kind: kind,
                value: value,
                trigger: trigger,
                apply: "self",
              }),
            );
          } else if ((trigger === "perUlt" || trigger === "onEnter") && (kind === "pct" || kind === "flat")) {
            // 速度也有「需要条件才生效」的：例如 4 件套「施放终结技后速度提高 6%」，
            // 进战触发的一次性加成同理。以前这里只处理拉条，速度会被静默丢掉（踩过）。
            let note;
            if (trigger === "perUlt") {
              const countedUlts = effectiveUlts(ults);
              if (countedUlts <= 0) {
                conditionalEffects.push(
                  Object.assign({}, record, { note: "需要开大才触发，当前开大次数为 0" }),
                );
                continue;
              }
              // 开大触发的速度只按**一次**计入（不是乘开大次数），所以标注里要写清。
              // 它**不是开局就生效**的：交给模拟内核，按 firstUltAction 决定从第几次行动起。
              note = "（开大触发" + ultNote + "，按一次计入）";
            } else {
              note = "（进战触发，开局即生效）";
            }
            applied.push(Object.assign({}, record, { counted: value }));
            const relicLabel = relic.name + "·" + slot + note;
            breakdown.push({ label: relicLabel, kind: kind, value: value, text: text });
            const speedMod = modifierOf({
              label: relicLabel,
              kind: kind,
              value: value,
              trigger: trigger,
              apply: "self",
              durationTurns: effect.durationTurns || 0,
              maxStacks: effect.maxStacks || 0,
            });
            if (speedMod.semantics === "constant") {
              // onEnter（没有持续回合的）：开局就生效，等价于旧算法的「直接加进总和」
              if (kind === "pct") pctTotal += value;
              else flatTotal += value;
            }
            // 开大触发 / 叠层不能并进 S0；constant 的也收进列表，模拟时间线要用它算速度
            relicModifiers.push(speedMod);
          } else {
            conditionalEffects.push(record);
          }
        }
        if (applied.length) {
          appliedSets.push({ label: label, setId: relic.id, setName: relic.name, effects: applied });
        }
      };

      const fourPieceId = relicIn.fourPieceId;
      if (pyBool(fourPieceId)) {
        applySet(pyStrNum(fourPieceId), "遗器 4 件套", num(relicIn, "fourPieceUlts", 0), ["2件套", "4件套"]);
      }
      // 位面饰品只留一个栏位（2 件套效果按一次算）
      const ornamentIds = relicIn.ornamentIds || [];
      for (const ornamentId of ornamentIds.slice(0, 1)) {
        if (pyBool(ornamentId)) {
          applySet(pyStrNum(ornamentId), "位面饰品", 0, ["2件套"]);
        }
      }

      // ---- 勾选的速度类效果（勾上就计入：全队类也一样，勾选本身就是你的判断）----
      const applied = [];
      const effectModifiers = [];
      // 勾选的条目也要标出触发方式，和遗器套装的标注口径保持一致
      const TRIGGER_NOTES = {
        perUlt: "（开大触发）",
        allyUlt: "（对队友开大触发）",
        onEnter: "（进战触发）",
        conditional: "（有条件）",
      };
      for (const effect of speedEffects) {
        if (!enabledSet[String(effect.id)]) continue;
        const value = Number(effect.value || 0);
        const isTeam = effect.apply === "team";
        // apply == "ally"（「被指定的我方目标」「得到【赐福】的我方单体」这类）：
        // 提速加在**队友**身上，不是这个角色 —— 照旧列出来让界面标注「仅队友」，
        // 但模拟内核不收，也不并进 S0。
        const isAlly = effect.apply === "ally";
        // apply == "enemy"：作用在敌人身上，勾上也绝不计入本角色
        const isEnemy = effect.apply === "enemy";
        applied.push(Object.assign({}, effect, { counted: true, countedForSelf: !(isAlly || isEnemy) }));
        const label =
          // 顺序不能反：先触发标注，再全队标注
          (effect.origin + "·" + (effect.name || "")).replace(/^·+/, "").replace(/·+$/, "") +
          (TRIGGER_NOTES[effect.trigger] || "") +
          (isTeam ? "（全队）" : "") +
          (isAlly ? "（仅队友，不计入本角色）" : "") +
          (isEnemy ? "（作用于敌方，不计入本角色）" : "");
        breakdown.push({
          label: label,
          kind: effect.kind,
          value: value,
          text: effect.text,
          team: isTeam,
          ally: isAlly,
        });
        if (isAlly || isEnemy) continue;
        const speedMod = modifierOf({
          label: label,
          kind: effect.kind,
          value: value,
          trigger: effect.trigger || "passive",
          apply: effect.apply || "self",
          durationTurns: effect.durationTurns || 0,
          maxStacks: effect.maxStacks || 0,
        });
        if (speedMod.semantics === "constant") {
          // 一直生效的那部分照旧直接并进总和（= 未加速速度 S0 的加成口径）
          if (effect.kind === "pct") pctTotal += value;
          else flatTotal += value;
        }
        // 开大触发 / 叠层不进 pctTotal，交给模拟内核按行动次数算；
        // constant 的也收进列表，模拟时间线要用它算每一步的速度。
        effectModifiers.push(speedMod);
      }

      // 全部速度修饰（手填 + 遗器套装 + 勾选的角色/光锥效果）。
      // constant 那批同时也已经并进 pctTotal / flatTotal 了，这里收着是为了让
      // **模拟时间线**每一步都能算出正确速度。
      const speedModifiers = manualModifiers.concat(relicModifiers, effectModifiers);
      // 只有「随行动变化」的才需要走模拟 / 二分
      const timelineModifiers = speedModifiers.filter((item) => (item.semantics || "constant") !== "constant");

      // 未加速速度 S0：不含「随行动变化」的加速（开大触发 / 叠层），也不含仅队友的。
      // 基础白值参与百分比，行迹固定值和其他固定值最后相加。
      const constPct = pctTotal;
      const constFlat = flatTotal;
      const finalSpeed = gameBase * (1 + constPct / 100.0) + traceFlat + constFlat;
      if (finalSpeed < 120) {
        for (let i = appliedSets.length - 1; i >= 0; i -= 1) {
          const entry = appliedSets[i];
          const kept = [];
          for (const effect of entry.effects) {
            if (effect.kind === "advance" && effect.trigger === "onEnter") {
              conditionalEffects.push(Object.assign({}, effect, { note: "速度未到 120，未计入" }));
            } else {
              kept.push(effect);
            }
          }
          if (kept.length) entry.effects = kept;
          else appliedSets.splice(i, 1);
        }
      }

      // ---- 拉条 ----
      const advanceItems = [];
      const openingItems = [];
      let advanceTotal = 0.0;
      const warnings = [];
      const pendingText = pendingAdvance.map((item) => item[0]).join(" ");

      const addAdvance = (label, percent, opening) => {
        if (percent <= 0) return;
        const record = { label: label, percent: percent };
        if (opening) {
          openingItems.push(record);
          return;
        }
        advanceTotal += percent;
        advanceItems.push(record);
      };

      const windUlts = effectiveUlts(num(advanceIn, "windUlts", 0));
      if (windUlts > 0 && pendingText.indexOf("翔鹰") === -1) {
        addAdvance("风套 4 件套 × " + pyG(windUlts) + " 次开大（每次 25%）" + ultNote, 25 * windUlts);
      }

      const danceUlts = effectiveUlts(num(advanceIn, "danceUlts", 0));
      const danceS = Math.max(1, Math.min(pyInt(num(advanceIn, "danceSuperimpose", 5)), 5));
      const dancePerUlt = { 1: 16, 2: 18, 3: 20, 4: 22, 5: 24 }[danceS];
      // 已选「舞！舞！舞！」且按 coneUlts 计了拉条时，手填 danceUlts 不再重复计
      const coneUltsCounted = effectiveUlts(num(advanceIn, "coneUlts", 0));
      const danceFromCone = !!(cone && cone.name === "舞！舞！舞！" && coneUltsCounted > 0);
      if (danceUlts > 0 && !danceFromCone) {
        addAdvance(
          "舞！舞！舞！叠影" + danceS + " × " + pyG(danceUlts) + " 次开大（每次 " + dancePerUlt + "%）" + ultNote,
          dancePerUlt * danceUlts,
        );
      }

      if (advanceIn.vonwacq && pendingText.indexOf("翁瓦克") === -1) {
        if (finalSpeed >= 120) {
          addAdvance("翁瓦克（生命的翁瓦克）进战一次 40%", 40, true);
        } else {
          warnings.push(
            "翁瓦克需要装备者速度 ≥ 120 才会触发进战拉条；当前算出来是 " + pyFixed(finalSpeed, 1) + "，未计入。",
          );
        }
      }

      const extraAdvance = num(advanceIn, "custom", 0);
      if (extraAdvance) {
        addAdvance("其它拉条 " + pyG(extraAdvance) + "%", extraAdvance);
      }

      // 遗器套装 / 位面饰品带出来的拉条（风套的开大拉条、翁瓦克的进战拉条都在这里）
      for (const [label, percent] of pendingAdvance) {
        if (label.indexOf("进战") !== -1 && finalSpeed < 120) {
          warnings.push(label + " 需要装备者速度 ≥ 120 才触发；当前算出来是 " + pyFixed(finalSpeed, 1) + "，未计入。");
          continue;
        }
        addAdvance(label, percent, label.indexOf("进战") !== -1);
      }

      // 光锥自带的拉条（舞！舞！舞！这类）：数值由叠影决定，开大次数你填多少就乘多少
      const coneAdvance = [];
      const coneConditional = [];
      const coneUlts = num(advanceIn, "coneUlts", 0);
      if (cone) {
        for (const effect of advanceEffects) {
          if (effect.origin !== "光锥") continue;
          const text = effect.text || "";
          const trigger = triggerOf(text);
          const value = Number(effect.value || 0);
          const record = {
            coneName: cone.name,
            superimpose: superimpose,
            value: value,
            trigger: trigger,
            text: text,
          };
          if (trigger === "perUlt") {
            const countedUlts = effectiveUlts(coneUlts);
            if (countedUlts > 0) {
              addAdvance(
                cone.name + " 叠影" + superimpose + " × " + pyG(countedUlts) + " 次开大" + ultNote,
                value * countedUlts,
              );
              record.counted = value * countedUlts;
            }
            coneAdvance.push(record);
          } else if (trigger === "onEnter") {
            addAdvance(cone.name + "（进战触发）", value, true);
            coneAdvance.push(Object.assign({}, record, { counted: value }));
          } else {
            coneConditional.push(record);
          }
        }
      }

      let openingSum = 0;
      for (const item of openingItems) openingSum += Number(item.percent);
      if (openingSum > 100 && openingItems.length) {
        const scale = 100.0 / openingSum;
        warnings.push(
          "进战拉条合计 " + pyG(openingSum) + "%，同一次行动超出 100% 的部分不带到下一次，已按 100% 计入。",
        );
        for (const item of openingItems) item.percent = Number(item.percent) * scale;
      }
      for (const item of openingItems) {
        advanceTotal += Number(item.percent);
        advanceItems.push(item);
      }

      // ---- 各模式阈值表 ----
      const modes = modesData();
      const cycles = modes.cycles;
      const distance = Number(cycles.distancePerAction || 10000);
      const firstAv = Number(cycles.firstCycleAV || 150);
      const stepAv = Number(cycles.cycleAV || 100);
      const targets = modes.targets;
      const minActions = toInt(targets.minActions || 1);
      const maxActions = toInt(targets.maxActions || 8);
      const advanceDistance = (advanceTotal / 100.0) * distance;

      // ---- 行动模拟：真的把角色一次一次行动走出来 ----
      const simulationIn = p.simulation || {};
      // 第一次开大发生在自己第几次行动**之后**（默认 1：第 1 次行动后开大）
      const firstUltAction = Math.max(0, pyInt(num(simulationIn, "firstUltAction", 1)));

      /** 按给定的「未加速速度 S0」把行动模拟出来（加速按各自时点叠加）。 */
      const animate = (speed0, windowAv, cap, extraFlat, extraModifiers) => {
        const flatAdd = extraFlat === undefined ? 0.0 : extraFlat;
        const extra = extraModifiers === undefined ? [] : extraModifiers;
        return simulate(gameBase, timelineModifiers.concat(extra), {
          speed0: speed0 + flatAdd,
          windowAv: windowAv,
          firstUltAction: firstUltAction,
          distance: distance,
          advanceDistance: advanceDistance,
          actionCap: cap,
        });
      };

      /** 按**当前配置**把行动模拟出来（界面展示时间线用）。 */
      const simulateCurrent = (windowAv, cap) =>
        simulate(gameBase, speedModifiers, {
          windowAv: windowAv,
          firstUltAction: firstUltAction,
          distance: distance,
          advanceDistance: advanceDistance,
          actionCap: cap,
        });

      /** 当前 S0 在该窗口内能打完几次（没有时间线加速时用旧公式，逐位一致）。 */
      const achievedWith = (speed0, windowAv, actions) => {
        if (!anyTimeline(timelineModifiers)) {
          return Math.max(0, toInt(Math.floor((speed0 * windowAv + advanceDistance) / distance + 1e-9)));
        }
        return animate(speed0, windowAv, Math.max(1, toInt(actions) + 1)).completed;
      };

      /** 要 actions 次行动落在 windowAv 内，需要多少「未加速速度 S0」。 */
      const speedNeeded = (actions, windowAv, addFlat, addPct, addAdvance, extraModifiers) => {
        const extraFlat = addFlat === undefined ? 0.0 : addFlat;
        const extraPct = addPct === undefined ? 0.0 : addPct;
        const extraAdvance = addAdvance === undefined ? 0.0 : addAdvance;
        const extra = extraModifiers === undefined ? [] : extraModifiers;
        const advanceDistanceNew = advanceDistance + (extraAdvance / 100.0) * distance;
        if (!anyTimeline(timelineModifiers)) {
          return Math.max(0.0, (actions * distance - advanceDistanceNew) / windowAv);
        }
        const mods = timelineModifiers.concat(extra);
        // 直道先估一个量级当上界：再差的配置也不会超过它 4 倍
        const estimate =
          gameBase * (1 + (constPct + extraPct + 40) / 100.0) + traceFlat + constFlat + extraFlat + 60;
        const high = Math.max(1000.0, estimate * 4.0);
        return requiredSpeed(gameBase, mods, {
          actions: actions,
          avLimit: windowAv,
          advanceDistance: advanceDistanceNew,
          distance: distance,
          firstUltAction: firstUltAction,
          low: 0.0,
          high: high,
        });
      };

      const requiredSpeedFor = (actions, windowAv) => speedNeeded(actions, windowAv);
      const reachable = (actions, windowAv) => achievedWith(finalSpeed, windowAv, actions) >= actions;

      const tables = [];
      const tableCache = new Map();
      for (const mode of modes.modes) {
        const modeFirst = Number(mode.firstCycleAV || firstAv);
        const modeStep = Number(mode.cycleAV || stepAv);
        const maxT = toInt(mode.maxT || 3);
        const tValues = [];
        for (let t = 0; t <= maxT; t += 1) tValues.push(t);
        const rows = [];
        for (let actions = minActions; actions <= maxActions; actions += 1) {
          const cells = [];
          for (const t of tValues) {
            const totalAv = modeFirst + t * modeStep;
            // 表格单元格和 verdict 同一口径：需求速度 = 需要多少「未加速速度」。
            // 有开大/叠层加速时这里是**真的模拟**出来的（逐格二分），
            // 没有时就是闭式公式，和旧算法逐位一致。
            const key = `${actions}:${totalAv}`;
            if (!tableCache.has(key)) tableCache.set(key, {
              speed: Math.max(0.0, speedNeeded(actions, totalAv)),
              reachable: reachable(actions, totalAv),
            });
            const cached = tableCache.get(key);
            cells.push({
              t: t,
              totalAV: totalAv,
              speed: cached.speed,
              reachable: cached.reachable,
            });
          }
          rows.push({ actions: actions, cells: cells });
        }
        tables.push({
          id: mode.id,
          name: mode.name,
          shortName: mode.shortName,
          note: mode.note,
          stars: mode.stars || [],
          firstCycleAV: modeFirst,
          cycleAV: modeStep,
          tValues: tValues,
          rows: rows,
        });
      }

      // ---- 单点结论：用户指定的目标 ----
      const targetIn = p.target || {};
      const targetT = Math.max(0, pyInt(num(targetIn, "t", 0)));
      const targetActions = Math.max(1, pyInt(num(targetIn, "actions", 2)));
      // 目标属于哪个模式，就用哪个模式的首轮行动值（异相仲裁首轮是 300，不是 150）
      const targetMode = modeById(modes, pyStr(targetIn.mode || ""));
      const baseFirst = Number((targetMode || {}).firstCycleAV || firstAv);
      const baseStep = Number((targetMode || {}).cycleAV || stepAv);
      // 也可以直接给一个行动值节点，给了就优先用
      const customAv = num(targetIn, "customAV", 0);
      const targetAv = customAv > 0 ? customAv : baseFirst + targetT * baseStep;
      checkTarget(targetActions, targetAv);
      // 需求速度 / 当前速度都用 S0 口径（「还差多少速」才有意义）
      const required = Math.max(0.0, speedNeeded(targetActions, targetAv));
      const gap = required - finalSpeed;

      // 模拟明细：时间线 + 说明，界面直接展示。
      // 时间线固定走满 12 步（不跟着 target.actions 缩），否则目标只写 2 动时
      // 根本看不出「第 3 次行动加速就过期了」这种回落。
      const simRun = simulateCurrent(targetAv, null);
      // 当前速度在该行动值下能打几次：没有随行动变化的加速 → 与旧公式逐位一致的闭式口径；
      // 有 → 用模拟出来的真实时间线数。
      const achievableActions = anyTimeline(timelineModifiers)
        ? simRun.completed
        : achievedWith(finalSpeed, targetAv, targetActions);
      const simulation = {
        firstUltAction: firstUltAction,
        windowAV: targetAv,
        achievedActions: achievableActions,
        completedActions: simRun.completed,
        timeline: simRun.timeline,
        notes: simulationNotes(timelineModifiers, firstUltAction),
      };

      // ---- 补足建议：差速度的时候，具体有哪些办法、各自能到多少 ----
      const evaluate = (opts) => {
        const addFlat = opts && opts.addFlat ? opts.addFlat : 0;
        const addPct = opts && opts.addPct ? opts.addPct : 0;
        const addAdvanceValue = opts && opts.addAdvance ? opts.addAdvance : 0;
        const speed = gameBase * (1 + (constPct + addPct) / 100.0) + traceFlat + constFlat + addFlat;
        const need = Math.max(
          0.0,
          speedNeeded(targetActions, targetAv, addFlat, addPct, addAdvanceValue),
        );
        return {
          speed: speed,
          required: need,
          gap: need - speed,
          ok: need <= speed + 1e-9,
        };
      };

      const suggestions = [];
      if (gap > 1e-9) {
        // 只堆副词条/固定速度需要多少
        const neededFlat = required - gameBase * (1 + constPct / 100.0) - traceFlat;
        const extraFlat = neededFlat - constFlat;
        if (extraFlat > 0) {
          suggestions.push(
            Object.assign({ label: "副词条/固定速度再堆 " + pyFixed(extraFlat, 1) + " 点" }, evaluate({ addFlat: extraFlat })),
          );
        }
        if (!relicIn.speedBoots) {
          suggestions.push(Object.assign({ label: "换上速度鞋（+25）" }, evaluate({ addFlat: SPEED_BOOTS_FLAT })));
        }
        if (!relicIn.fourPieceId) {
          suggestions.push(
            Object.assign(
              { label: "遗器 4 件套换风套（按 1 次开大算，拉条 25%）" },
              evaluate({ addAdvance: 25 }),
            ),
          );
        }
        if (!(relicIn.ornamentIds || [null])[0] && !advanceIn.vonwacq) {
          suggestions.push(
            Object.assign(
              { label: "位面饰品换翁瓦克（进战拉条 40%，需速度 ≥ 120）" },
              evaluate({ addAdvance: 40 }),
            ),
          );
        }
        suggestions.push(Object.assign({ label: "遗器 2 件套叠速度 6%" }, evaluate({ addPct: 6 })));
        // 按效果排序：能达成的排前面，其次差距小的
        suggestions.sort(cmpBy([(item) => !item.ok, (item) => Math.abs(item.gap)]));
      }

      const verdictText =
        ((targetMode || {}).name === undefined ? "" : (targetMode || {}).name) +
        " " +
        (customAv > 0 ? pyG(customAv) + " AV 节点" : targetT + "T（" + pyG(targetAv) + " AV）") +
        " 内打 " +
        targetActions +
        " 动需要 " +
        pyFixed(required, 2) +
        " 速，" +
        (gap <= 1e-9
          ? "你现在 " + pyFixed(finalSpeed, 2) + " 速，够。"
          : "你现在 " + pyFixed(finalSpeed, 2) + " 速，还差 " + pyFixed(gap, 2) + " 速。");

      return {
        character: {
          id: character.id,
          name: character.name,
          path: character.path,
          pathName: character.pathName,
          elementName: character.elementName,
          rarity: character.rarity,
          baseSpeed: baseSpeed,
        },
        lightcone: cone
          ? {
              id: cone.id,
              name: cone.name,
              pathName: cone.pathName,
              rarity: cone.rarity,
            }
          : null,
        eidolon: eidolon,
        superimpose: superimpose,
        speed: {
          base: baseSpeed,
          baseRaw: gameBase,
          traceSpeed: traceFlat,
          traceSpeedPct: tracePct,
          // pct / flat / final 都是「未加速速度 S0」口径：不含开大触发与叠层这类
          // 随行动变化的加速（它们体现在 simulation.timeline 里）。
          pct: constPct,
          flat: constFlat,
          final: finalSpeed,
          pctAll: pctTotal,
          flatAll: flatTotal,
          hasTimeline: anyTimeline(timelineModifiers),
          formula:
            pyG(gameBase) +
            " × (1 + " + pyG(constPct) + "%)" + (traceFlat ? " + 行迹 " + pyG(traceFlat) : "") + " + " + pyG(constFlat) + " = " + pyFixed(finalSpeed, 2) +
            (anyTimeline(timelineModifiers) ? "（未加速速度；加速随行动生效，见 simulation）" : ""),
          breakdown: breakdown,
        },
        effects: {
          speed: speedEffects,
          advance: advanceEffects,
          enabled: enabled.slice().sort(),
          conditional: conditionalEffects,
          coneAdvance: coneAdvance,
          coneConditional: coneConditional,
        },
        relicSets: appliedSets,
        advance: {
          total: advanceTotal,
          distance: advanceDistance,
          items: advanceItems,
          excludeLastUlt: excludeLastUlt,
        },
        simulation: simulation,
        tables: tables,
        suggestions: suggestions,
        verdict: {
          t: targetT,
          actions: targetActions,
          totalAV: targetAv,
          customAV: customAv,
          mode: targetMode
            ? {
                id: targetMode.id,
                name: targetMode.name,
                firstCycleAV: baseFirst,
                cycleAV: baseStep,
              }
            : null,
          requiredSpeed: required,
          currentSpeed: finalSpeed,
          gap: gap,
          achievableActions: achievableActions,
          text: verdictText,
        },
        warnings: warnings,
      };
    }

    // ----------------------------------------------------------------------- #
    // 我的配装（storage 里存，浏览器版由外壳落到 localStorage）
    // ----------------------------------------------------------------------- #

    /** 列出已存的配装（按角色 id 索引）。 */
    function presets(payload) {
      const store = loadPresets();
      return { presets: store, count: Object.keys(store).length };
    }

    /** 把当前这套配置存到这个角色名下。 */
    function savePreset(payload) {
      const p = payload || {};
      const characterId = pyStrip(p.characterId || "");
      if (!characterId) {
        throw new Error("缺少 characterId");
      }
      const config = p.config;
      if (!isDict(config)) {
        throw new Error("缺少 config（要存的配置对象）");
      }
      validateSubstatSpeed(config.relic || {});

      const character = find(characters(), characterId);
      const store = loadPresets();
      store[characterId] = {
        name: pyStr(p.name || (character || {}).name || characterId),
        savedAt: nowStamp(),
        config: config,
      };
      presetStore.save(store);
      return { saved: characterId, count: Object.keys(store).length, path: null };
    }

    function deletePreset(payload) {
      const p = payload || {};
      const characterId = pyStrip(p.characterId || "");
      const store = loadPresets();
      delete store[characterId];
      presetStore.save(store);
      return { deleted: characterId, count: Object.keys(store).length };
    }

    // ----------------------------------------------------------------------- #
    // 自动推荐配装
    // ----------------------------------------------------------------------- #

    /** 光锥能提供的 (速度%, 固定速度, 拉条%)。只取无条件和开大触发的。 */
    function coneContribution(cone, superimpose, ults) {
      if (!cone) return [0.0, 0.0, 0.0];
      let pct = 0.0;
      let flat = 0.0;
      let advance = 0.0;
      for (const effect of cone.effects || []) {
        if (!(effect.superimpose === undefined || effect.superimpose === null || effect.superimpose === superimpose)) {
          continue;
        }
        const text = effect.text || "";
        const trigger = triggerOf(text);
        const kind = effect.kind;
        const value = Number(effect.value || 0);
        if (kind === "advance") {
          if (trigger === "perUlt") advance += value * ults;
          else if (trigger === "onEnter") advance += value;
        } else if (trigger === "passive") {
          if (kind === "pct") pct += value;
          else if (kind === "flat") flat += value;
        }
      }
      return [pct, flat, advance];
    }

    /** 遗器套装的 (速度%, 固定速度, 拉条%, 是否要求速度≥120)。 */
    function setContribution(relic, slots, ults) {
      if (!relic) return [0.0, 0.0, 0.0, false];
      let pct = 0.0;
      let flat = 0.0;
      let advance = 0.0;
      let needs120 = false;
      for (const effect of relic.effects || []) {
        if (slots.indexOf(effect.slot) === -1) continue;
        const text = effect.text || "";
        const trigger = effect.trigger || triggerOf(text);
        const kind = effect.kind;
        const value = Number(effect.value || 0);
        if (kind === "advance") {
          if (trigger === "perUlt") {
            advance += value * ults;
          } else if (trigger === "onEnter") {
            advance += value;
            if (text.indexOf("120") !== -1) needs120 = true;
          }
        } else if (trigger === "passive") {
          if (kind === "pct") pct += value;
          else if (kind === "flat") flat += value;
        }
      }
      return [pct, flat, advance, needs120];
    }

    /**
     * 穷举这个角色能用的光锥与遗器组合，给出「达成目标最省」的几套。
     *
     * 说明：这是**自动推荐**——在你的可选范围内算出来的最优解，不是社区主流配装表
     * （那个数据源米游社详情接口拿不到，见 README）。
     */
    function recommend(payload) {
      const p = payload || {};
      const character = resolveCharacter(p);
      const gameBase = Number(character.baseSpeed || 0);
      const traceFlat = Number(character.traceSpeed || 0);
      const baseSpeed = gameBase + traceFlat;
      if (baseSpeed <= 0) {
        throw new Error(character.name + " 没有基础速度数据");
      }

      const modes = modesData();
      const cycles = modes.cycles;
      const distance = Number(cycles.distancePerAction || 10000);
      const firstAv = Number(cycles.firstCycleAV || 150);
      const stepAv = Number(cycles.cycleAV || 100);

      const targetIn = p.target || {};
      const targetT = Math.max(0, pyInt(num(targetIn, "t", 0)));
      const actions = Math.max(1, pyInt(num(targetIn, "actions", 2)));
      const customAv = num(targetIn, "customAV", 0);
      // 目标模式决定首轮行动值（异相仲裁首轮 300，不是 150）
      const targetMode = modeById(modes, pyStr(targetIn.mode || ""));
      const modeFirst = Number((targetMode || {}).firstCycleAV || firstAv);
      const modeStep = Number((targetMode || {}).cycleAV || stepAv);
      const targetAv = customAv > 0 ? customAv : modeFirst + targetT * modeStep;
      checkTarget(actions, targetAv);

      const relicIn = p.relic || {};
      const useBoots = pyBool(relicIn.speedBoots === undefined ? true : relicIn.speedBoots);
      const superimpose = Math.max(1, Math.min(pyInt(num(p, "superimpose", 1)), 5)); // 默认叠影 1
      let coneUlts = Math.max(0.0, num(p, "coneUlts", 1));
      let fourUlts = Math.max(0.0, num(p, "fourPieceUlts", 1));
      const limit = Math.max(1, Math.min(pyInt(num(p, "maxResults", 10)), 30));
      const excludeLastUlt = pyBool(p.excludeLastUlt);
      if (excludeLastUlt) {
        coneUlts = Math.max(0.0, coneUlts - 1);
        fourUlts = Math.max(0.0, fourUlts - 1);
      }

      // 候选：同命途光锥（星级高、速度相关优先）
      // 自定义角色不限命途：在全部光锥里挑
      let cones = lightconesData().filter((item) => character.custom || item.path === character.path);
      cones = cones.slice().sort(
        cmpBy([
          (item) => -(item.rarity || 0),
          (item) => -(item.effects || []).filter((e) => e.kind === "pct" || e.kind === "flat" || e.kind === "advance").length,
          (item) => item.name || "",
        ]),
      );
      cones = cones.slice(0, 6);

      // 遗器候选要按「和配速有没有关系」挑，跟界面上的推出顺序解耦，
      // 否则我改一次显示顺序，推荐结果就会跟着变差。
      const options = relicEffectOptions(relics());
      const fourPiece = options.fourPiece
        .slice()
        .sort(cmpBy([(item) => !item.hasSpeedEffect, (item) => item.name || ""]));
      const ornaments = options.ornaments
        .slice()
        .sort(cmpBy([(item) => !item.hasSpeedEffect, (item) => item.name || ""]));

      const fourChoices = [null].concat(fourPiece).map(item => [item, setContribution(item, ["2件套", "4件套"], fourUlts)]);
      const ornamentChoices = [null].concat(ornaments).map(item => [item, setContribution(item, ["2件套"], 0)]);
      const results = [];
      for (const cone of [null].concat(cones)) {
        const [conePct, coneFlat, coneAdvanceValue] = coneContribution(cone, superimpose, coneUlts);
        for (const [four, fourValues] of fourChoices) {
          const [fourPct, fourFlat, fourAdvance, fourNeeds120] = fourValues;
          // 位面饰品只有一个栏位（和界面一致）
          for (const [ornament, ornamentValues] of ornamentChoices) {
            let pct = conePct + fourPct;
            let flat = coneFlat + fourFlat;
            let advance = coneAdvanceValue + fourAdvance;
            let needs120Advance = 0.0;
            const pending120Labels = [];

            if (ornament !== null) {
              const [oPct, oFlat, oAdvance, oNeeds120] = ornamentValues;
              pct += oPct;
              flat += oFlat;
              if (oNeeds120) {
                needs120Advance += oAdvance;
                pending120Labels.push(ornament.name);
              } else {
                advance += oAdvance;
              }
            }
            if (fourNeeds120) {
              pending120Labels.push(four.name);
            }

            if (useBoots) flat += SPEED_BOOTS_FLAT;
            const speedNoSubstat = gameBase * (1 + pct / 100.0) + traceFlat + flat;

            // 速度不到 120 时，翁瓦克这类进战拉条不生效
            let effectiveAdvance = advance;
            const notes = [];
            if (needs120Advance) {
              if (speedNoSubstat >= 120) {
                effectiveAdvance += needs120Advance;
              } else {
                notes.push(
                  pending120Labels.join("、") +
                    " 的进战拉条要求速度 ≥ 120，当前 " +
                    pyFixed(speedNoSubstat, 0) +
                    " 速未触发，未计入",
                );
              }
            }

            const required = Math.max(
              0.0,
              (actions * distance - (effectiveAdvance / 100.0) * distance) / targetAv,
            );
            const needed = Math.max(0.0, required - speedNoSubstat);

            results.push({
              // 「不装备/不指定」在 Python 里是 None，导出成 JSON 就是 null，
              // 这里必须显式给 null，不能留 undefined
              coneId: cone ? cone.id : null,
              coneName: (cone || {}).name || "（不装备光锥）",
              fourPieceId: four ? four.id : null,
              fourPieceName: (four || {}).name || "（不指定）",
              ornamentIds: [ornament ? ornament.id || "" : ""],
              ornamentNames: [ornament ? ornament.name || "" : ""],
              speed: speedNoSubstat,
              advance: effectiveAdvance,
              required: required,
              neededSubstatSpeed: needed,
              ok: needed <= 1e-9,
              notes: notes,
            });
          }
        }
      }

      results.sort(
        cmpBy([
          (item) => item.neededSubstatSpeed,
          (item) => -item.advance,
          (item) => item.coneName,
        ]),
      );
      // 去重：结果一样的（速度、拉条、是否达成）只留最省的那一条，
      // 否则前几名会是一堆等效方案，看不出区别。
      const deduped = [];
      const seen = {};
      for (const item of results) {
        const signature = round1(item.speed) + "|" + round1(item.advance) + "|" + item.ok;
        if (seen[signature]) continue;
        seen[signature] = true;
        deduped.push(item);
      }
      const top = deduped.length ? deduped.slice(0, limit) : results.slice(0, limit);

      return {
        character: { id: character.id, name: character.name, baseSpeed: baseSpeed },
        target: { t: targetT, actions: actions, totalAV: targetAv, customAV: customAv },
        assumptions: {
          speedBoots: useBoots,
          superimpose: superimpose,
          coneUlts: coneUlts,
          fourPieceUlts: fourUlts,
          excludeLastUlt: excludeLastUlt,
        },
        evaluated: results.length,
        results: top,
        note: "自动推荐：在你的可选范围内穷举得出的最省方案，不是社区主流配装表。",
      };
    }

    const ACTIONS = {
      catalog: catalog,
      lightcones: lightcones,
      plan: plan,
      recommend: recommend,
      presets: presets,
      save_preset: savePreset,
      delete_preset: deletePreset,
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
      /** 调试/自检用：把关键内部函数露出来，方便和 Python 对拍。 */
      _internals: {
        triggerOf: triggerOf,
        round1: round1,
        pyG: pyG,
        pyFixed: pyFixed,
      },
    };
  }

  return {
    createApi: createApi,
    trigger_of: triggerOf,
    PRESET_KEY: PRESET_KEY,
    DEFAULT_CYCLES: DEFAULT_CYCLES,
    SPEED_BOOTS_FLAT: SPEED_BOOTS_FLAT,
  };
});
