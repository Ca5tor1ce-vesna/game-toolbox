"""崩铁配速 / 排轴。

两条基本规则（其余都是推论）：

1. **行动值** ``AV = 10000 / 速度``。谁剩余 AV 最小谁先动。
2. **轮次时间** ``t = 轮数 × 100 + 50``：首轮 150 AV，之后每轮 100 AV。

阈值公式（社区通用写法，等价于“路程 ÷ 时间”）：

    需求速度 = (动数 × 10000 − 拉条总量) ÷ (轮数 × 100 + 50)

拉条按“缩短路程”折算：拉条 25% ⇒ 减 2500。
"""

from __future__ import annotations

import math
from typing import Any

from core.feature_api import api

EPS = 1e-9


def _constants(ctx) -> dict[str, Any]:
    data = ctx.data("speed_presets") or {}
    raw = data.get("constants") or {}
    advance = raw.get("advance") or {}
    return {
        "distancePerAction": float(raw.get("distancePerAction", 10000)),
        "firstCycleAV": float(raw.get("firstCycleAV", 150)),
        "cycleAV": float(raw.get("cycleAV", 100)),
        "advance": {
            "windSetPerUlt": float(advance.get("windSetPerUlt", 25)),
            "danceDanceDanceS5PerUlt": float(advance.get("danceDanceDanceS5PerUlt", 24)),
            "vonwacqOnEnter": float(advance.get("vonwacqOnEnter", 40)),
        },
    }


def _num(payload: dict[str, Any], key: str, default: float = 0.0) -> float:
    value = payload.get(key, default)
    if value is None or value == "":
        return float(default)
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"参数 {key} 需要是数字，收到 {value!r}") from exc


def _time_for(cycles: float, const: dict[str, Any]) -> float:
    """轮数 → 可用行动值总量。首轮 150，其后每轮 100。"""
    return cycles * const["cycleAV"] + (const["firstCycleAV"] - const["cycleAV"])


def cycle_of(time_av: float, const: dict[str, Any]) -> int:
    """某个时刻落在第几轮。"""
    first = const["firstCycleAV"]
    step = const["cycleAV"]
    if time_av <= first + EPS:
        return 1
    return 1 + int(math.ceil((time_av - first) / step - EPS))


@api("info")
def info(payload: dict[str, Any], ctx) -> dict[str, Any]:
    """常数、常见阈值、拉条来源。"""
    data = ctx.data("speed_presets") or {}
    return {
        "constants": _constants(ctx),
        "presets": data.get("presets") or [],
        "advanceSources": data.get("advanceSources") or [],
        "meta": data.get("meta") or {},
    }


@api("base")
def base(payload: dict[str, Any], ctx) -> dict[str, Any]:
    """速度 ↔ 行动值 换算。"""
    const = _constants(ctx)
    speed = _num(payload, "speed")
    if speed <= 0:
        raise ValueError("速度必须大于 0")
    distance = const["distancePerAction"]
    av = distance / speed
    return {
        "speed": speed,
        "actionValue": av,
        "firstCycleActions": const["firstCycleAV"] / av,
        "perCycleActions": const["cycleAV"] / av,
        "note": "行动值越小越先出手；出手一次消耗一整条行动值。",
    }


@api("threshold")
def threshold(payload: dict[str, Any], ctx) -> dict[str, Any]:
    """N 轮 M 动需要多少速度（可扣掉拉条）。"""
    const = _constants(ctx)
    cycles = _num(payload, "cycles", 1)
    actions = _num(payload, "actions", 2)
    if cycles <= 0:
        raise ValueError("轮数必须大于 0")
    if actions <= 0:
        raise ValueError("动数必须大于 0")

    distance = actions * const["distancePerAction"]
    total_time = _time_for(cycles, const)
    advance = const["advance"]

    cuts: list[dict[str, Any]] = []
    cut_total = 0.0

    def add_cut(label: str, percent_total: float) -> None:
        nonlocal cut_total
        value = percent_total / 100.0 * const["distancePerAction"]
        if value <= 0:
            return
        cuts.append({"label": label, "distance": value, "percent": percent_total})
        cut_total += value

    wind = _num(payload, "windUlts")
    dance = _num(payload, "danceUlts")
    extra = _num(payload, "extraAdvancePercent")
    vonwacq = bool(payload.get("vonwacq"))

    if wind > 0:
        add_cut(f"风套 × {wind:g} 次开大", wind * advance["windSetPerUlt"])
    if dance > 0:
        add_cut(f"叠五舞舞舞 × {dance:g} 次开大", dance * advance["danceDanceDanceS5PerUlt"])
    if vonwacq:
        add_cut("翁瓦克（进战一次性）", advance["vonwacqOnEnter"])
    if extra > 0:
        add_cut(f"其它拉条 {extra:g}%", extra)

    effective = distance - cut_total
    result: dict[str, Any] = {
        "cycles": cycles,
        "actions": actions,
        "totalTimeAV": total_time,
        "distance": distance,
        "cuts": cuts,
        "cutDistance": cut_total,
        "effectiveDistance": effective,
        "achievable": effective > 0,
    }

    if effective <= 0:
        result.update(
            {
                "speed": 0.0,
                "speedCeil": 0,
                "speedExact": 0.0,
                "formula": f"{actions:g}×10000 = {distance:g} ≤ 拉条总量 {cut_total:g}，任何速度都够",
                "note": "拉条总量已经覆盖所需路程，速度再低也能达成；实战还受充能/手法限制。",
            }
        )
        return result

    speed = effective / total_time
    result.update(
        {
            "speed": speed,
            "speedExact": speed,
            "speedCeil": int(math.ceil(speed - EPS)),
            "speedFloor2": math.floor(speed * 100) / 100,
            "formula": f"({actions:g}×10000 − {cut_total:g}) ÷ {total_time:g} = {speed:.2f}",
            "note": (
                f"实战按 {int(math.ceil(speed - EPS))} 速堆（面板速度取整向上），"
                "留一点余量更稳。"
            ),
        }
    )
    return result


@api("table")
def table(payload: dict[str, Any], ctx) -> dict[str, Any]:
    """速查表：行=动数，列=轮数，值=无拉条时需要的速度。"""
    const = _constants(ctx)
    max_actions = int(_num(payload, "maxActions", 10))
    max_cycles = int(_num(payload, "maxCycles", 4))
    max_actions = max(1, min(max_actions, 30))
    max_cycles = max(1, min(max_cycles, 10))

    cycles = list(range(1, max_cycles + 1))
    rows: list[dict[str, Any]] = []
    for actions in range(1, max_actions + 1):
        speeds = []
        for cycle in cycles:
            speeds.append(actions * const["distancePerAction"] / _time_for(cycle, const))
        rows.append({"actions": actions, "speeds": speeds})
    return {
        "cycles": cycles,
        "cycleTimes": [_time_for(c, const) for c in cycles],
        "rows": rows,
        "note": "表里是“不带任何拉条”的需求速度；带拉条请用上面的阈值计算。",
    }


@api("simulate")
def simulate(payload: dict[str, Any], ctx) -> dict[str, Any]:
    """多单位行动顺序模拟。

    每个单位可配：速度、进战初始拉条%、每 N 次行动触发的拉条%（自身或全队）。
    用于看“这套配速到底谁先动、几轮动几次”。
    """
    const = _constants(ctx)
    raw_units = payload.get("units")
    if not isinstance(raw_units, list) or not raw_units:
        raise ValueError("至少需要一个单位")

    cycles = _num(payload, "cycles", 3)
    limit_raw = payload.get("timeLimit")
    if limit_raw in (None, ""):
        if cycles <= 0:
            raise ValueError("轮数必须大于 0")
        limit = _time_for(cycles, const)
    else:
        limit = float(limit_raw)

    distance = const["distancePerAction"]
    units: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_units):
        if not isinstance(raw, dict):
            raise ValueError(f"第 {index + 1} 个单位不是对象")
        speed = float(raw.get("speed") or 0)
        if speed <= 0:
            raise ValueError(f"第 {index + 1} 个单位的速度必须大于 0")
        base_av = distance / speed
        start_advance = min(max(float(raw.get("startAdvance") or 0), 0.0), 100.0)
        units.append(
            {
                "slot": index,
                "name": str(raw.get("name") or f"单位{index + 1}"),
                "speed": speed,
                "baseAV": base_av,
                "nextAV": base_av * (1 - start_advance / 100.0),
                "actions": 0,
                "every": int(raw.get("everyNActions") or 0),
                "advPercent": float(raw.get("advancePercent") or 0),
                "advTarget": "all" if str(raw.get("advanceTarget") or "self") == "all" else "self",
            }
        )

    timeline: list[dict[str, Any]] = []
    clock = 0.0
    max_events = 6000

    while len(timeline) < max_events:
        smallest = min(unit["nextAV"] for unit in units)
        if clock + smallest > limit + EPS:
            break
        clock += smallest
        for unit in units:
            unit["nextAV"] -= smallest

        ready = [unit for unit in units if unit["nextAV"] <= EPS]
        # 同一时刻多人行动：速度高的先动，速度相同按输入顺序
        ready.sort(key=lambda unit: (-unit["speed"], unit["slot"]))
        actor = ready[0]
        for other in ready[1:]:
            other["nextAV"] = 1e-6  # 同刻的人紧接着动，不推进时钟

        actor["nextAV"] = actor["baseAV"]
        actor["actions"] += 1
        timeline.append(
            {
                "index": len(timeline) + 1,
                "time": round(clock, 3),
                "cycle": cycle_of(clock, const),
                "slot": actor["slot"],
                "unit": actor["name"],
                "speed": actor["speed"],
                "unitAction": actor["actions"],
            }
        )

        if actor["every"] > 0 and actor["advPercent"] > 0 and actor["actions"] % actor["every"] == 0:
            targets = units if actor["advTarget"] == "all" else [actor]
            for target in targets:
                target["nextAV"] = max(
                    0.0, target["nextAV"] - target["baseAV"] * actor["advPercent"] / 100.0
                )

    stats: list[dict[str, Any]] = []
    for unit in units:
        per_cycle: dict[str, int] = {}
        for event in timeline:
            if event["slot"] == unit["slot"]:
                key = str(event["cycle"])
                per_cycle[key] = per_cycle.get(key, 0) + 1
        stats.append(
            {
                "slot": unit["slot"],
                "name": unit["name"],
                "speed": unit["speed"],
                "baseAV": round(unit["baseAV"], 3),
                "actions": unit["actions"],
                "perCycle": per_cycle,
            }
        )

    return {
        "timeLimit": limit,
        "cycles": cycles,
        "timeline": timeline,
        "stats": stats,
        "truncated": len(timeline) >= max_events,
    }
