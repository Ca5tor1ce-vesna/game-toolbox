"""崩铁配速查询。

速度合成（游戏规则）
--------------------
    最终速度 = 基础速度 × (1 + 速度百分比之和) + 固定速度之和

百分比只作用在**基础速度**上，固定速度加在最后 —— 顺序搞反结果会差很多。

行动模拟（有些加速不是开局就生效的）
------------------------------------
静态公式默认所有加速从第 1 次行动就生效，但游戏里有两类不是：
  * **开大触发**（信使 4 件套「施放终结技后我方全体速度提高 12%」）——
    第一次开大之前根本没有，之后也只持续 durationTurns 次自己的行动；
  * **叠层**（只需等待「每次施放攻击后速度提高 8%，最多叠 3 层」）——
    第 k 次行动前只有 min(k−1, N) 层。
所以本模块会**真的把角色一次一次行动走出来**（见 `_simulate`）：
第 k 次行动用当时生效的增益算速度，AV += 距离 / 速度，直到超过窗口行动值。

「未加速速度 S0」= 基础速度(含行迹) × (1 + 常驻pct/100) + 常驻flat，
不含上面那两类随行动变化的加速。`verdict.requiredSpeed` / 表格单元格 /
`verdict.currentSpeed` 都是 S0 口径，这样界面上的「还差多少速」才有意义。
没有任何随行动变化的加速时走闭式公式，结果与改动前的算法**逐位一致**。

需求速度（与「配速排轴」「阿哈时刻配速」同一套模型）
----------------------------------------------------
    需求速度 = (动数 × 10000 − 拉条总量) ÷ (150 + T × 100)
    拉条总量 = Σ(拉条% × 10000)

拉条来源：风套 4 件套每次开大 25%、舞！舞！舞！每次开大全队 16~24%（看叠影）、
翁瓦克（生命的翁瓦克）进战一次 40%、以及自定义。拉条和加速是两回事：
拉条直接改「还差多少距离」，加速改的是行动速度。

数据来源
--------
角色基础速度、光锥/星魂/技能/行迹/遗器的速度与拉条效果，全部由
`tools/import_hsr_data.py` 从米游社官方图鉴 + StarRailRes 抓取并**自动抽取**。
自动抽取出来的是「候选」，条件是否成立要看实战，所以界面上要你自己勾选 ——
工具负责把原文摆在你面前，不替你判断。
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from core.feature_api import api

DEFAULT_CYCLES = {"firstCycleAV": 150, "cycleAV": 100, "distancePerAction": 10000}
SPEED_BOOTS_FLAT = 25  # 遗器主词条「速度」鞋


# --------------------------------------------------------------------------- #
# 数据读取
# --------------------------------------------------------------------------- #

def _characters(ctx) -> list[dict[str, Any]]:
    data = ctx.data("characters")
    if not isinstance(data, list) or not data:
        raise ValueError(
            "角色数据为空：先跑一次 `python tools/import_hsr_data.py` 把米游社数据抓下来"
        )
    return data


def _lightcones(ctx) -> list[dict[str, Any]]:
    data = ctx.data("lightcones")
    if not isinstance(data, list):
        raise ValueError("光锥数据缺失，先跑 `python tools/import_hsr_data.py`")
    return data


def _relics(ctx) -> list[dict[str, Any]]:
    data = ctx.data("relic_sets")
    return data if isinstance(data, list) else []


def _modes(ctx) -> dict[str, Any]:
    data = ctx.data("modes") or {}
    defaults = {**DEFAULT_CYCLES, **(data.get("cycles") or {})}
    modes: list[dict[str, Any]] = []
    for mode in data.get("modes") or []:
        # 每个模式可以有自己的首轮/每轮行动值（异相仲裁首轮就是 400）
        modes.append(
            {
                **mode,
                "firstCycleAV": float(mode.get("firstCycleAV", defaults["firstCycleAV"])),
                "cycleAV": float(mode.get("cycleAV", defaults["cycleAV"])),
            }
        )
    return {
        "modes": modes,
        "cycles": defaults,
        "targets": data.get("targets") or {"minActions": 1, "maxActions": 8},
        "meta": data.get("meta") or {},
    }


def _mode_by_id(modes: dict[str, Any], mode_id: str) -> dict[str, Any] | None:
    for mode in modes["modes"]:
        if mode.get("id") == mode_id:
            return mode
    return None


def _num(payload: dict[str, Any], key: str, default: float = 0.0) -> float:
    value = payload.get(key, default)
    if value is None or value == "":
        return float(default)
    # 只认 ASCII 数字串（与网页版 web_api.js 一致：全角「１２」两边都拒绝）
    if isinstance(value, str) and not value.strip().isascii():
        raise ValueError(f"参数 {key} 需要是数字，收到 {value!r}")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"参数 {key} 需要是数字，收到 {value!r}") from exc
    # inf / nan / 天文数字一律拒绝（旧版会在后面 int() / 乘法里 500，且不报字段名）
    if not math.isfinite(number) or abs(number) > NUM_LIMIT:
        raise ValueError(f"参数 {key} 超出范围，收到 {value!r}")
    return number


def _check_target(actions: int, window_av: float) -> None:
    if actions > SIM_MAX_ACTIONS:
        raise ValueError(f"目标动数最多 {SIM_MAX_ACTIONS}，收到 {actions}")
    if window_av > MAX_WINDOW_AV:
        raise ValueError(f"行动值节点最多 {MAX_WINDOW_AV:g}，收到 {window_av:g}")


def _id_str(value: Any) -> str:
    """id 统一成字符串；1005.0 这种整数值浮点当成 "1005"（与网页版一致）。"""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _find(items: list[dict[str, Any]], item_id: str) -> dict[str, Any] | None:
    for item in items:
        if _id_str(item.get("id")) == _id_str(item_id):
            return item
    return None


# --------------------------------------------------------------------------- #
# 遗器套装的触发方式
# --------------------------------------------------------------------------- #

def trigger_of(text: str) -> str:
    """判断一条效果什么时候生效——这决定了它能不能自动计入。"""
    if "施放终结技" in text:
        # 信使 4 件套是「对我方目标施放终结技」，对敌人开大不会触发。
        if "对我方目标" in text or "对队友" in text:
            return "allyUlt"
        return "perUlt"       # 每次开大触发：风套这类，要乘以开大次数
    if "进入战斗" in text or "战斗开始时" in text:
        return "onEnter"      # 进战一次性：翁瓦克这类
    if any(marker in text for marker in ("若", "大于", "每回合", "持续", "层", "消灭")):
        return "conditional"  # 有条件，交给用户判断
    return "passive"          # 无条件常驻


# --------------------------------------------------------------------------- #
# 行动模拟内核（速度随时间生效）
# --------------------------------------------------------------------------- #
#
# 为什么需要它：静态公式「最终速度 = 基础 × (1+pct) + flat」默认所有加速从第 1 次
# 行动就生效。但游戏里有两类加速不是这样的：
#   * 开大触发的加速（信使 4 件套、棺的回响）——第一次开大之前根本没有；
#   * 叠层类的加速（只需等待「每次施放攻击后速度提高 4.8%，最多叠 3 层」）——
#     第 1 次行动 0 层、第 2 次行动 1 层……逐层往上叠。
# 这两类必须**真的把角色的行动一次一次走出来**，才能知道第 k 次行动时有多少加速，
# 进而知道在窗口行动值内到底能打几次。
#
# 模拟口径（和用户确认过的语义）：
#   * 从行动值 AV=0 起，第 k 次行动发生在累计 AV 处；
#   * 第 k 次行动用**当时生效**的加速算速度 speed_k = (基础速度 + 行迹) × (1 + pct_k/100) + flat_k；
#   * 然后 AV += distance / speed_k（distance = 10000），直到超过窗口 AV；
#   * 持续 N 回合 = 接下来自己的 N 次行动内有效；叠层 = 每行动一次 +1 层，上限 maxStacks。
#
# 兼容性红线：没有任何这类「随行动变化」的加速时，走闭式公式的快速路径，
# 结果与旧算法**逐位一致**（见 _simulate / _required_speed 的 fallback）。

SIM_TIMELINE_LIMIT = 12  # timeline 最多给界面 12 条
SIM_MAX_STEPS = 100000  # 模拟的硬上限（只防死循环，正常窗口远到不了）
SIM_MAX_ACTIONS = 200
MAX_WINDOW_AV = 100000.0  # 行动值节点上限
NUM_LIMIT = 1e9  # 数字参数绝对值上限  # 有随行动变化的加速时，二分求需求速度的目标动数上限


def modifier_of(*, label: str, kind: str, value: float, trigger: str,
                apply: str = "self", duration_turns: int = 0, max_stacks: int = 0) -> dict[str, Any]:
    """把一条速度效果整理成模拟内核认识的形式。

    semantics：
      stack    — 叠层：第 k 次行动前有 min(k-1, maxStacks) 层（一层都没叠时不生效）
      perUlt   — 开大触发：第 firstUltAction 次行动之后开始生效，持续 durationTurns 次
      timed    — 勾选后从第 1 次行动起生效，持续 durationTurns 次自己的行动
      constant — 从第 1 次行动起一直生效（无条件常驻 / 进战触发 / 没有回合数的条件效果）

    说明：进战触发（onEnter）即使文案写了持续 N 回合，也从第 1 次行动起一直算到窗口结束。
    其它带「持续 N 回合」的效果按 N 次自己的行动衰减，不再并进整场速度。
    """
    stacks = max(0, int(max_stacks or 0))
    duration = max(0, int(duration_turns or 0))
    if stacks > 0:
        semantics = "stack"
    elif trigger in ("perUlt", "allyUlt"):
        semantics = "perUlt"
    elif duration > 0 and trigger != "onEnter":
        semantics = "timed"
    else:
        semantics = "constant"
    return {
        "label": label,
        "kind": kind,
        "value": float(value or 0),
        "trigger": trigger,
        "apply": apply or "self",
        "durationTurns": duration,
        "maxStacks": stacks,
        "semantics": semantics,
    }


def _active_modifiers(modifiers: list[dict], step: int, first_ult_action: int) -> list[dict]:
    """第 step 次行动时还在生效的加速（step 从 1 开始）。

    叠层的条目返回的是**按层数放大后**的副本（第 k 次行动前 min(k-1, N) 层），
    所以调用方直接累加 value 就是当前这一动的加成。
    """
    out: list[dict] = []
    for item in modifiers:
        semantics = item.get("semantics") or "constant"
        if semantics == "constant":
            out.append(item)
            continue
        if semantics == "stack":
            stacks = min(max(step - 1, 0), item.get("maxStacks") or 0)
            if stacks <= 0:
                continue
            out.append({**item, "value": float(item.get("value") or 0) * stacks, "stacks": stacks})
            continue
        if semantics == "timed":
            duration = item.get("durationTurns") or 0
            if duration <= 0 or step > duration:
                continue
            out.append(item)
            continue
        if semantics == "perUlt":
            # firstUltAction = 第一次开大发生在自己第几次行动**之后**
            begin = (first_ult_action or 0) + 1
            if step < begin:
                continue
            duration = item.get("durationTurns") or 0
            if duration > 0 and step >= begin + duration:
                continue
        out.append(item)
    return out


def _active_label(item: dict, step: int) -> str:
    """生效增益的简写标签（界面 timeline 里显示这个）。

    常驻条目只报「常驻」，否则 12 条 timeline 里会全是同一串名字，看不出变化。
    """
    semantics = item.get("semantics") or "constant"
    if semantics == "stack":
        stacks = min(max(step - 1, 0), item.get("maxStacks") or 0)
        return f"层数 {stacks}/{item.get('maxStacks')}"
    if semantics == "constant":
        return f"常驻 {item.get('label') or ''}".strip()
    return item.get("label") or ""


def _any_timeline(modifiers: list[dict]) -> bool:
    """有没有「随行动变化」的加速（开大触发 / 叠层）。

    没有的话整条链走闭式公式，结果与旧算法逐位一致（兼容性红线）。
    """
    return any((item.get("semantics") or "constant") != "constant" for item in modifiers)


def _step_speed(base: float, active: list[dict], *, percent_base: float | None = None) -> float:
    """当前这一步的速度。

    百分比只作用在**基础速度**上、固定值加在最后 —— 和游戏公式
    「最终速度 = 基础速度 × (1 + 百分比之和) + 固定速度之和」一致。
    不能写成「当前速度 × (1+pct)」（那是复利，会算高）。

    ``percent_base`` 只在反推 S0 时使用：这时 ``base`` 已经是
    S0 = 基础 × (1 + 常驻百分比) + 常驻固定值，额外百分比必须乘真正的基础速度，
    不能再乘一遍 S0。
    """
    pct = 0.0
    flat = 0.0
    for item in active:
        if item.get("kind") == "pct":
            pct += float(item.get("value") or 0)
        else:
            flat += float(item.get("value") or 0)
    if percent_base is None:
        return base * (1 + pct / 100.0) + flat
    return base + float(percent_base) * (pct / 100.0) + flat


def _simulate(base_speed: float, modifiers: list[dict], *, speed0: float | None = None,
              window_av: float, first_ult_action: int = 1, distance: float = 10000.0,
              advance_distance: float = 0.0, timeline_limit: int = SIM_TIMELINE_LIMIT,
              action_cap: int | None = None) -> dict[str, Any]:
    """从 AV=0 开始一次次行动，直到窗口结束。

    两种给法：
      * modifiers 里同时含常驻与随行动变化的效果（界面路径）：
        每一步速度 = 基础速度 × (1 + 当时生效的 pct 之和/100) + 当时生效的 flat 之和；
      * speed0 给了标量「未加速速度 S0」（推荐 / 建议里反推需求速度用）：
        因为 S0 = 基础 × (1 + 常驻pct) + 常驻flat，把百分比作用在 S0 上
        （S0 × (1+pct)）与作用在基础速度上等价。
        这时 modifiers 只需要装随行动变化的那批。

    timeline 里的 av 是这次行动**开始**的累计行动值（第 1 次行动是 0）。

    返回两个计数，口径一致（都是「这一次行动**打完**时窗口还没结束」）：
      achieved  — 用当前这一步的速度推出来的阈值判定，写成
                  (k×distance − 拉条) ≤ 速度 × 窗口AV，与旧公式
                  floor((速度×窗口AV + 拉条) / 距离) 完全同一个阈值
                  （兼容性红线要求它和旧算法**逐位相同**）。
      completed — 用**模拟出来的真实行动值**判定。没有开大/叠层加速时两者必然相等
                  （速度恒定 → 两者是同一个不等式），有加速时才知道真正打完几次。
    """
    base = float(speed0) if speed0 is not None else base_speed
    distance_left = 0.0
    # 拉条按「总路程减少 advance_distance」处理（与闭式公式同一口径），
    # 从最早的行动开始抵扣：第 k 次行动打完的真实行动值 = (k×距离 − 已用拉条) 按各步速度走完。
    advance_left = max(0.0, float(advance_distance or 0.0))
    av = 0.0
    achieved = 0
    completed = 0
    timeline: list[dict[str, Any]] = []
    # 不再用时间线条数当上限（旧版 12 条封顶会把 50000 AV 的 625 动数成 12）；
    # 循环靠「行动开始时间出窗口」自然结束，这里只是防死循环的硬上限。
    max_steps = int(action_cap) if action_cap else SIM_MAX_STEPS
    while achieved < max_steps:
        step = achieved + 1
        active = _active_modifiers(modifiers, step, first_ult_action)
        if speed0 is None:
            speed = _step_speed(base_speed, active)
        else:
            speed = _step_speed(base, active, percent_base=base_speed)
        if speed <= 0:
            break  # 速度非正 → 永远动不了
        use = min(distance, advance_left)
        next_av = av + (distance - use) / speed
        if av > window_av + 1e-9 * max(1.0, abs(av)):
            break  # 这次行动的开始时间已经出了窗口：后面的更晚，不用再走了
        # 与旧公式同一个阈值：这一次行动打完还在窗口内
        if distance_left + distance - advance_distance <= window_av * speed + 1e-9 * max(
            1.0, abs(window_av * speed)
        ):
            achieved += 1
        else:
            # 这一步按「当前速度恒定」推已经超了窗口，但**模拟出来的真实行动值**未必：
            # 开大/叠层之后速度会涨，后面的行动可能反而打得完。所以这里不能 break，
            # 继续走完整条时间线，由 completed 给出真实次数。
            achieved = max(achieved, completed + 1)
        if next_av <= window_av + 1e-9 * max(1.0, abs(next_av)):
            completed += 1
        if len(timeline) < timeline_limit:
            pct = sum(float(i.get("value") or 0) for i in active if i.get("kind") == "pct")
            flat = sum(float(i.get("value") or 0) for i in active if i.get("kind") != "pct")
            labels = [_active_label(i, step) for i in active]
            timeline.append(
                {
                    "action": step,
                    "speed": speed,
                    "av": av,
                    "pct": pct,
                    "flat": flat,
                    "active": labels or ["（无增益）"],
                }
            )
        # 注意：这两行必须在 while 里、不能缩进到上面的 if 里面 ——
        # timeline 只记前 12 条，但行动次数要继续数下去。
        distance_left += distance
        advance_left -= use
        av = next_av
        if not math.isfinite(av):
            break
    return {"av": av, "achieved": achieved, "completed": completed, "timeline": timeline}


def _required_speed(base_speed: float, modifiers: list[dict], *, actions: int, av_limit: float,
                    advance_distance: float, distance: float, first_ult_action: int,
                    low: float = 0.0, high: float | None = None) -> float:
    """二分「未加速速度 S0」，使得窗口内正好能打出 actions 次行动。

    没有随行动变化的加速时，闭式解 (actions×distance − 拉条) / 窗口 AV 与模拟等价，
    这里直接返回闭式解，保证与旧算法逐位一致。
    """
    if not actions or av_limit <= 0:
        return 0.0
    if not any((item.get("semantics") or "constant") != "constant" for item in modifiers):
        return max(0.0, (actions * distance - advance_distance) / av_limit)
    if high is None:
        high = max(1000.0, base_speed * 50.0)
    cap = int(actions) + 1

    def done(s0: float) -> bool:
        return _simulate(base_speed, modifiers, speed0=s0, window_av=av_limit,
                         first_ult_action=first_ult_action, distance=distance,
                         advance_distance=advance_distance,
                         timeline_limit=0, action_cap=cap)["completed"] >= int(actions)

    # 上界不够就翻倍（旧版直接把上界当答案返回 → 不可能的目标显示 1000）
    for _ in range(80):
        if done(high):
            break
        low, high = high, high * 2.0
    else:
        return math.inf
    for _ in range(200):
        mid = (low + high) / 2.0
        result = _simulate(base_speed, modifiers, speed0=mid, window_av=av_limit,
                           first_ult_action=first_ult_action, distance=distance,
                           advance_distance=advance_distance,
                           timeline_limit=0, action_cap=cap)
        if result["completed"] >= int(actions):
            high = mid
        else:
            low = mid
        # 收敛到相邻浮点数就停：再二分下去也没有更细的解了
        if math.nextafter(low, high) >= high:
            break
    return high


def _simulation_notes(modifiers: list[dict], first_ult_action: int) -> list[str]:
    """把「哪条加速从第几次行动起生效」写成一句人话，界面直接用。"""
    notes: list[str] = []
    for item in modifiers:
        semantics = item.get("semantics") or "constant"
        label = item.get("label") or "速度效果"
        if semantics == "perUlt":
            begin = (first_ult_action or 0) + 1
            duration = item.get("durationTurns") or 0
            tail = (
                f"，持续 {duration} 次行动（第 {begin + duration} 次行动起失效）"
                if duration > 0
                else "，一直有效到窗口结束"
            )
            notes.append(f"第 {first_ult_action or 0} 次行动后开大，「{label}」从第 {begin} 次行动起生效{tail}")
        elif semantics == "stack":
            notes.append(
                f"「{label}」每次行动叠 1 层，最多 {item.get('maxStacks')} 层"
                f"（第 k 次行动前有 min(k−1, {item.get('maxStacks')}) 层）"
            )
        elif semantics == "timed":
            duration = item.get("durationTurns") or 0
            notes.append(
                f"「{label}」从第 1 次行动起生效，持续 {duration} 次行动"
                f"（第 {duration + 1} 次行动起失效）"
            )
    return notes


def relic_effect_options(ctx) -> tuple[list[dict], list[dict]]:
    """把遗器套装拆成「可作 4 件套的」和「可作位面饰品的」两组。

    两组都是**全量**：没有速度效果的套装照样能选（比如为了它的攻击/伤害效果），
    只是计算时不会产生任何速度贡献。分类依据是套装文案条数
    （遗器 = 2 件套 + 4 件套两条；位面饰品只有 2 件套一条）。
    """
    four_piece: list[dict[str, Any]] = []
    ornaments: list[dict[str, Any]] = []

    for relic in _relics(ctx):
        effects: list[dict[str, Any]] = []
        for effect in relic.get("effects") or []:
            kind = effect.get("kind")
            if kind not in ("pct", "flat", "advance"):
                continue
            source = effect.get("source") or ""
            slot = "4件套" if "4件套" in source else ("2件套" if "2件套" in source else source)
            text = effect.get("text") or ""
            effects.append(
                {
                    "slot": slot,
                    "kind": kind,
                    "value": effect.get("value"),
                    "apply": effect.get("apply"),
                    "text": text,
                    "trigger": trigger_of(text),
                }
            )
        desc = [str(line) for line in (relic.get("desc") or [])]
        entry = {
            "id": relic.get("id"),
            "name": relic.get("name"),
            "contentId": relic.get("contentId"),
            "icon": relic.get("icon") or relic.get("iconSmall"),  # 本地 webp 优先，远程兜底
            "releaseOrder": relic.get("releaseOrder"),
            "effects": effects,
            "hasSpeedEffect": bool(effects),
            "summary": " ／ ".join(desc)[:100],
        }
        if len(desc) >= 2:
            four_piece.append(entry)
        else:
            ornaments.append(entry)

    # 遗器池按推出顺序排（新的在前），和角色列表一致
    four_piece.sort(key=lambda item: (item.get("releaseOrder") is None, item.get("releaseOrder") or 0))
    ornaments.sort(key=lambda item: (item.get("releaseOrder") is None, item.get("releaseOrder") or 0))
    return four_piece, ornaments


# --------------------------------------------------------------------------- #
# 效果与勾选
# --------------------------------------------------------------------------- #

CONDITION_MARKERS = ("若", "当", "大于", "小于", "每", "层", "触发", "持续", "叠影", "受到", "消灭")


def _effect_id(scope: str, index: int) -> str:
    return f"{scope}#{index}"


def _collect_effects(ctx, character: dict, cone: dict | None, superimpose: int,
                     eidolon: int) -> tuple[list[dict], list[dict]]:
    """返回 (速度类效果, 拉条类效果)，都带稳定 id 与默认勾选状态。"""
    speed: list[dict] = []
    advance: list[dict] = []

    def push(scope: str, index: int, raw: dict, origin: str) -> None:
        kind = raw.get("kind")
        text = raw.get("text") or ""
        # 触发方式要摆到界面上：有些加速不是开局就生效的（开大后 / 进战 / 有条件），
        # 用户得知道自己在勾什么。判定逻辑和遗器套装共用 trigger_of()。
        trigger = trigger_of(text)
        entry = {
            "id": _effect_id(scope, index),
            "origin": origin,
            "name": raw.get("name") or "",
            "kind": kind,
            "value": raw.get("value"),
            "apply": raw.get("apply") or "self",
            "text": text,
            "rank": raw.get("rank"),
            "superimpose": raw.get("superimpose"),
            "trigger": trigger,
            # 持续回合 / 叠层上限：模拟内核要靠它们决定加速什么时候生效、什么时候到期
            "durationTurns": int(raw.get("durationTurns") or 0),
            "maxStacks": int(raw.get("maxStacks") or 0),
            # 自动判断「看起来是否无条件（开局就生效）」。有条件的一律默认不勾，避免高估速度。
            "defaultEnabled": (
                kind in ("pct", "flat")
                and raw.get("apply") == "self"
                and trigger == "passive"
                and not any(marker in text for marker in CONDITION_MARKERS)
            )
            # 星魂是你**主动选**的（我把星魂调到 2 魂，就是要它的效果），
            # 所以星魂来源的速度效果默认勾上——否则界面上选了星魂却看不到任何变化。
            or (kind in ("pct", "flat") and (raw.get("source") or "") == "星魂"),
        }
        if kind in ("pct", "flat"):
            speed.append(entry)
        elif kind == "advance":
            advance.append(entry)

    scope_index = 0
    for raw in character.get("effects") or []:
        push(f"char{scope_index}", scope_index, raw, f"角色·{raw.get('source') or '技能'}")
        scope_index += 1

    if cone:
        for raw in cone.get("effects") or []:
            if raw.get("superimpose") not in (None, superimpose):
                continue
            push(f"cone{scope_index}", scope_index, raw, "光锥")
            scope_index += 1

    def dedup(items: list[dict]) -> list[dict]:
        seen: set[tuple] = set()
        out: list[dict] = []
        for item in items:
            key = (item["kind"], item["value"], item["apply"], item["text"])
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
        return out

    return dedup(speed), dedup(advance)


def _filter_by_eidolon(character: dict, eidolon: int) -> list[dict]:
    """星魂效果只保留 rank <= 当前星魂档位的。"""
    out: list[dict] = []
    for raw in character.get("effects") or []:
        if raw.get("source") == "星魂":
            rank = raw.get("rank")
            if rank is None or int(rank) > eidolon:
                continue
        out.append(raw)
    return out


# --------------------------------------------------------------------------- #
# 接口
# --------------------------------------------------------------------------- #

@api("catalog")
def catalog(payload: dict[str, Any], ctx) -> dict[str, Any]:
    """角色列表、模式、遗器速度套装、数据来源。"""
    characters = _characters(ctx)
    modes = _modes(ctx)
    sources = ctx.data("sources") or {}

    # 2 件套给速度百分比的遗器，供「套装」下拉用（手动兜底，主路径是下面两组）
    speed_sets: list[dict[str, Any]] = []
    for relic in _relics(ctx):
        for effect in relic.get("effects") or []:
            if effect.get("source") == "遗器·2件套" and effect.get("kind") == "pct":
                speed_sets.append(
                    {
                        "id": relic.get("id"),
                        "name": relic.get("name"),
                        "pct": effect.get("value"),
                        "text": effect.get("text"),
                    }
                )
                break

    four_piece, ornaments = relic_effect_options(ctx)

    return {
        "fourPieceSets": four_piece,
        "ornamentSets": ornaments,
        "characters": [
            {
                "id": char.get("id"),
                "name": char.get("name"),
                "rarity": char.get("rarity"),
                "path": char.get("path"),
                "pathName": char.get("pathName"),
                "elementName": char.get("elementName"),
                "baseSpeed": char.get("baseSpeed"),
                # 行迹里的速度是角色自带的，界面上显示的「初始速度」要带上它
                "traceSpeed": char.get("traceSpeed") or 0,
                "effectiveBaseSpeed": char.get("effectiveBaseSpeed") or char.get("baseSpeed"),
                "effectCount": len(char.get("effects") or []),
                "contentId": char.get("contentId"),
                # 官方图：小图给下拉列表用，立绘给左侧展示用；都是远程地址，
                # 由工具箱的 /api/asset 按需下载并缓存到本地
                "icon": char.get("icon") or char.get("iconSmall"),  # 本地 webp 优先，远程兜底
                "iconLarge": char.get("icon"),
                # 立绘优先用游戏内预览图（没有「首发/复刻」角标），失败时界面回退到米游社那张
                "splash": char.get("splash") or char.get("splashSmall") or char.get("splashFallback"),
                "splashFallback": char.get("splashFallback"),
                "releaseOrder": char.get("releaseOrder"),
            }
            for char in sorted(
                characters,
                key=lambda item: (
                    item.get("releaseOrder") is None,
                    item.get("releaseOrder") or 0,
                ),
            )
        ],
        "paths": sorted({char.get("pathName") for char in characters if char.get("pathName")}),
        "modes": modes["modes"],
        "cycles": modes["cycles"],
        "targets": modes["targets"],
        "speedSets": speed_sets,
        "sources": sources,
    }


@api("lightcones")
def lightcones(payload: dict[str, Any], ctx) -> dict[str, Any]:
    """按命途筛选光锥（角色只能用同命途的光锥）。"""
    cones = _lightcones(ctx)
    path = payload.get("path")
    rarity = int(_num(payload, "rarity", 0))
    out = []
    for cone in cones:
        if path and cone.get("path") != path:
            continue
        if rarity and int(cone.get("rarity") or 0) < rarity:
            continue
        out.append(
            {
                "id": cone.get("id"),
                "name": cone.get("name"),
                "rarity": cone.get("rarity"),
                "path": cone.get("path"),
                "pathName": cone.get("pathName"),
                "effectCount": len(cone.get("effects") or []),
                "icon": cone.get("icon") or cone.get("iconSmall"),  # 本地 webp 优先，远程兜底
                "releaseOrder": cone.get("releaseOrder"),
                "speedRelated": any(
                    (effect.get("kind") in ("pct", "flat", "advance"))
                    for effect in cone.get("effects") or []
                ),
            }
        )
    return {"lightcones": out, "path": path}


@api("plan")
def plan(payload: dict[str, Any], ctx) -> dict[str, Any]:
    """算实际速度 + 各模式各 T 数各动数的需求速度。"""
    characters = _characters(ctx)
    character = _find(characters, payload.get("characterId"))
    if character is None:
        raise ValueError(f"找不到角色 {payload.get('characterId')!r}")

    eidolon = max(0, min(int(_num(payload, "eidolon", 0)), 6))
    superimpose = max(1, min(int(_num(payload, "superimpose", 1)), 5))

    cone: dict[str, Any] | None = None
    cone_id = payload.get("lightconeId")
    if cone_id:
        cone = _find(_lightcones(ctx), cone_id)
        if cone is None:
            raise ValueError(f"找不到光锥 {cone_id!r}")
        if cone.get("path") and character.get("path") and cone["path"] != character["path"]:
            raise ValueError(
                f"{character['name']}（{character.get('pathName')}）不能装备"
                f"{cone['name']}（{cone.get('pathName')}）"
            )

    # 效果清单（星魂按档位过滤后再抽取）
    filtered = dict(character)
    filtered["effects"] = _filter_by_eidolon(character, eidolon)
    speed_effects, advance_effects = _collect_effects(ctx, filtered, cone, superimpose, eidolon)

    # None（没给）= 用默认勾选；[] = 用户把效果全勾掉了，必须照办（旧版把 [] 也当默认）
    raw_enabled = payload.get("enabledEffects")
    if raw_enabled is not None and not isinstance(raw_enabled, list):
        raise ValueError("参数 enabledEffects 需要是列表")
    enabled = {_id_str(x) for x in raw_enabled} if raw_enabled is not None else set()
    if raw_enabled is None:
        enabled = {effect["id"] for effect in speed_effects if effect["defaultEnabled"]}

    game_base = float(character.get("baseSpeed") or 0)
    if game_base <= 0:
        raise ValueError(f"{character.get('name')} 没有基础速度数据，请重新跑导入器")

    # 行迹（属性加成）里的速度是角色自带的常驻加成，直接并进基础速度
    trace_flat = float(character.get("traceSpeed") or 0)
    trace_pct = float(character.get("traceSpeedPct") or 0)
    base_speed = game_base + trace_flat

    breakdown: list[dict[str, Any]] = []
    if trace_flat or trace_pct:
        breakdown.append({"label": "角色基础速度（游戏白值）", "kind": "base", "value": game_base})
        detail = "、".join(
            f"{item.get('name')}+{item.get('value'):g}"
            for item in (character.get("traceSpeedDetails") or [])
        )
        if trace_flat:
            breakdown.append(
                {
                    "label": "行迹速度加成（自带，已并入基础速度）",
                    "kind": "base",
                    "value": trace_flat,
                    "text": detail,
                }
            )

    # ---- 遗器与手填 ----
    relic_in = payload.get("relic") or {}
    advance_in = payload.get("advance") or {}
    # 「轴底开大」：最后一次开大的拉条发生在收尾，帮不到前面几动，勾了就把它扣掉
    exclude_last_ult = bool(advance_in.get("excludeLastUlt"))
    ult_note = "（轴底那次开大不计）" if exclude_last_ult else ""

    def effective_ults(count: float) -> float:
        """按「轴底开大」把每次开大触发的拉条次数减一。"""
        count = max(0.0, count)
        if not exclude_last_ult or count <= 0:
            return count
        return max(0.0, count - 1)

    # 手填部分的累积值（速度鞋 / 2 件套 / 副词条 / 手填）。它们和「一直生效的套装加成」
    # 一起构成未加速速度 S0；遗器套装里的开大/叠层加速由 apply_set 单独收进 relic_modifiers。
    # manual_modifiers 只是这些手填项的「修饰形态」，给模拟时间线算每一步速度用，
    # 不重复累加（数值已经在 pct_total / flat_total 里了）。
    pct_total = trace_pct
    flat_total = 0.0
    manual_modifiers: list[dict[str, Any]] = []

    if trace_pct:
        # 行迹里的速度% 已经并进基础速度的口径里，这里补一条修饰给模拟时间线用
        manual_modifiers.append(
            modifier_of(label="行迹速度%", kind="pct", value=trace_pct, trigger="passive")
        )

    if relic_in.get("speedBoots"):
        flat_total += SPEED_BOOTS_FLAT
        breakdown.append({"label": "遗器主词条·速度鞋", "kind": "flat", "value": SPEED_BOOTS_FLAT})
        manual_modifiers.append(
            modifier_of(label="遗器主词条·速度鞋", kind="flat", value=SPEED_BOOTS_FLAT, trigger="passive")
        )

    set_pct = _num(relic_in, "setSpeedPct", 0)
    if set_pct:
        pct_total += set_pct
        breakdown.append(
            {"label": relic_in.get("setSpeedName") or "遗器 2 件套速度", "kind": "pct", "value": set_pct}
        )
        manual_modifiers.append(
            modifier_of(
                label=relic_in.get("setSpeedName") or "遗器 2 件套速度",
                kind="pct",
                value=set_pct,
                trigger="passive",
            )
        )

    substat = _num(relic_in, "substatSpeed", 0)
    if substat:
        flat_total += substat
        breakdown.append({"label": "遗器副词条速度", "kind": "flat", "value": substat})
        manual_modifiers.append(
            modifier_of(label="遗器副词条速度", kind="flat", value=substat, trigger="passive")
        )

    custom_pct = _num(relic_in, "customPct", 0)
    if custom_pct:
        pct_total += custom_pct
        breakdown.append({"label": "其它速度%", "kind": "pct", "value": custom_pct})
        manual_modifiers.append(
            modifier_of(label="其它速度%", kind="pct", value=custom_pct, trigger="passive")
        )

    custom_flat = _num(relic_in, "customFlat", 0)
    if custom_flat:
        flat_total += custom_flat
        breakdown.append({"label": "其它固定速度", "kind": "flat", "value": custom_flat})
        manual_modifiers.append(
            modifier_of(label="其它固定速度", kind="flat", value=custom_flat, trigger="passive")
        )


    # ---- 遗器套装 / 位面饰品：从套装数据自动带出加速与拉条 ----
    # 规则：
    #   * 拉条 + 每次开大触发（风套）→ 自动 × 开大次数
    #   * 拉条 + 进入战斗触发（翁瓦克）→ 自动一次性
    #   * 速度% / 固定速度 + 无条件 → 自动
    #   * 其它（带条件、按回合、依赖层数）→ 只列出来给你看，不自动计入
    conditional_effects: list[dict[str, Any]] = []
    pending_advance: list[tuple[str, float]] = []
    applied_sets: list[dict[str, Any]] = []
    # 遗器套装里带速度的条目也交给模拟内核（触发方式 + 持续回合 + 层数一起带过去）
    relic_modifiers: list[dict[str, Any]] = []
    ult_targets_ally = bool(relic_in.get("ultTargetsAlly"))

    def apply_set(relic_id: str, label: str, ults: float, slots: tuple[str, ...]) -> None:
        nonlocal pct_total, flat_total, relic_modifiers
        relic = _find(_relics(ctx), relic_id)
        if relic is None:
            raise ValueError(f"找不到遗器套装 {relic_id!r}")
        applied: list[dict[str, Any]] = []
        for effect in relic.get("effects") or []:
            kind = effect.get("kind")
            if kind not in ("pct", "flat", "advance"):
                continue
            source = effect.get("source") or ""
            slot = "4件套" if "4件套" in source else ("2件套" if "2件套" in source else source)
            if slot not in slots:
                continue
            text = effect.get("text") or ""
            trigger = trigger_of(text)
            value = float(effect.get("value") or 0)
            record = {
                "setId": relic.get("id"),
                "setName": relic.get("name"),
                "slot": slot,
                "kind": kind,
                "value": value,
                "trigger": trigger,
                "text": text,
            }
            if trigger == "allyUlt" and not ult_targets_ally:
                conditional_effects.append(
                    {
                        **record,
                        "note": "只在对队友施放终结技时触发。勾选「开大目标是队友」后才计入。",
                    }
                )
                continue
            if trigger == "allyUlt":
                trigger = "perUlt"
                record["trigger"] = "perUlt"
            if kind == "advance":
                if trigger == "perUlt":
                    counted_ults = effective_ults(ults)
                    percent = value * counted_ults
                    if percent > 0:
                        pending_advance.append(
                            (f"{relic['name']}·{slot} × {counted_ults:g} 次开大{ult_note}", percent)
                        )
                        applied.append({**record, "counted": percent})
                elif trigger == "onEnter":
                    pending_advance.append((f"{relic['name']}·{slot}（进战触发）", value))
                    applied.append({**record, "counted": value})
                else:
                    conditional_effects.append(record)
            elif trigger == "passive":
                pct_total += value if kind == "pct" else 0.0
                flat_total += value if kind != "pct" else 0.0
                applied.append({**record, "counted": value})
                breakdown.append(
                    {
                        "label": f"{relic['name']}·{slot}",
                        "kind": kind,
                        "value": value,
                        "text": text,
                    }
                )
                relic_modifiers.append(
                    modifier_of(
                        label=f"{relic['name']}·{slot}",
                        kind=kind,
                        value=value,
                        trigger=trigger,
                        apply="self",
                    )
                )
            elif trigger in ("perUlt", "onEnter") and kind in ("pct", "flat"):
                # 速度也有「需要条件才生效」的：例如 4 件套「施放终结技后速度提高 6%」，
                # 进战触发的一次性加成同理。以前这里只处理拉条，速度会被静默丢掉（踩过）。
                if trigger == "perUlt":
                    counted_ults = effective_ults(ults)
                    if counted_ults <= 0:
                        conditional_effects.append(
                            {**record, "note": "需要开大才触发，当前开大次数为 0"}
                        )
                        continue
                    # 开大触发的速度只按**一次**计入（不是乘开大次数），所以标注里要写清。
                    # 它**不是开局就生效**的：交给模拟内核，按 firstUltAction 决定从第几次行动起。
                    note = f"（开大触发{ult_note}，按一次计入）"
                else:
                    note = "（进战触发，开局即生效）"
                applied.append({**record, "counted": value})
                relic_label = f"{relic['name']}·{slot}{note}"
                breakdown.append(
                    {
                        "label": relic_label,
                        "kind": kind,
                        "value": value,
                        "text": text,
                    }
                )
                speed_mod = modifier_of(
                    label=relic_label,
                    kind=kind,
                    value=value,
                    trigger=trigger,
                    apply="self",
                    duration_turns=effect.get("durationTurns") or 0,
                    max_stacks=effect.get("maxStacks") or 0,
                )
                if speed_mod["semantics"] == "constant":
                    # onEnter（没有持续回合的）：开局就生效，等价于旧算法的「直接加进总和」
                    if kind == "pct":
                        pct_total += value
                    else:
                        flat_total += value
                # 开大触发 / 叠层：不能并进 S0，交给模拟内核按行动次数算；
                # constant 的也收进去，模拟时间线要用它算每一步的速度。
                relic_modifiers.append(speed_mod)
            else:
                # 有条件但还没叠层/定时语义的：只列出来给你判断（勾选后从第 1 次行动起算）
                conditional_effects.append(record)
        if applied:
            applied_sets.append({"label": label, "setId": relic.get("id"), "setName": relic.get("name"), "effects": applied})

    four_piece_id = relic_in.get("fourPieceId")
    if four_piece_id:
        apply_set(
            str(four_piece_id),
            "遗器 4 件套",
            _num(relic_in, "fourPieceUlts", 0),
            ("2件套", "4件套"),
        )
    # 位面饰品只留一个栏位（2 件套效果按一次算）
    for ornament_id in (relic_in.get("ornamentIds") or [])[:1]:
        if ornament_id:
            apply_set(str(ornament_id), "位面饰品", 0, ("2件套",))

    # ---- 勾选的速度类效果（勾上就计入：全队类也一样，勾选本身就是你的判断）----
    # 注意 apply == "ally"（「被指定的我方目标」「得到【赐福】的我方单体」这类）：
    # 提速加在**队友**身上，不是这个角色，所以照旧列在 effects 里让界面标注「仅队友」，
    # 但模拟内核不收 —— 除非先把它标成队友。
    applied: list[dict[str, Any]] = []
    effect_modifiers: list[dict[str, Any]] = []
    TRIGGER_NOTES = {
        "perUlt": "（开大触发）",
        "allyUlt": "（对队友开大触发）",
        "onEnter": "（进战触发）",
        "conditional": "（有条件）",
    }
    for effect in speed_effects:
        if effect["id"] not in enabled:
            continue
        value = float(effect["value"] or 0)
        is_team = effect["apply"] == "team"
        is_ally = effect["apply"] == "ally"
        applied.append({**effect, "counted": True, "countedForSelf": not is_ally})
        label = (
            f"{effect['origin']}·{effect['name'] or ''}".strip("·")
            + TRIGGER_NOTES.get(effect.get("trigger"), "")
            + ("（全队）" if is_team else "")
            + ("（仅队友，不计入本角色）" if is_ally else "")
        )
        breakdown.append(
            {
                "label": label,
                "kind": effect["kind"],
                "value": value,
                "text": effect["text"],
                "team": is_team,
                "ally": is_ally,
            }
        )
        if is_ally:
            continue
        speed_mod = modifier_of(
            label=label,
            kind=effect["kind"],
            value=value,
            trigger=effect.get("trigger") or "passive",
            apply=effect.get("apply") or "self",
            duration_turns=effect.get("durationTurns") or 0,
            max_stacks=effect.get("maxStacks") or 0,
        )
        if speed_mod["semantics"] == "constant":
            # 一直生效的那部分照旧直接并进总和（= 未加速速度 S0 的加成口径）
            if effect["kind"] == "pct":
                pct_total += value
            else:
                flat_total += value
        # 开大触发 / 叠层不进 pct_total，交给模拟内核按行动次数算；
        # constant 的也收进列表，模拟时间线要用它算每一步的速度。
        effect_modifiers.append(speed_mod)

    # 全部速度修饰（遗器套装 + 勾选的角色/光锥效果）。constant 那批同时也已经并进
    # pct_total / flat_total 了，这里收着是为了让**模拟时间线**每一步都能算出正确速度。
    speed_modifiers = [*manual_modifiers, *relic_modifiers, *effect_modifiers]
    # 只有「随行动变化」的才需要走模拟/二分
    timeline_modifiers = [m for m in speed_modifiers if (m.get("semantics") or "constant") != "constant"]

    # 未加速速度 S0：不含「随行动变化」的加速（开大触发 / 叠层），也不含仅队友的。
    # 兼容性红线：没有任何随行动变化的加速时，final_speed 就是老算法的最终速度，逐位一致。
    const_pct = pct_total
    const_flat = flat_total
    final_speed = base_speed * (1 + const_pct / 100.0) + const_flat
    if final_speed < 120:
        # 翁瓦克这类进战拉条此时不生效，不要再标成「套装已生效」。
        kept_sets: list[dict[str, Any]] = []
        for entry in applied_sets:
            kept_effects = []
            for effect in entry["effects"]:
                if effect.get("kind") == "advance" and effect.get("trigger") == "onEnter":
                    conditional_effects.append({**effect, "note": "速度未到 120，未计入"})
                else:
                    kept_effects.append(effect)
            if kept_effects:
                entry["effects"] = kept_effects
                kept_sets.append(entry)
        applied_sets = kept_sets
    # ---- 拉条 ----
    advance_items: list[dict[str, Any]] = []
    opening_items: list[dict[str, Any]] = []
    advance_total = 0.0
    warnings: list[str] = []
    pending_text = " ".join(label for label, _percent in pending_advance)

    def add_advance(label: str, percent: float, *, opening: bool = False) -> None:
        nonlocal advance_total
        if percent <= 0:
            return
        record = {"label": label, "percent": percent}
        # 进战拉条打在同一条行动条上，先收着，最后按 100% 封顶。
        if opening:
            opening_items.append(record)
            return
        advance_total += percent
        advance_items.append(record)

    wind_ults = effective_ults(_num(advance_in, "windUlts", 0))
    # 已经选了风套时，套装数据会自己带出拉条，手填的 windUlts 不再加一遍。
    if wind_ults > 0 and "翔鹰" not in pending_text:
        add_advance(f"风套 4 件套 × {wind_ults:g} 次开大（每次 25%）{ult_note}", 25 * wind_ults)

    dance_ults = effective_ults(_num(advance_in, "danceUlts", 0))
    dance_s = max(1, min(int(_num(advance_in, "danceSuperimpose", 5)), 5))
    dance_per_ult = {1: 16, 2: 18, 3: 20, 4: 22, 5: 24}[dance_s]
    # 已经选了「舞！舞！舞！」并按 coneUlts 计了拉条时，手填的 danceUlts 不再加一遍
    # （和风套 / 翁瓦克的去重同一个道理）。
    cone_ults_counted = effective_ults(_num(advance_in, "coneUlts", 0))
    dance_from_cone = bool(cone and cone.get("name") == "舞！舞！舞！" and cone_ults_counted > 0)
    if dance_ults > 0 and not dance_from_cone:
        add_advance(
            f"舞！舞！舞！叠影{dance_s} × {dance_ults:g} 次开大（每次 {dance_per_ult}%）{ult_note}",
            dance_per_ult * dance_ults,
        )

    if advance_in.get("vonwacq") and "翁瓦克" not in pending_text:
        if final_speed >= 120:
            add_advance("翁瓦克（生命的翁瓦克）进战一次 40%", 40, opening=True)
        else:
            warnings.append(
                f"翁瓦克需要装备者速度 ≥ 120 才会触发进战拉条；当前算出来是 {final_speed:.1f}，未计入。"
            )

    extra_advance = _num(advance_in, "custom", 0)
    if extra_advance:
        add_advance(f"其它拉条 {extra_advance:g}%", extra_advance)

    # 遗器套装 / 位面饰品带出来的拉条（风套的开大拉条、翁瓦克的进战拉条都在这里）
    for label, percent in pending_advance:
        if "进战" in label and final_speed < 120:
            warnings.append(
                f"{label} 需要装备者速度 ≥ 120 才触发；当前算出来是 {final_speed:.1f}，未计入。"
            )
            continue
        add_advance(label, percent, opening="进战" in label)

    # 光锥自带的拉条（舞！舞！舞！这类）：数值由叠影决定，开大次数你填多少就乘多少
    cone_advance: list[dict[str, Any]] = []
    cone_conditional: list[dict[str, Any]] = []
    cone_ults = _num(advance_in, "coneUlts", 0)
    if cone:
        for effect in advance_effects:
            if effect.get("origin") != "光锥":
                continue
            text = effect.get("text") or ""
            trigger = trigger_of(text)
            value = float(effect.get("value") or 0)
            record = {
                "coneName": cone.get("name"),
                "superimpose": superimpose,
                "value": value,
                "trigger": trigger,
                "text": text,
            }
            if trigger == "perUlt":
                counted_ults = effective_ults(cone_ults)
                if counted_ults > 0:
                    add_advance(
                        f"{cone['name']} 叠影{superimpose} × {counted_ults:g} 次开大{ult_note}",
                        value * counted_ults,
                    )
                    record["counted"] = value * counted_ults
                cone_advance.append(record)
            elif trigger == "onEnter":
                add_advance(f"{cone['name']}（进战触发）", value, opening=True)
                cone_advance.append({**record, "counted": value})
            else:
                cone_conditional.append(record)

    # 进战拉条打在开局同一条行动条上，合计超过 100% 的部分不会留给下一次行动。
    opening_sum = sum(float(item["percent"]) for item in opening_items)
    if opening_sum > 100 and opening_items:
        scale = 100.0 / opening_sum
        warnings.append(
            f"进战拉条合计 {opening_sum:g}%，同一次行动超出 100% 的部分不带到下一次，已按 100% 计入。"
        )
        for item in opening_items:
            item["percent"] = float(item["percent"]) * scale
    for item in opening_items:
        advance_total += float(item["percent"])
        advance_items.append(item)

    # ---- 各模式阈值表 ----
    modes = _modes(ctx)
    cycles = modes["cycles"]
    distance = float(cycles.get("distancePerAction") or 10000)
    first_av = float(cycles.get("firstCycleAV") or 150)
    step_av = float(cycles.get("cycleAV") or 100)
    targets = modes["targets"]
    min_actions = int(targets.get("minActions") or 1)
    max_actions = int(targets.get("maxActions") or 8)
    advance_distance = advance_total / 100.0 * distance

    # ---- 行动模拟：真的把角色一次一次行动走出来 ----
    simulation_in = payload.get("simulation") or {}
    # 第一次开大发生在自己第几次行动**之后**（默认 1：第 1 次行动后开大）
    first_ult_action = max(0, int(_num(simulation_in, "firstUltAction", 1)))

    def animate(speed0: float, window_av: float, cap: int, extra_flat: float = 0.0,
                extra_modifiers: tuple = ()) -> dict[str, Any]:
        """按给定的「未加速速度 S0」把行动模拟出来（加速按各自时点叠加）。"""
        return _simulate(
            base_speed,
            [*timeline_modifiers, *extra_modifiers],
            speed0=speed0 + extra_flat,
            window_av=window_av,
            first_ult_action=first_ult_action,
            distance=distance,
            advance_distance=advance_distance,
            action_cap=cap,
        )

    def simulate_current(window_av: float, cap: int | None) -> dict[str, Any]:
        """按**当前配置**把行动模拟出来（界面展示时间线用）。

        这里必须走 speed_modifiers 这条路：游戏里百分比只作用在基础速度上，
        用 S0 再乘一遍百分比会多算（S0 × 1.12 ≠ 基础 × (1+6%+12%)）。
        """
        return _simulate(
            base_speed,
            speed_modifiers,
            window_av=window_av,
            first_ult_action=first_ult_action,
            distance=distance,
            advance_distance=advance_distance,
            action_cap=cap,
        )

    def achieved_with(speed0: float, window_av: float, actions: int) -> int:
        """当前 S0 在该窗口内能打完几次。

        没有随行动变化的加速时，直接照抄旧公式
        floor((速度×窗口AV + 拉条) / 距离 + 1e-9) —— 连那个 1e-9 都照抄，
        逐位一致（兼容性红线）。有加速时才靠模拟数。
        """
        if not _any_timeline(timeline_modifiers):
            return max(0, int(math.floor((speed0 * window_av + advance_distance) / distance + 1e-9)))
        return animate(speed0, window_av, max(1, int(actions) + 1))["completed"]

    def speed_needed(actions: int, window_av: float, add_flat: float = 0.0,
                     add_pct: float = 0.0, add_advance: float = 0.0,
                     extra_modifiers: tuple = ()) -> float:
        """要 actions 次行动落在 window_av 内，需要多少「未加速速度 S0」。

        * 没有随行动变化的加速 → 闭式公式，与旧算法**逐位一致**（兼容性红线）；
        * 有（开大触发 / 叠层）→ 二分搜索 S0，判定用真实模拟。
        """
        advance_distance_new = advance_distance + add_advance / 100.0 * distance
        if not _any_timeline(timeline_modifiers):
            return max(0.0, (actions * distance - advance_distance_new) / window_av)
        mods = [*timeline_modifiers, *extra_modifiers]
        # 直道先估一个量级当上界：再差的配置也不会超过它 4 倍
        estimate = base_speed * (1 + (const_pct + add_pct + 40) / 100.0) + const_flat + add_flat + 60
        high = max(1000.0, estimate * 4.0)
        return _required_speed(
            base_speed,
            mods,
            actions=actions,
            av_limit=window_av,
            advance_distance=advance_distance_new,
            distance=distance,
            first_ult_action=first_ult_action,
            low=0.0,
            high=high,
        )

    def required_speed(actions: int, window_av: float) -> float:
        return speed_needed(actions, window_av)

    def reachable(actions: int, window_av: float) -> bool:
        return achieved_with(final_speed, window_av, actions) >= int(actions)


    tables: list[dict[str, Any]] = []
    for mode in modes["modes"]:
        mode_first = float(mode.get("firstCycleAV") or first_av)
        mode_step = float(mode.get("cycleAV") or step_av)
        max_t = int(mode.get("maxT") or 3)
        t_values = list(range(0, max_t + 1))
        rows = []
        for actions in range(min_actions, max_actions + 1):
            speeds = []
            for t in t_values:
                total_av = mode_first + t * mode_step
                # 表格单元格和 verdict 同一口径：需求速度 = 需要多少「未加速速度」。
                # 有开大/叠层加速时这里是**真的模拟**出来的（逐格二分），
                # 没有时就是闭式公式，和旧算法逐位一致。
                needed = max(0.0, speed_needed(actions, total_av))
                speeds.append(
                    {
                        "t": t,
                        "totalAV": total_av,
                        "speed": needed,
                        "reachable": reachable(actions, total_av),
                    }
                )
            rows.append({"actions": actions, "cells": speeds})
        tables.append(
            {
                "id": mode.get("id"),
                "name": mode.get("name"),
                "shortName": mode.get("shortName"),
                "note": mode.get("note"),
                "stars": mode.get("stars") or [],
                "firstCycleAV": mode_first,
                "cycleAV": mode_step,
                "tValues": t_values,
                "rows": rows,
            }
        )

    # ---- 单点结论：用户指定的目标 ----
    target_in = payload.get("target") or {}
    target_t = max(0, int(_num(target_in, "t", 0)))
    target_actions = max(1, int(_num(target_in, "actions", 2)))
    # 目标属于哪个模式，就用哪个模式的首轮行动值（异相仲裁首轮是 300，不是 150）
    target_mode = _mode_by_id(modes, str(target_in.get("mode") or ""))
    base_first = float((target_mode or {}).get("firstCycleAV") or first_av)
    base_step = float((target_mode or {}).get("cycleAV") or step_av)
    # 也可以直接给一个行动值节点，给了就优先用
    custom_av = _num(target_in, "customAV", 0)
    target_av = custom_av if custom_av > 0 else base_first + target_t * base_step
    _check_target(target_actions, target_av)
    # 需求速度 / 当前速度都用 S0 口径（「还差多少速」才有意义）
    required = max(0.0, speed_needed(target_actions, target_av))
    gap = required - final_speed

    # 模拟明细：时间线 + 说明，界面直接展示。
    # 时间线固定走满 12 步（不跟着 target.actions 缩），否则目标只写 2 动时
    # 根本看不出「第 3 次行动加速就过期了」这种回落。
    sim_run = simulate_current(target_av, None)
    # 当前速度在该行动值下能打几次：
    #   没有随行动变化的加速 → 与旧公式逐位一致的闭式口径；
    #   有 → 用模拟出来的真实时间线数（这时才知道开大/叠层到底帮了多少）。
    achievable_actions = (
        sim_run["completed"]
        if _any_timeline(timeline_modifiers)
        else achieved_with(final_speed, target_av, target_actions)
    )
    simulation = {
        "firstUltAction": first_ult_action,
        "windowAV": target_av,
        # 两个计数口径相同（「这一次行动打完时窗口还没结束」）：
        # achievedActions = verdict.achievableActions（当前配置真正能打完几次）；
        # completedActions = 同一条时间线数出来的次数（没有加速时两者必然相等）。
        "achievedActions": achievable_actions,
        "completedActions": sim_run["completed"],
        "timeline": sim_run["timeline"],
        "notes": _simulation_notes(timeline_modifiers, first_ult_action),
    }

    # ---- 补足建议：差速度的时候，具体有哪些办法、各自能到多少 ----
    def evaluate(*, add_flat: float = 0.0, add_pct: float = 0.0, add_advance: float = 0.0) -> dict:
        speed = base_speed * (1 + (const_pct + add_pct) / 100.0) + const_flat + add_flat
        need = max(0.0, speed_needed(target_actions, target_av, add_flat=add_flat,
                                     add_pct=add_pct, add_advance=add_advance))
        return {
            "speed": speed,
            "required": need,
            "gap": need - speed,
            "ok": need <= speed + 1e-9,
        }

    suggestions: list[dict[str, Any]] = []
    if gap > 1e-9:
        # 只堆副词条/固定速度需要多少
        needed_flat = required - base_speed * (1 + const_pct / 100.0)
        extra_flat = needed_flat - const_flat
        if extra_flat > 0:
            suggestions.append(
                {
                    "label": f"副词条/固定速度再堆 {extra_flat:.1f} 点",
                    **evaluate(add_flat=extra_flat),
                }
            )
        if not relic_in.get("speedBoots"):
            suggestions.append({"label": "换上速度鞋（+25）", **evaluate(add_flat=SPEED_BOOTS_FLAT)})
        if not relic_in.get("fourPieceId"):
            suggestions.append(
                {"label": "遗器 4 件套换风套（按 1 次开大算，拉条 25%）", **evaluate(add_advance=25)}
            )
        if not (relic_in.get("ornamentIds") or [None])[0] and not advance_in.get("vonwacq"):
            suggestions.append(
                {"label": "位面饰品换翁瓦克（进战拉条 40%，需速度 ≥ 120）", **evaluate(add_advance=40)}
            )
        suggestions.append({"label": "遗器 2 件套叠速度 6%", **evaluate(add_pct=6)})
        # 按效果排序：能达成的排前面，其次差距小的
        suggestions.sort(key=lambda item: (not item["ok"], abs(item["gap"])))

    return {
        "character": {
            "id": character.get("id"),
            "name": character.get("name"),
            "path": character.get("path"),
            "pathName": character.get("pathName"),
            "elementName": character.get("elementName"),
            "rarity": character.get("rarity"),
            "baseSpeed": base_speed,
        },
        "lightcone": (
            {
                "id": cone.get("id"),
                "name": cone.get("name"),
                "pathName": cone.get("pathName"),
                "rarity": cone.get("rarity"),
            }
            if cone
            else None
        ),
        "eidolon": eidolon,
        "superimpose": superimpose,
        "speed": {
            "base": base_speed,
            "baseRaw": game_base,
            "traceSpeed": trace_flat,
            "traceSpeedPct": trace_pct,
            # pct / flat / final 都是「未加速速度 S0」口径：不含开大触发与叠层这类
            # 随行动变化的加速（它们体现在 simulation.timeline 里）。
            "pct": const_pct,
            "flat": const_flat,
            "final": final_speed,
            "pctAll": pct_total,
            "flatAll": flat_total,
            "hasTimeline": _any_timeline(timeline_modifiers),
            "formula": (
                (f"({game_base:g} + 行迹 {trace_flat:g})" if trace_flat else f"{game_base:g}")
                + f" × (1 + {const_pct:g}%) + {const_flat:g} = {final_speed:.2f}"
                + ("（未加速速度；加速随行动生效，见 simulation）" if _any_timeline(timeline_modifiers) else "")
            ),
            "breakdown": breakdown,
        },
        "effects": {
            "speed": speed_effects,
            "advance": advance_effects,
            "enabled": sorted(enabled),
            "conditional": conditional_effects,
            "coneAdvance": cone_advance,
            "coneConditional": cone_conditional,
        },
        "relicSets": applied_sets,
        "advance": {
            "total": advance_total,
            "distance": advance_distance,
            "items": advance_items,
            "excludeLastUlt": exclude_last_ult,
        },
        "simulation": simulation,
        "tables": tables,
        "suggestions": suggestions,
        "verdict": {
            "t": target_t,
            "actions": target_actions,
            "totalAV": target_av,
            "customAV": custom_av,
            "mode": (
                {
                    "id": target_mode.get("id"),
                    "name": target_mode.get("name"),
                    "firstCycleAV": base_first,
                    "cycleAV": base_step,
                }
                if target_mode
                else None
            ),
            "requiredSpeed": required,
            "currentSpeed": final_speed,
            "gap": gap,
            "achievableActions": achievable_actions,
            "text": (
                f"{(target_mode or {}).get('name', '')} "
                + (
                    f"{custom_av:g} AV 节点"
                    if custom_av > 0
                    else f"{target_t}T（{target_av:g} AV）"
                )
                + f" 内打 {target_actions} 动需要 {required:.2f} 速，"
                + (
                    f"你现在 {final_speed:.2f} 速，够。"
                    if gap <= 1e-9
                    else f"你现在 {final_speed:.2f} 速，还差 {gap:.2f} 速。"
                )
            ),
        },
        "warnings": warnings,
    }


# --------------------------------------------------------------------------- #
# 我的配装（存在 userdata/，升级代码不会丢）
# --------------------------------------------------------------------------- #

PRESET_KEY = "speed-plan-presets"


def _preset_store(ctx) -> dict[str, Any]:
    data = ctx.user_data(PRESET_KEY)
    return data if isinstance(data, dict) else {}


@api("presets")
def presets(payload: dict[str, Any], ctx) -> dict[str, Any]:
    """列出已存的配装（按角色 id 索引）。"""
    store = _preset_store(ctx)
    return {"presets": store, "count": len(store)}


@api("save_preset")
def save_preset(payload: dict[str, Any], ctx) -> dict[str, Any]:
    """把当前这套配置存到这个角色名下。"""
    character_id = str(payload.get("characterId") or "").strip()
    if not character_id:
        raise ValueError("缺少 characterId")
    config = payload.get("config")
    if not isinstance(config, dict):
        raise ValueError("缺少 config（要存的配置对象）")

    characters = _characters(ctx)
    character = _find(characters, character_id)
    with ctx.lock:  # 读 → 改 → 写 整体串行，并发保存不会互相覆盖
        store = _preset_store(ctx)
        store[character_id] = {
            "name": str(payload.get("name") or (character or {}).get("name") or character_id),
            "savedAt": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "config": config,
        }
        path = ctx.save_user_data(PRESET_KEY, store)
    return {"saved": character_id, "count": len(store), "path": path}


@api("delete_preset")
def delete_preset(payload: dict[str, Any], ctx) -> dict[str, Any]:
    character_id = str(payload.get("characterId") or "").strip()
    with ctx.lock:
        store = _preset_store(ctx)
        store.pop(character_id, None)
        ctx.save_user_data(PRESET_KEY, store)
    return {"deleted": character_id, "count": len(store)}


# --------------------------------------------------------------------------- #
# 自动推荐配装
# --------------------------------------------------------------------------- #

def _cone_contribution(cone: dict[str, Any] | None, superimpose: int, ults: float) -> tuple[float, float, float]:
    """光锥能提供的 (速度%, 固定速度, 拉条%)。只取无条件和开大触发的。"""
    if not cone:
        return 0.0, 0.0, 0.0
    pct = flat = advance = 0.0
    for effect in cone.get("effects") or []:
        if effect.get("superimpose") not in (None, superimpose):
            continue
        text = effect.get("text") or ""
        trigger = trigger_of(text)
        kind = effect.get("kind")
        value = float(effect.get("value") or 0)
        if kind == "advance":
            if trigger == "perUlt":
                advance += value * ults
            elif trigger == "onEnter":
                advance += value
        elif trigger == "passive":
            if kind == "pct":
                pct += value
            elif kind == "flat":
                flat += value
    return pct, flat, advance


def _set_contribution(
    relic: dict[str, Any] | None, slots: tuple[str, ...], ults: float
) -> tuple[float, float, float, bool]:
    """遗器套装的 (速度%, 固定速度, 拉条%, 是否要求速度≥120)。"""
    if not relic:
        return 0.0, 0.0, 0.0, False
    pct = flat = advance = 0.0
    needs_120 = False
    for effect in relic.get("effects") or []:
        if effect.get("slot") not in slots:
            continue
        text = effect.get("text") or ""
        trigger = effect.get("trigger") or trigger_of(text)
        kind = effect.get("kind")
        value = float(effect.get("value") or 0)
        if kind == "advance":
            if trigger == "perUlt":
                advance += value * ults
            elif trigger == "onEnter":
                advance += value
                if "120" in text:
                    needs_120 = True
        elif trigger == "passive":
            if kind == "pct":
                pct += value
            elif kind == "flat":
                flat += value
    return pct, flat, advance, needs_120


@api("recommend")
def recommend(payload: dict[str, Any], ctx) -> dict[str, Any]:
    """穷举这个角色能用的光锥与遗器组合，给出「达成目标最省」的几套。

    说明：这是**自动推荐**——在你的可选范围内算出来的最优解，不是社区主流配装表
    （那个数据源米游社详情接口拿不到，见 README）。
    """
    character = _find(_characters(ctx), payload.get("characterId"))
    if character is None:
        raise ValueError(f"找不到角色 {payload.get('characterId')!r}")
    base_speed = float(character.get("baseSpeed") or 0) + float(character.get("traceSpeed") or 0)
    if base_speed <= 0:
        raise ValueError(f"{character.get('name')} 没有基础速度数据")

    modes = _modes(ctx)
    cycles = modes["cycles"]
    distance = float(cycles.get("distancePerAction") or 10000)
    first_av = float(cycles.get("firstCycleAV") or 150)
    step_av = float(cycles.get("cycleAV") or 100)

    target_in = payload.get("target") or {}
    target_t = max(0, int(_num(target_in, "t", 0)))
    actions = max(1, int(_num(target_in, "actions", 2)))
    custom_av = _num(target_in, "customAV", 0)
    # 目标模式决定首轮行动值（异相仲裁首轮 300，不是 150）
    target_mode = _mode_by_id(modes, str(target_in.get("mode") or ""))
    mode_first = float((target_mode or {}).get("firstCycleAV") or first_av)
    mode_step = float((target_mode or {}).get("cycleAV") or step_av)
    target_av = custom_av if custom_av > 0 else mode_first + target_t * mode_step
    _check_target(actions, target_av)

    relic_in = payload.get("relic") or {}
    use_boots = bool(relic_in.get("speedBoots", True))
    superimpose = max(1, min(int(_num(payload, "superimpose", 5)), 5))
    cone_ults = max(0.0, _num(payload, "coneUlts", 1))
    four_ults = max(0.0, _num(payload, "fourPieceUlts", 1))
    limit = max(1, min(int(_num(payload, "maxResults", 10)), 30))
    exclude_last_ult = bool(payload.get("excludeLastUlt"))
    if exclude_last_ult:
        cone_ults = max(0.0, cone_ults - 1)
        four_ults = max(0.0, four_ults - 1)

    # 候选：同命途光锥（星级高、速度相关优先）
    cones = [item for item in _lightcones(ctx) if item.get("path") == character.get("path")]
    cones.sort(
        key=lambda item: (
            -(item.get("rarity") or 0),
            -sum(1 for e in item.get("effects") or [] if e.get("kind") in ("pct", "flat", "advance")),
            item.get("name") or "",
        )
    )
    cones = cones[:6]

    # 遗器候选要按「和配速有没有关系」挑，跟界面上的推出顺序解耦，
    # 否则我改一次显示顺序，推荐结果就会跟着变差。
    four_piece, ornaments = relic_effect_options(ctx)
    four_piece = sorted(
        four_piece, key=lambda item: (not item["hasSpeedEffect"], item.get("name") or "")
    )
    ornaments = sorted(
        ornaments, key=lambda item: (not item["hasSpeedEffect"], item.get("name") or "")
    )

    results: list[dict[str, Any]] = []
    for cone in [None, *cones]:
        cone_pct, cone_flat, cone_advance = _cone_contribution(cone, superimpose, cone_ults)
        for four in [None, *four_piece]:
            four_pct, four_flat, four_advance, four_needs_120 = _set_contribution(
                four, ("2件套", "4件套"), four_ults
            )
            # 位面饰品只有一个栏位（和界面一致）
            for ornament in [None, *ornaments]:
                pct = cone_pct + four_pct
                flat = cone_flat + four_flat
                advance = cone_advance + four_advance
                needs_120_advance = 0.0
                pending_120_labels: list[str] = []

                if ornament is not None:
                    o_pct, o_flat, o_advance, o_needs_120 = _set_contribution(
                        ornament, ("2件套",), 0
                    )
                    pct += o_pct
                    flat += o_flat
                    if o_needs_120:
                        needs_120_advance += o_advance
                        pending_120_labels.append(ornament["name"])
                    else:
                        advance += o_advance
                if four_needs_120:
                    pending_120_labels.append(four["name"])

                if use_boots:
                    flat += SPEED_BOOTS_FLAT
                speed_no_substat = base_speed * (1 + pct / 100.0) + flat

                # 速度不到 120 时，翁瓦克这类进战拉条不生效
                effective_advance = advance
                notes: list[str] = []
                if needs_120_advance:
                    if speed_no_substat >= 120:
                        effective_advance += needs_120_advance
                    else:
                        notes.append(
                            f"{'、'.join(pending_120_labels)} 的进战拉条要求速度 ≥ 120，"
                            f"当前 {speed_no_substat:.0f} 速未触发，未计入"
                        )

                required = max(
                    0.0,
                    (actions * distance - effective_advance / 100.0 * distance) / target_av,
                )
                needed = max(0.0, required - speed_no_substat)

                results.append(
                    {
                        "coneId": (cone or {}).get("id"),
                        "coneName": (cone or {}).get("name") or "（不装备光锥）",
                        "fourPieceId": (four or {}).get("id"),
                        "fourPieceName": (four or {}).get("name") or "（不指定）",
                        "ornamentIds": [(ornament or {}).get("id") or ""],
                        "ornamentNames": [(ornament or {}).get("name") or ""],
                        "speed": speed_no_substat,
                        "advance": effective_advance,
                        "required": required,
                        "neededSubstatSpeed": needed,
                        "ok": needed <= 1e-9,
                        "notes": notes,
                    }
                )

    results.sort(
        key=lambda item: (
            item["neededSubstatSpeed"],
            -item["advance"],
            item["coneName"],
        )
    )
    # 去重：结果一样的（速度、拉条、是否达成）只留最省的那一条，
    # 否则前几名会是一堆等效方案，看不出区别。
    deduped: list[dict[str, Any]] = []
    seen: set[tuple] = set()
    for item in results:
        signature = (round(item["speed"], 1), round(item["advance"], 1), item["ok"])
        if signature in seen:
            continue
        seen.add(signature)
        deduped.append(item)
    top = deduped[:limit] if deduped else results[:limit]

    return {
        "character": {"id": character.get("id"), "name": character.get("name"), "baseSpeed": base_speed},
        "target": {"t": target_t, "actions": actions, "totalAV": target_av, "customAV": custom_av},
        "assumptions": {
            "speedBoots": use_boots,
            "superimpose": superimpose,
            "coneUlts": cone_ults,
            "fourPieceUlts": four_ults,
            "excludeLastUlt": exclude_last_ult,
        },
        "evaluated": len(results),
        "results": top,
        "note": "自动推荐：在你的可选范围内穷举得出的最省方案，不是社区主流配装表。",
    }
