"""行动值排轴 —— 崩铁行动轴 + 回能曲线。

机制模型（严格按用户在《行动与回能机制》里给的口径）
----------------------------------------------------
    当前速度 = (基础速度 + 光锥白字) × (1 + 速度百分比之和) + 固定速度之和 + 行迹速度
    单次行动价值 AV = 10000 / 当前速度
    行动提前 k%  = **这一动**的剩余行动距离减少 k% × 10000（按**完整行动距离**算，
                   不是拿剩余 AV 乘；减到 0 为止，多出来的**不进入下一次行动**）
    行动延后 k%  = 这一动的剩余行动距离增加 k% × 10000（可以超过 10000）

行迹速度在百分比**外面**（爻光：101 × 1.06 + 9 = 116.06，不是 110 × 1.06 = 116.6）；
光锥白字（《将光阴织成黄金》这类）进括号，会被百分比放大。
拉条与加速**不是一回事**：拉条改「还差多少距离」，加速改「行动速度」。
本模块把两者分开记账：拉条按「这一动」抵扣距离，多余部分作废；
加速带发生时刻（第几动开始前 / 剩余路程还剩多少），中途变速只重算剩下的行动值，
已跑路程不动。

回能
----
    实际回能 = 基础回能 × (1 + 能量恢复效率)
部分回能（例如受击回能里的固定部分）不吃 ERR，所以本模块把能量分成两类：
    * **吃 ERR**：普攻/战技/终结技/击杀/受击 这类基础回能；
    * **不吃 ERR**：光锥天赋里写死的"固定恢复 N 点"，以及档案里标「固定」的技能回能
      （停云终结技 50 点固定能量、流萤战技 144 点固定回能、阿哈愿力这类）。
界面上两者分开列，公式也分开写。

数据
----
角色资料（能量上限、技能文案、行迹、星魂）来自 `data/profiles.json`，
由 `tools/import_action_profiles.py` 从 StarRailRes 抓取生成。
**每技能的基础回能 StarRailRes 里没有** —— 能从那句技能文案里抽到的按文案（标「文案」），
抽不到的用通用基础表兜底（标「通用」）。两个来源在界面上必须分开显示，
不要把通用值当成这个角色的实测值。

单元与轮次
----------
沿用配速查询的轮次口径：第 1 轮窗口 150 AV，之后每轮 100 AV。
所以 `rounds=4` 等价于窗口 150 + 3×100 = 450 AV。
轮次标签也和配速查询一致：打完时的累计行动值 **≤ 该轮窗口**，仍算在这一轮
（150 落在第 1 轮、250 落在第 2 轮、350 落在第 3 轮、450 落在第 4 轮）。
"""

from __future__ import annotations

from typing import Any

from core.feature_api import api
from core import feature_api

FEATURE_DIR = "action-value/features/timeline"
DISTANCE_PER_ACTION = 10000.0
FIRST_CYCLE_AV = 150.0
CYCLE_AV = 100.0
PROFILE_FILE = "profiles"

# 通用基础回能（社区通行口径，非 StarRailRes 数据）—— 只在角色文案没写明时用
BASE_ENERGY = {"普攻": 20.0, "战技": 30.0, "终结技": 5.0}
DEFAULT_ROTATION = ["战技", "普攻", "普攻", "普攻", "普攻"]
DEFAULT_TARGET = "战技"


# --------------------------------------------------------------------------
# 取值小工具
# --------------------------------------------------------------------------

def _num(payload: dict[str, Any], key: str, default: float = 0.0) -> float:
    raw = payload.get(key)
    if raw is None or raw == "":
        return default
    if isinstance(raw, bool):
        raise ValueError(f"参数 {key} 需要是数字，收到布尔值 {raw!r}")
    try:
        return float(raw)
    except (TypeError, ValueError):
        # 空值走默认值，**非空的非法值要报错** —— 静默兜底会让界面显示一个不是你要的数字
        raise ValueError(f"参数 {key} 需要是数字，收到 {raw!r}") from None


def _int(payload: dict[str, Any], key: str, default: int) -> int:
    return int(round(_num(payload, key, default)))


def _bool(payload: dict[str, Any], key: str, default: bool = False) -> bool:
    raw = payload.get(key)
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in ("1", "true", "yes", "on", "是")


def _first(payload: dict[str, Any], *keys: str) -> Any:
    """取几个别名里第一个给了值的参数（前端新旧两种写法都认）。"""
    for key in keys:
        if key in payload and payload[key] is not None and payload[key] != "":
            return payload[key]
    return None


def _num_list(payload: dict[str, Any], *keys: str) -> list[float]:
    """一串数字参数：可以给一个数（一次加成）或一组数（同一动上的多次加成）。"""
    out: list[float] = []
    for key in keys:
        raw = payload.get(key)
        if raw is None or raw == "":
            continue
        if isinstance(raw, (list, tuple)):
            for i, item in enumerate(raw):
                if item is None or item == "":
                    continue
                if isinstance(item, bool):
                    raise ValueError(f"参数 {key}[{i}] 需要是数字，收到布尔值 {item!r}")
                try:
                    out.append(float(item))
                except (TypeError, ValueError):
                    raise ValueError(f"参数 {key}[{i}] 需要是数字，收到 {item!r}") from None
        else:
            out.append(_num(payload, key))
    return out


def _action_floats(raw: Any, key: str) -> dict[int, float]:
    """「第几动 → 百分比」的映射（键可以是数字或数字字符串）。"""
    out: dict[int, float] = {}
    if raw is None:
        return out
    if not isinstance(raw, dict):
        raise ValueError(f'参数 {key} 需要是对象，例如 {{"2": 50}}')
    for k, v in raw.items():
        try:
            index = int(k)
        except (TypeError, ValueError):
            raise ValueError(f"参数 {key} 的动数 {k!r} 需要是整数") from None
        try:
            out[index] = float(v)
        except (TypeError, ValueError):
            raise ValueError(f"参数 {key}[{k}] 需要是数字，收到 {v!r}") from None
    return out


def _mid_turn_map(raw: Any, key: str) -> dict[int, list[dict[str, Any]]]:
    """「第几动 → 中途变速事件」的映射；每个事件带发生时刻与新速度。

    例如 `{"1": [{"atRemainingDistance": 5000, "speed": 200}]}`：
    第 1 动跑到剩余路程 5000 时速度变 200。
    """
    out: dict[int, list[dict[str, Any]]] = {}
    if raw is None:
        return out
    if not isinstance(raw, dict):
        raise ValueError(
            f'参数 {key} 需要是对象，例如 {{"1": [{{"atRemainingDistance": 5000, "speed": 200}}]}}'
        )
    for k, v in raw.items():
        try:
            index = int(k)
        except (TypeError, ValueError):
            raise ValueError(f"参数 {key} 的动数 {k!r} 需要是整数") from None
        rows = []
        for item in (v if isinstance(v, list) else [v]):
            if not isinstance(item, dict):
                raise ValueError(f"参数 {key}[{k}] 的每一项需要是对象，收到 {item!r}")
            rows.append(item)
        out[index] = rows
    return out


def _profiles(ctx) -> tuple[dict[str, Any], dict[str, Any]]:
    """常规能量角色档案 + 特殊能量隔离名单（data/profiles.json 的 profiles / excludedProfiles）。"""
    data = ctx.data(PROFILE_FILE)
    if not isinstance(data, dict) or not isinstance(data.get("profiles"), dict):
        raise ValueError("角色档案数据缺失或格式不对（data/profiles.json）")
    return data["profiles"], (data.get("excludedProfiles") or {})


def _excluded_message(exc_prof: dict[str, Any]) -> str:
    """特殊能量角色的统一拒绝话术（残梦/飞黄/新蕊/火种/追忆/隐藏分这类）。"""
    return f"{exc_prof.get('name')}：{exc_prof.get('reason')}（这套回能公式不适用）"


def _profile(ctx, char_id: str) -> dict[str, Any]:
    profiles, excluded = _profiles(ctx)
    key = str(char_id)
    if key in excluded:
        # 这些角色不用常规能量点数（不吃 ERR）—— 通用回能公式对他们是错的，直接拒绝
        raise ValueError(_excluded_message(excluded[key]))
    prof = profiles.get(key)
    if prof is None:
        known = "、".join(f"{k}({v.get('name')})" for k, v in sorted(profiles.items()))
        raise ValueError(f"档案里没有角色 {char_id}。现有：{known}")
    return prof


def _energy_is_fixed(info: dict[str, Any]) -> bool:
    """这个技能的回能是固定点数吗？「固定」不吃能量恢复效率（ERR）。"""
    return bool(info.get("fixed")) or info.get("source") == "固定"


def cycle_window(rounds: int) -> float:
    """轮次 → 窗口行动值。第 1 轮 150，之后每轮 100。"""
    rounds = max(1, int(rounds))
    return FIRST_CYCLE_AV + (rounds - 1) * CYCLE_AV


# --------------------------------------------------------------------------
# 速度与行动条
# --------------------------------------------------------------------------

def final_speed(base: float, pct: float = 0.0, flat: float = 0.0,
                lightcone_base: float = 0.0, trace: float = 0.0) -> float:
    """当前速度 = (基础速度 + 光锥白字) × (1 + 百分比之和/100) + 固定速度之和 + 行迹速度。

    `base` 只用档案里的 `baseSpeed`（白值）；行迹速度 `trace` 加在百分比**外面**；
    光锥白字 `lightcone_base`（《将光阴织成黄金》这类）进括号，会被百分比放大。
    """
    if base <= 0:
        raise ValueError(f"基础速度需要大于 0，收到 {base:g}")
    return (base + lightcone_base) * (1.0 + pct / 100.0) + flat + trace


def recalc_remaining_av(rem_dist: float, old_spd: float, new_spd: float) -> float:
    """中途变速重算：已跑路程不动，新剩余行动值 = 剩余路程 / 新速度。

        AV_新 = AV_旧 × 速度_旧 / 速度_新 = 剩余路程 / 速度_新

    `old_spd` 不进公式（两条式子等价），留着是让调用方把「变速前速度」交代清楚，
    也顺手挡掉 0 / 负速度。
    """
    if float(old_spd) <= 0:
        raise ValueError(f"变速前的速度需要大于 0，收到 {old_spd:g}")
    if float(new_spd) <= 0:
        raise ValueError(f"变速后的速度需要大于 0，收到 {new_spd:g}")
    return float(rem_dist) / float(new_spd)


def simulate_actions(*, speed: float, adv_percents: list[float] | None = None,
                     delay_percents: list[float] | None = None,
                     max_actions: int = 40, window_av: float = 0.0,
                     speed_by_action: dict[int, float] | None = None,
                     adv_by_action: dict[int, float] | None = None,
                     mid_turn_changes: dict[int, list[dict]] | None = None,
                     distance: float = DISTANCE_PER_ACTION) -> dict[str, Any]:
    """把行动一次一次走出来。

    拉条（行动提前）**减少**这一动的剩余路程，`adv_percents` 传正数，
    全部记在**第 1 动**上（一次行动上的多次拉条先求和）；`adv_by_action` 再给
    「第几动各拉多少」的逐动明细。延后（推条）**增加**这一动的剩余路程，
    `delay_percents` 传正数（符号由调用方保证，别传负数），同样记在第 1 动上。

        这一动剩余路程 = max(0, 10000 − 这一动拉条距离) + 这一动推条距离
        这一动行动值   = 这一动剩余路程 / 当时的速度

    ⚠️ 拉条**只减当前这一动**的路程、减到 0 为止，多出来的直接作废，
    **不会**滚到下一动：40% + 80% 拉条 = 这一动路程 0，下一动仍是完整 10000。
    推条没有上限，路程可以超过 10000。

    `speed_by_action` 是「第几动用多少速度」的**绝对速度**表（键从 1 开始），
    来自 speed-plan 的 `simulation.timeline` —— 有开大触发/叠层加速时每一动速度不同。
    ⚠️ 那是**绝对速度**不是增量：拿它当增量去叠加会把 147 速算成 302（踩过）。
    表里没有的动沿用时间轴上的「当前速度」。

    `mid_turn_changes` 是「第几动跑到一半变速」的事件表：
    `{1: [{"atRemainingDistance": 5000, "speed": 200}]}` 表示第 1 动剩余路程还剩 5000
    时速度变 200。变速点之前按旧速度、之后按新速度分段算；已跑路程不动，
    只把剩下的重算（见 `recalc_remaining_av`）。变速后的速度会一直沿用到后面的行动，
    直到再有变化。

    返回每次行动的 {index, av, gap, speed, advanceUsed, delayUsed, round}。
    """
    speed = float(speed)
    if speed <= 0:
        raise ValueError(f"最终速度需要大于 0，收到 {speed:g}")

    advance_pct = sum(float(x) for x in (adv_percents or []))
    delay_pct = sum(float(x) for x in (delay_percents or []))

    by_action = {int(k): float(v) for k, v in (speed_by_action or {}).items()
                 if v and float(v) > 0}
    adv_by = {int(k): float(v) for k, v in (adv_by_action or {}).items()}
    mid_by: dict[int, list[dict[str, Any]]] = {}
    for k, v in (mid_turn_changes or {}).items():
        mid_by[int(k)] = [c for c in (v if isinstance(v, list) else [v]) if isinstance(c, dict)]

    rows: list[dict[str, Any]] = []
    av = 0.0
    current_speed = speed  # 时间轴上的「当前速度」；中途变速后一直沿用
    for index in range(1, max(1, int(max_actions)) + 1):
        spd = by_action.get(index, current_speed)
        # 这一动的拉条先求和，再抵扣路程；只减这一动，减到 0 为止，**余量作废**
        adv_pct_here = adv_by.get(index, 0.0) + (advance_pct if index == 1 else 0.0)
        used = min(distance, max(0.0, adv_pct_here / 100.0 * distance))
        pushed = max(0.0, (delay_pct if index == 1 else 0.0) / 100.0 * distance)
        rem = max(0.0, distance - used) + pushed

        # 中途变速按发生时刻分段跑：变速点之前旧速度，之后新速度
        gap = 0.0
        cur = rem
        cur_spd = spd
        for ch in sorted(mid_by.get(index, []),
                         key=lambda c: -float(c.get("atRemainingDistance") or 0.0)):
            at = max(0.0, float(ch.get("atRemainingDistance") or 0.0))
            new_spd = float(ch.get("speed") or 0.0)
            if new_spd <= 0:
                raise ValueError(f"中途变速的速度需要大于 0，收到 {new_spd:g}")
            cut = min(at, cur)
            if cut < cur:
                gap += (cur - cut) / cur_spd
                cur = cut
            cur_spd = new_spd
        if cur > 0:
            # 剩下的路程按变速后的速度重算 —— 已跑路程不动
            gap += recalc_remaining_av(cur, spd, cur_spd)
        current_speed = cur_spd

        av += gap
        if window_av and av > window_av + 1e-9:
            break
        rows.append({
            "index": index,
            "av": av,
            "gap": gap,
            "speed": spd,
            "advanceUsed": used,
            "advancePctUsed": used / distance * 100.0,
            "delayUsed": pushed,
            "round": round_of(av),
        })
    return {
        "speed": speed,
        "distancePerAction": distance,
        "totalAdvancePct": advance_pct,
        "totalAdvanceDistance": advance_pct / 100.0 * distance,
        "totalDelayPct": delay_pct,
        "totalDelayDistance": delay_pct / 100.0 * distance,
        "actions": rows,
        "actionCount": len(rows),
    }


def round_of(av: float) -> int:
    """行动值落在第几轮。

    轮次窗口与配速查询同一口径：第 1 轮 0–150，之后每轮 100；
    **打完时的累计行动值 ≤ 该轮窗口，仍算在这一轮** —— 150 落在第 1 轮、
    250 落在第 2 轮、350 落在第 3 轮、450 落在第 4 轮（边界带 1e-9 容差）。
    """
    if av <= FIRST_CYCLE_AV + 1e-9:
        return 1
    return 2 + int((av - FIRST_CYCLE_AV - 1e-9) // CYCLE_AV)


def open_formula_speed(*, actions: int, window_av: float, advance_pct: float = 0.0,
                       distance: float = DISTANCE_PER_ACTION) -> float:
    """闭式解：窗口内刚好打满 actions 次行动所需的速度。

        需求速度 = (动数 × 距离 − 拉条总量) ÷ 窗口行动值
    """
    if window_av <= 0:
        raise ValueError("窗口行动值需要大于 0")
    adv = float(advance_pct) / 100.0 * distance
    return max(0.0, (int(actions) * distance - adv) / window_av)


# --------------------------------------------------------------------------
# 回能
# --------------------------------------------------------------------------

def resolve_energy_table(profile: dict[str, Any], overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """角色的回能表：文案优先，缺的用通用兜底；overrides 可以逐项覆盖。

    `source` 三档：「文案」（技能文案写了点数）/「固定」（固定能量，**不吃 ERR**）/
    「通用」（文案没写，用通用基础表兜底）。标「固定」或 `fixed: true` 的技能回能
    （停云终结技 50、流萤战技 144、阿哈愿力 +1 这类）一律不乘 (1 + ERR)。
    """
    table: dict[str, Any] = {}
    stored = profile.get("energy") or {}
    for slot in ("普攻", "战技", "终结技"):
        info = stored.get(slot) or {}
        value = info.get("value")
        source = info.get("source") or "通用"
        fixed = _energy_is_fixed(info)
        if value is None:
            value, source, fixed = BASE_ENERGY.get(slot, 0.0), "通用", False
        table[slot] = {"value": float(value), "source": source, "fixed": fixed}
    for slot, spec in (overrides or {}).items():
        if slot in table and spec is not None and spec != "":
            # 手填只改数值；「固定」是技能本身的性质，跟着原档案走
            table[slot] = {"value": float(spec), "source": "手动",
                           "fixed": table[slot].get("fixed", False)}
    return table


def simulate_energy(*, max_sp: float, rotation: list[str], start_energy: float = 0.0,
                    err: float = 0.0, energy_table: dict[str, Any] | None = None,
                    fixed_energy_per_own_action: float = 0.0,
                    hit_energy: float = 0.0, kills_per_action: float = 0.0,
                    kill_energy: float = 0.0, ult_energy: float | None = None,
                    actions: int = 20, actions_per_ult: float = 0.0) -> dict[str, Any]:
    """按行动序列叠能量，产出每一步的能量与「第几动满能」。

    * `rotation`：自己每次行动用「普攻」还是「战技」，循环使用。
    * `actions_per_ult`：多少次自己的行动会夹一次开大（0 = 不模拟开大节奏，
      只在满能时标记"可以开大"）。
    * 吃 ERR 的部分 = 基础回能 × (1 + err/100)；标「固定」的技能回能**不乘 ERR**。
      `fixed_energy_per_own_action` 是不吃 ERR 的固定回能，单独加。
    """
    table = energy_table or {}
    mult = 1.0 + float(err) / 100.0
    ult_info = table.get("终结技") or {}
    ult_fixed = _energy_is_fixed(ult_info)
    if ult_energy is None:
        value = ult_info.get("value")
        ult_energy = float(BASE_ENERGY["终结技"] if value is None else value)

    rows: list[dict[str, Any]] = []
    energy = float(start_energy)
    first_full: int | None = None
    ults_used = 0
    rotation = [r for r in (rotation or DEFAULT_ROTATION) if r in ("普攻", "战技")] or list(DEFAULT_ROTATION)
    n = max(1, int(actions))

    for i in range(1, n + 1):
        acted_with = rotation[(i - 1) % len(rotation)]
        info = table.get(acted_with) or {}
        value = info.get("value")
        base = float(BASE_ENERGY[acted_with] if value is None else value)
        if _energy_is_fixed(info):
            gain = base
            detail = [f"{acted_with} {base:g}（固定回能，不吃 ERR）"]
        else:
            gain = base * mult
            detail = [f"{acted_with} {base:g} × {mult:.3f} = {gain:.2f}"]
        gain += float(fixed_energy_per_own_action)
        if fixed_energy_per_own_action:
            detail.append(f"固定 +{fixed_energy_per_own_action:g}（不吃 ERR）")
        if hit_energy:
            gain += float(hit_energy) * mult
            detail.append(f"受击 {hit_energy:g} × {mult:.3f}")
        if kills_per_action and kill_energy:
            gain += float(kills_per_action) * float(kill_energy) * mult
            detail.append(f"击杀 {kills_per_action:g} × {kill_energy:g} × {mult:.3f}")

        energy = min(float(max_sp), energy + gain)
        note = ""
        if actions_per_ult and i % int(actions_per_ult) == 0 and energy >= float(max_sp):
            ult_back = float(ult_energy) if ult_fixed else float(ult_energy) * mult
            energy = min(float(max_sp), energy - float(max_sp) + ult_back)
            ults_used += 1
            note = (f"开大：清空并回 {ult_energy:g}（固定回能，不吃 ERR）" if ult_fixed
                    else f"开大：清空并回 {ult_energy:g} × {mult:.3f}")
        if first_full is None and energy >= float(max_sp) - 1e-9:
            first_full = i
        rows.append({
            "index": i,
            "actedWith": acted_with,
            "gain": gain,
            "energy": energy,
            "detail": detail,
            "note": note,
            "canUlt": energy >= float(max_sp) - 1e-9,
        })

    return {
        "maxSp": float(max_sp),
        "err": float(err),
        "rotation": rotation,
        "rows": rows,
        "firstFullAction": first_full,
        "ultsUsed": ults_used,
    }


# --------------------------------------------------------------------------
# 爻光专属：欢愉 / 笑点 / 结界
# --------------------------------------------------------------------------

def yaoguang_kit(profile: dict[str, Any], *, skill_level: int = 10, eidolon: int = 0) -> dict[str, Any]:
    """从档案里把爻光的机制数值取出来（按等级与服务等级取值）。"""
    by_type: dict[str, dict[str, Any]] = {}
    for s in profile.get("skills") or []:
        by_type.setdefault(s.get("type") or "", s)

    def params_of(stype: str) -> list:
        s = by_type.get(stype) or {}
        rows = s.get("params") or []
        if not rows:
            return []
        idx = max(1, int(skill_level)) - 1
        return rows[min(idx, len(rows) - 1)]

    def rank_desc(num: int) -> str:
        for r in profile.get("ranks") or []:
            if int(r.get("rank") or 0) == num:
                return r.get("desc") or ""
        return ""

    skill_p = params_of("BPSkill")          # [结界回合, 欢愉度转化比, 笑点数]
    ult_p = params_of("Ultra")              # [笑点, 抗穿, 持续, 计入笑点, 额外回合]
    talent_p = params_of("Talent")          # [大吉大利倍率]

    out = {
        "maxSp": profile.get("maxSp"),
        "skill": {
            "name": (by_type.get("BPSkill") or {}).get("name"),
            "fieldTurns": int(skill_p[0]) if len(skill_p) > 0 else None,
            "elationShare": skill_p[1] if len(skill_p) > 1 else None,
            "spunkPerAction": int(skill_p[2]) if len(skill_p) > 2 else None,
        },
        "ult": {
            "name": (by_type.get("Ultra") or {}).get("name"),
            "spunk": int(ult_p[0]) if len(ult_p) > 0 else None,
            "resPen": ult_p[1] if len(ult_p) > 1 else None,
            "resPenTurns": int(ult_p[2]) if len(ult_p) > 2 else None,
        },
        "talent": {
            "name": (by_type.get("Talent") or {}).get("name"),
            "elationDamage": talent_p[0] if talent_p else None,
        },
        "eidolonNotes": {},
    }
    if eidolon >= 1:
        out["eidolonNotes"]["E1"] = rank_desc(1)
        out["eidolonNotes"]["E1_spunkCap"] = 40
    if eidolon >= 2:
        out["eidolonNotes"]["E2"] = rank_desc(2)
        out["eidolonNotes"]["E2_teamSpeedPct"] = 12.0
        out["eidolonNotes"]["E2_extraElationPct"] = 16.0
    if eidolon >= 4:
        out["eidolonNotes"]["E4"] = rank_desc(4)
    if eidolon >= 6:
        out["eidolonNotes"]["E6"] = rank_desc(6)
    # 额外行迹 = 有名字、有文案的那种（「开屏有礼」这类）；
    # 「速度强化 / 暴击率强化」只是数值升级项，数据层已标为「数值升级」，不算额外行迹
    trace_names = [t.get("name") for t in (profile.get("traces") or [])
                   if t.get("kind") == "额外行迹" and (t.get("name") or "").strip()]
    out["extraTraces"] = trace_names
    return out


# --------------------------------------------------------------------------
# 动作：目录 / 排轴 / 回能
# --------------------------------------------------------------------------

def base_speed_options(profile_obj: dict[str, Any] | None,
                       payload: dict[str, Any]) -> dict[str, Any]:
    """基础速度取哪个口径 —— 默认**裸基础速度（白值）**，行迹速度在百分比外面单独加。

    库里的合成公式：

        当前速度 = (基础速度 + 光锥白字) × (1 + 百分比之和/100) + 固定速度之和 + 行迹速度

    所以爻光是 101 × 1.06 + 9 = 116.06，**不是** 110 × 1.06 = 116.6。
    `useEffectiveBase=true`（要显式传）才走旧口径：行迹并进基础速度一起吃百分比，
    这时 `trace` 记 0，不重复加。

    参数里可以手填 `lightconeBaseSpeed`（光锥白字，默认 0 —— 没手填不悄悄加）
    和 `traceSpeed`（覆盖档案里的行迹速度）。
    """
    speed = (profile_obj or {}).get("speed") or {}
    raw = speed.get("baseSpeed")
    eff = speed.get("effectiveBaseSpeed")
    use_eff = _bool(payload, "useEffectiveBase", False)
    lc_base = _num(payload, "lightconeBaseSpeed", 0.0)
    trace_speed = _num(payload, "traceSpeed", float(speed.get("traceSpeed") or 0.0))
    if use_eff and eff is not None:
        chosen = eff
        trace = 0.0  # 行迹已经在 effectiveBaseSpeed 里，别再加一遍
    else:
        chosen = raw or eff or 0.0
        trace = trace_speed
    return {
        "raw": raw,
        "effective": eff,
        "traceSpeed": trace_speed,
        "trace": trace,
        "lightconeBase": lc_base,
        "used": float(chosen or 0),
        "useEffective": bool(use_eff),
        "source": speed.get("_source") or "",
    }


@api("catalog")
def catalog(payload: dict[str, Any], ctx) -> dict[str, Any]:
    """模块里已有档案的角色列表（含速度三件套、回能机制备注）+ 特殊能量隔离名单。"""
    profiles, excluded = _profiles(ctx)
    items = []
    for cid, p in sorted(profiles.items()):
        spd = p.get("speed") or {}
        items.append({
            "id": cid,
            "name": p.get("name"),
            "path": p.get("path"),
            "pathName": p.get("pathName"),
            "element": p.get("element"),
            "elementName": p.get("elementName"),
            "rarity": p.get("rarity"),
            "maxSp": p.get("maxSp"),
            "energyType": p.get("energyType"),
            "baseSpeed": spd.get("baseSpeed"),
            "traceSpeed": spd.get("traceSpeed") or 0.0,
            "effectiveBaseSpeed": spd.get("effectiveBaseSpeed"),
            "mechanismNote": p.get("mechanismNote"),
            "skillCount": len(p.get("skills") or []),
        })
    return {"characters": items,
            "excludedCharacters": [dict(v) for _, v in sorted(excluded.items())],
            "distancePerAction": DISTANCE_PER_ACTION,
            "firstCycleAV": FIRST_CYCLE_AV,
            "cycleAV": CYCLE_AV}


@api("profile")
def profile(payload: dict[str, Any], ctx) -> dict[str, Any]:
    """一个角色的完整档案 + 机制摘要（爻光这类会把笑点/结界算出来）。

    特殊能量角色（excludedProfiles 里的隔离名单：残梦/飞黄/新蕊/火种/追忆/隐藏分）
    没有常规能量档案 —— 返回 `excluded: true` 和「这套回能公式不适用」，
    不要拿通用回能公式硬套。
    """
    char_id = str(payload.get("characterId") or "1502")
    _, excluded = _profiles(ctx)
    exc_prof = excluded.get(char_id)
    if exc_prof is not None:
        return {
            "character": {"id": exc_prof.get("id"), "name": exc_prof.get("name")},
            "excluded": True,
            "excludedReason": exc_prof.get("reason"),
            "message": "这套回能公式不适用",
            "excludedProfile": exc_prof,
        }
    prof = _profile(ctx, char_id)
    table = resolve_energy_table(prof, payload.get("energyOverrides") or {})
    kit = yaoguang_kit(prof, skill_level=_int(payload, "skillLevel", 10),
                       eidolon=_int(payload, "eidolon", 0))
    return {"profile": prof, "energyTable": table, "kit": kit}


def compute_from_config(config: dict[str, Any], ctx,
                        character_id: str | None = None,
                        timeline_limit: int = 120) -> dict[str, Any]:
    """把「配速查询」里那套配置交给 speed-plan 真算一遍，拿回速度与拉条。

    这是两个模块之间的**唯一**耦合点：排轴不自己重算光锥/星魂/遗器，
    而是调 speed-plan 的 `plan` 动作（同一套口径，不会两处打架）。

    ⚠️ 两个踩过的坑：
      1. 配速查询存的 `config` 里**没有 characterId**（角色 id 是预设的键，在 config 外面），
         必须补进去，否则 speed-plan 报「找不到角色 None」。
      2. `simulation.timeline` 里每条是**这一动的绝对速度**（不是增量）。
         早期版本把它当增量叠加，147 速被算成 302 —— 所以要按 action 取绝对速度用。

    返回 {speed, advance, timeline, speedByAction, source}。
    """
    plan_payload: dict[str, Any] = dict(config)
    if character_id:
        plan_payload["characterId"] = character_id
    if not plan_payload.get("characterId"):
        raise ValueError("套用预设时缺少角色 id：config 里没有 characterId，调用也没传")
    # 只要"多记几条时间线"，绝不能顺手改行动次数上限（那是 action_cap，会截断 completed）
    plan_payload["timelineLimit"] = max(1, int(timeline_limit))
    try:
        res = feature_api.call("honkai-star-rail", "speed-plan", "plan", plan_payload)
    except KeyError as exc:
        raise ValueError(
            "调不到配速查询（speed-plan）—— 排轴要用它算速度。"
            f"原始错误：{exc}"
        ) from None
    speed = res.get("speed") or {}
    advance = res.get("advance") or {}
    sim = res.get("simulation") or {}
    timeline = sim.get("timeline") or []
    # 每一动的**绝对速度**（timeline 里 action 从 1 开始）
    speed_by_action = {
        int(item["action"]): float(item["speed"])
        for item in timeline
        if isinstance(item, dict) and item.get("action") and item.get("speed")
    }
    return {
        "speed": {
            "base": speed.get("base"),
            "baseRaw": speed.get("baseRaw"),
            "final": speed.get("final"),
            "pct": speed.get("pct"),
            "flat": speed.get("flat"),
            "pctAll": speed.get("pctAll"),
            "flatAll": speed.get("flatAll"),
            "hasTimeline": bool(speed.get("hasTimeline")),
            "formula": speed.get("formula"),
            "breakdown": speed.get("breakdown") or [],
        },
        "advance": {
            "total": advance.get("total") or 0.0,
            "distance": advance.get("distance") or 0.0,
            "items": advance.get("items") or [],
        },
        "timeline": timeline,
        "speedByAction": speed_by_action,
        "source": "speed-plan",
    }


@api("preset")
def preset(payload: dict[str, Any], ctx) -> dict[str, Any]:
    """列表 / 读取「配速查询」里保存的配装（给排轴直接套用）。

    不传 characterId 就列全部；传了就返回那一条的**已算好**速度与拉条。
    """
    store = feature_api.call("honkai-star-rail", "speed-plan", "presets", {})
    presets = (store or {}).get("presets") or {}
    char_id = str(payload.get("characterId") or "").strip()
    if not char_id:
        items = []
        for cid, entry in sorted(presets.items()):
            cfg = entry.get("config") or {}
            items.append({
                "characterId": cid,
                "name": entry.get("name") or cid,
                "savedAt": entry.get("savedAt"),
                "lightconeId": cfg.get("lightconeId"),
                "eidolon": cfg.get("eidolon"),
                "superimpose": cfg.get("superimpose"),
                "hasTimeline": None,
            })
        return {"presets": items, "count": len(items)}

    entry = presets.get(char_id)
    if entry is None:
        raise ValueError(f"配速查询里没有 {char_id} 的配装。先到「配速查询」里保存一套。")
    config = entry.get("config") or {}
    computed = compute_from_config(config, ctx, char_id)
    warnings: list[str] = []
    if computed["speed"].get("hasTimeline"):
        warnings.append(
            "这套配置里有**随行动变化的加速**（开大触发 / 叠层），"
            "排轴的「当前速度」取的是未触发时的 S0；要看每一动的实际速度，"
            "timeline 字段里有逐步结果"
        )
    return {
        "characterId": char_id,
        "name": entry.get("name") or char_id,
        "savedAt": entry.get("savedAt"),
        "config": config,
        "computed": computed,
        "warnings": warnings,
    }


@api("plan")
def plan(payload: dict[str, Any], ctx) -> dict[str, Any]:
    """行动轴：给速度和拉条，算出每一动的行动值落在第几轮。

    速度有三种给法（优先级从高到低）：
      1. `presetCharacterId`：直接套用「配速查询」里保存的配装（**推荐**，口径统一）
      2. `characterId` + `speedPct` / `speedFlat`：从档案取基础速度，再手填加成
      3. 只给 `baseSpeed` + 加成
    """
    # ---- 优先：直接套配速查询里保存的配装 ----
    preset_char = str(payload.get("presetCharacterId") or "").strip()
    if preset_char:
        store = feature_api.call("honkai-star-rail", "speed-plan", "presets", {})
        entry = ((store or {}).get("presets") or {}).get(preset_char)
        if entry is None:
            raise ValueError(f"配速查询里没有 {preset_char} 的配装。")
        config = entry.get("config") or {}
        computed = compute_from_config(config, ctx, preset_char)
        sp = computed["speed"]
        adv = computed["advance"]
        rounds = _int(payload, "rounds", 4)
        window = cycle_window(rounds)
        sim = simulate_actions(
            speed=float(sp.get("final") or 0),
            adv_percents=[float(adv.get("total") or 0)],
            max_actions=_int(payload, "maxActions", 30),
            window_av=window,
            # 绝对速度序列（有开大/叠层加速时每一动速度不同）；不是增量，别叠
            speed_by_action=computed.get("speedByAction") or {},
        )
        per_round: dict[int, int] = {}
        for row in sim["actions"]:
            per_round[row["round"]] = per_round.get(row["round"], 0) + 1
        return {
            "character": {"id": preset_char, "name": entry.get("name") or preset_char},
            "appliedPreset": {
                "characterId": preset_char,
                "name": entry.get("name") or preset_char,
                "savedAt": entry.get("savedAt"),
                "config": config,
                "speedBreakdown": sp.get("breakdown") or [],
                "hasTimeline": sp.get("hasTimeline"),
            },
            "advance": {"pct": float(adv.get("total") or 0),
                        "distance": float(adv.get("distance") or 0),
                        "items": adv.get("items") or []},
            "delay": {"pct": 0.0, "distance": 0.0},
            "window": {"rounds": rounds, "av": window,
                       "formula": f"150 + ({rounds} − 1) × 100 = {window:g} AV"},
            "perRound": per_round,
            "baseSpeedUsed": sim["speed"],
            **sim,
            "speed": {"base": sp.get("base"), "pct": sp.get("pct"), "flat": sp.get("flat"),
                      "final": sp.get("final"), "formula": sp.get("formula"),
                      "baseSource": {"source": "配速查询（speed-plan）",
                                     "useEffective": True}},
            "source": "preset",
        }

    char_id = str(payload.get("characterId") or "")
    profile_obj: dict[str, Any] | None = None
    if char_id:
        profile_obj = _profile(ctx, char_id)
    spd = base_speed_options(profile_obj, payload)
    # 档案里的基础速度白值优先（行迹在百分比外面单独加）；档案没有就用参数里手填的
    base = spd["used"] or _num(payload, "baseSpeed", 0)
    if base <= 0:
        base = 101.0  # 崩铁角色基础速度常见值；不填时给个明确默认

    pct = _num(payload, "speedPct", 0.0)
    flat = _num(payload, "speedFlat", 0.0)
    lc_base = float(spd["lightconeBase"] or 0.0)
    trace_used = float(spd["trace"] or 0.0)
    speed = final_speed(base, pct, flat, lightcone_base=lc_base, trace=trace_used)

    # 同一动上的多次拉条/推条先求和；advByAction / midTurnChanges 再给逐动、逐时刻的明细。
    # 拉条只减**这一动**的路程、减到 0 为止，多出来的不滚到下一动。
    adv_percents = _num_list(payload, "advancePct") + _num_list(payload, "adv_percents")
    delay_percents = _num_list(payload, "delayPct") + _num_list(payload, "delay_percents")
    advance = sum(adv_percents)
    delay = sum(delay_percents)
    adv_by_action = _action_floats(_first(payload, "advByAction", "adv_by_action"), "advByAction")
    mid_turn_changes = _mid_turn_map(_first(payload, "midTurnChanges", "mid_turn_changes"),
                                     "midTurnChanges")
    rounds = _int(payload, "rounds", 4)
    window = cycle_window(rounds)
    max_actions = _int(payload, "maxActions", 30)

    # 手填的「随行动变化的加速」：前端给的是**增量**（{fromAction, pct, flat}），
    # 这里换算成 simulate_actions 要的**绝对速度**表（它只认绝对速度）。
    # 增量只加在白字上：
    #   这一动 = (base + 光锥白字) × (1 + 常驻% + 这一动%) + 常驻固定 + 这一动固定 + 行迹
    # 拿已经算完的速度当基数再乘一遍，会把鞋子和行迹也放大（踩过）。
    changes = [c for c in (payload.get("speedChanges") or []) if isinstance(c, dict)]
    speed_by_action: dict[int, float] = {}
    if changes:
        for index in range(1, max_actions + 1):
            d_pct = d_flat = 0.0
            for c in changes:
                if index >= int(c.get("fromAction") or 1):
                    d_pct += float(c.get("pct") or 0.0)
                    d_flat += float(c.get("flat") or 0.0)
            if d_pct or d_flat:
                speed_by_action[index] = final_speed(
                    base, pct + d_pct, flat + d_flat,
                    lightcone_base=lc_base, trace=trace_used)

    # 注意符号：拉条（行动提前）**减少**距离 → 传正数；
    # 延后（推条）**增加**距离 → 这里必须传正数进"增加"通道，写成 -delay 会把推条当拉条用（踩过）。
    sim = simulate_actions(
        speed=speed,
        adv_percents=adv_percents,
        delay_percents=delay_percents,
        max_actions=max_actions,
        window_av=window,
        speed_by_action=speed_by_action,
        adv_by_action=adv_by_action,
        mid_turn_changes=mid_turn_changes,
    )

    per_round: dict[int, int] = {}
    for row in sim["actions"]:
        per_round[row["round"]] = per_round.get(row["round"], 0) + 1

    # 注意：sim 里有个名为 "speed" 的**数值**，会和下面这个速度对象撞名。
    # 先铺 sim、再放 speed 对象，否则界面拿到的是数字、取 .final 就崩（踩过）。
    return {
        "character": ({"id": profile_obj.get("id"), "name": profile_obj.get("name")}
                      if profile_obj else None),
        "advance": {"pct": advance, "distance": advance / 100.0 * DISTANCE_PER_ACTION},
        # 延后距离按机制是**正数**（+2000 = 推条 20%），写成负数会让界面把推条当拉条
        "delay": {"pct": delay, "distance": delay / 100.0 * DISTANCE_PER_ACTION},
        "window": {"rounds": rounds, "av": window,
                   "formula": f"150 + ({rounds} − 1) × 100 = {window:g} AV"},
        "perRound": per_round,
        "baseSpeedUsed": sim["speed"],
        **sim,
        "speed": {"base": base, "lightconeBase": lc_base, "pct": pct, "flat": flat,
                  "trace": trace_used, "final": speed,
                  "formula": (f"({base:g} + {lc_base:g}) × (1 + {pct:g}%) "
                              f"+ {flat:g} + {trace_used:g} = {speed:.4f}"),
                  "baseSource": spd},
    }


@api("energy")
def energy(payload: dict[str, Any], ctx) -> dict[str, Any]:
    """回能曲线：按行动序列叠能量，给出「第几动满能」。"""
    char_id = str(payload.get("characterId") or "1502")
    prof = _profile(ctx, char_id)
    table = resolve_energy_table(prof, payload.get("energyOverrides") or {})
    max_sp = _num(payload, "maxSp", float(prof.get("maxSp") or 0))
    if max_sp <= 0:
        raise ValueError("能量上限需要大于 0（档案里没有 maxSp，请在参数里给 maxSp）")

    rotation = payload.get("rotation") or list(DEFAULT_ROTATION)
    if not isinstance(rotation, list):
        raise ValueError("rotation 需要是数组，例如 [\"战技\",\"普攻\",\"普攻\"]")

    sim = simulate_energy(
        max_sp=max_sp,
        rotation=[str(x) for x in rotation],
        start_energy=_num(payload, "startEnergy", 0.0),
        err=_num(payload, "err", 0.0),
        energy_table=table,
        fixed_energy_per_own_action=_num(payload, "fixedEnergyPerAction", 0.0),
        hit_energy=_num(payload, "hitEnergy", 0.0),
        kills_per_action=_num(payload, "killsPerAction", 0.0),
        kill_energy=_num(payload, "killEnergy", 10.0),
        actions=_int(payload, "actions", 20),
        actions_per_ult=_num(payload, "actionsPerUlt", 0.0),
    )

    # 结界覆盖：从第 1 次行动开始算（施放战技那一次起）
    kit = yaoguang_kit(prof, skill_level=_int(payload, "skillLevel", 10),
                       eidolon=_int(payload, "eidolon", 0))
    field_turns = (kit.get("skill") or {}).get("fieldTurns")
    return {
        "character": {"id": prof.get("id"), "name": prof.get("name")},
        "energyTable": table,
        "kit": kit,
        "maxSp": max_sp,
        "field": {"turns": field_turns,
                  "coversActions": field_turns,
                  "note": ("结界随爻光自己的回合递减，所以 3 回合 = 覆盖爻光 3 次行动"
                           if field_turns else "")},
        **sim,
    }


@api("yaoguang")
def yaoguang(payload: dict[str, Any], ctx) -> dict[str, Any]:
    """爻光机制推演：笑点 / 结界覆盖 / 阿哈额外回合 / 回能节奏。

    只建模**能确定**的部分，其余全部明确列成「假设」返回给界面：
      * 笑点：战技展开结界后，爻光自己每次普攻/战技 +3；开大 +5（1 魂时额外回合的固定计入 20→40）
      * 结界：3 回合，且**随爻光自己的回合递减** —— 所以「覆盖爻光 3 次行动」
      * 阿哈额外回合：每次开大给 1 个，不消耗笑点
      * 终结技的施放时机、阿哈自己的行动轴、笑点是否有上限：**数据里没有，不做假设**
    """
    prof = _profile(ctx, "1502")
    skill_level = _int(payload, "skillLevel", 10)
    eidolon = _int(payload, "eidolon", 0)
    kit = yaoguang_kit(prof, skill_level=skill_level, eidolon=eidolon)
    table = resolve_energy_table(prof, payload.get("energyOverrides") or {})

    actions = max(1, _int(payload, "actions", 12))
    rotation = payload.get("rotation") or list(DEFAULT_ROTATION)
    rotation = [str(x) for x in rotation if str(x) in ("普攻", "战技")] or list(DEFAULT_ROTATION)
    opening_skill = _bool(payload, "openingSkill", True)

    spunk_per = (kit.get("skill") or {}).get("spunkPerAction") or 3
    ult_spunk = (kit.get("ult") or {}).get("spunk") or 5
    field_turns = (kit.get("skill") or {}).get("fieldTurns") or 3
    e1 = eidolon >= 1
    fixed_per_ult = 40 if e1 else 20

    sim = simulate_energy(
        max_sp=float(prof.get("maxSp") or 0),
        rotation=[str(x) for x in rotation],
        start_energy=_num(payload, "startEnergy", 0.0),
        err=_num(payload, "err", 0.0),
        energy_table=table,
        hit_energy=_num(payload, "hitEnergy", 0.0),
        actions=actions,
        actions_per_ult=_num(payload, "actionsPerUlt", 0.0),
    )

    rows: list[dict[str, Any]] = []
    spunk = 0
    ults = 0
    extra_turns = 0
    field_left = 0

    # 先把"第 i 次行动用什么"整条序列摆出来，别在循环里算模运算（容易错位）
    seq: list[str] = []
    if opening_skill:
        seq.append("战技")
    while len(seq) < actions:
        seq.append(rotation[len(seq) % len(rotation)])

    # 能量按**同一条序列**叠（不能借 simulate_energy 的结果：它的轮转索引和起手战技对不上）
    max_sp = float(prof.get("maxSp") or 0)
    mult = 1.0 + _num(payload, "err", 0.0) / 100.0
    hit_e = _num(payload, "hitEnergy", 0.0) * mult
    per_ult = _num(payload, "actionsPerUlt", 0.0)
    ult_info = table.get("终结技") or {}
    ult_fixed = _energy_is_fixed(ult_info)
    ult_value = ult_info.get("value")
    ult_base = float(BASE_ENERGY["终结技"] if ult_value is None else ult_value)
    energy = _num(payload, "startEnergy", 0.0)
    first_full: int | None = None

    for i in range(1, actions + 1):
        acted_with = seq[i - 1]
        notes = []
        # 结界随爻光**自己**的回合开始递减。施放战技那一次先展开、当回合**不再**立刻减：
        # 3 回合结界要覆盖她自己的 3 次正常行动（fieldLeft 3 → 2 → 1 → 0）
        if field_left > 0:
            field_left = max(0, field_left - 1)
            if field_left == 0:
                notes.append(f"结界到期（覆盖了爻光自己的 {field_turns} 次行动）")
        if acted_with == "战技":
            field_left = field_turns
            notes.append(f"展开结界（{field_turns} 回合，随爻光自己的回合开始递减）")

        info = table.get(acted_with) or {}
        value = info.get("value")
        base = float(BASE_ENERGY[acted_with] if value is None else value)
        gain = (base if _energy_is_fixed(info) else base * mult) + hit_e
        energy = min(max_sp, energy + gain)
        spunk += int(spunk_per)
        notes.append(f"笑点 +{spunk_per} → {spunk}")

        # 满能判定要在「开大清空」之前做，否则永远记不到"第一次满能"（踩过）
        if energy >= max_sp - 1e-9 and first_full is None:
            first_full = i

        if per_ult and i % int(per_ult) == 0 and energy >= max_sp - 1e-9:
            ults += 1
            extra_turns += 1
            back = ult_base if ult_fixed else ult_base * mult
            energy = min(max_sp, energy - max_sp + back)
            spunk += ult_spunk
            back_desc = (f"{ult_base:g}（固定回能，不吃 ERR）" if ult_fixed
                         else f"{ult_base:g}×{mult:.3f}")
            notes.append(f"开大：清空并回 {back_desc}；笑点 +{ult_spunk} → {spunk}；"
                         f"阿哈额外回合 +1（固定计入 {fixed_per_ult} 笑点）")

        rows.append({
            "index": i,
            "actedWith": acted_with,
            "energy": energy,
            "canUlt": energy >= max_sp - 1e-9,
            "spunk": spunk,
            "fieldLeft": field_left,
            "fieldActive": field_left > 0,
            "notes": notes,
        })

    sim = {"firstFullAction": first_full}

    return {
        "character": {"id": prof.get("id"), "name": prof.get("name")},
        "maxSp": prof.get("maxSp"),
        "kit": kit,
        "energyTable": table,
        "params": {
            "skillLevel": skill_level, "eidolon": eidolon, "actions": actions,
            "rotation": rotation, "openingSkill": opening_skill,
            "actionsPerUlt": _num(payload, "actionsPerUlt", 0.0),
        },
        "rows": rows,
        "totals": {"spunk": spunk, "ults": ults, "extraTurnsForAha": extra_turns},
        "firstFullAction": sim["firstFullAction"],
        "assumptions": [
            "笑点是否有上限、超出后怎么处理：数据里没有，本推演不设上限",
            "阿哈自己的行动轴（它的速度、额外回合落在哪个行动值）：不在本模块范围",
            "终结技的实际施放时机：用 actionsPerUlt 近似（每 N 次自己的行动夹一次），不是真实轴",
            "受击/击杀回能：默认 0，参数里给了才计入",
            "结界「随爻光自己的回合开始递减」：施放战技那一次直接记满回合、当回合不减，"
            "3 回合结界覆盖她自己的 3 次正常行动",
        ],
    }


@api("compare")
def compare(payload: dict[str, Any], ctx) -> dict[str, Any]:
    """同一个角色几套速度方案并排比：窗口内各能打几次行动。"""
    char_id = str(payload.get("characterId") or "")
    profile_obj: dict[str, Any] | None = None
    if char_id:
        profile_obj = _profile(ctx, char_id)
    spd = base_speed_options(profile_obj, payload)
    base = spd["used"] or _num(payload, "baseSpeed", 0)
    if base <= 0:
        base = 101.0
    lc_base = float(spd["lightconeBase"] or 0.0)
    trace_used = float(spd["trace"] or 0.0)
    rounds = _int(payload, "rounds", 4)
    window = cycle_window(rounds)
    advance = _num(payload, "advancePct", 0.0)

    plans = payload.get("plans")
    if not isinstance(plans, list) or not plans:
        # 速度鞋是**固定 +25**（满级鞋精确 25.032），不是百分比 +25；
        # 副词条那 45 固定单独标来源，不要把 70 叫成速度鞋
        plans = [
            {"label": "速度鞋", "pct": 0.0, "flat": 25.0},
            {"label": "速度鞋 + 18%", "pct": 18.0, "flat": 25.0},
            {"label": "18% + 速度鞋 + 45 副词条", "pct": 18.0, "flat": 70.0,
             "shoeFlat": 25.0, "extraFlat": 45.0},
        ]

    rows = []
    for item in plans:
        pct = _num(item, "pct", 0.0)
        flat = _num(item, "flat", 0.0)
        speed = final_speed(base, pct, flat, lightcone_base=lc_base, trace=trace_used)
        sim = simulate_actions(speed=speed, adv_percents=[advance],
                               max_actions=_int(payload, "maxActions", 30), window_av=window)
        row = {
            "label": str(item.get("label") or f"{pct:g}% + {flat:g}"),
            "pct": pct,
            "flat": flat,
            "speed": speed,
            "actions": sim["actionCount"],
            "lastAv": sim["actions"][-1]["av"] if sim["actions"] else 0.0,
        }
        if "shoeFlat" in item:
            row["shoeFlat"] = _num(item, "shoeFlat", 0.0)
        if "extraFlat" in item:
            row["extraFlat"] = _num(item, "extraFlat", 0.0)
        rows.append(row)
    return {
        "base": base, "baseSource": spd, "window": {"rounds": rounds, "av": window},
        "advancePct": advance, "rows": rows,
        "requiredForActions": {
            str(k): open_formula_speed(actions=k, window_av=window, advance_pct=advance)
            for k in (4, 5, 6, 7, 8)
        },
    }
