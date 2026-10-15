"""崩铁抽卡规划。

概率模型
--------
设 ``n`` 为“距离上一个五星已经抽了多少次 + 1”（也就是这一抽的序号）：

* ``n <  softPityStart``：``p(n) = baseRate``
* ``n >= softPityStart``：``p(n) = baseRate + softPityStep × (n − softPityStart + 1)``
* ``n == hardPity``：``p(n) = 1``（硬保底）

这个模型可以用官方公布的**综合概率**反向自检：模型算出的期望抽数取倒数，
应该约等于官方综合概率（角色池 1.600%，光锥池 1.870%）。`check` 动作就是干这个的。

大保底：五星有 ``upChance`` 概率是当期 UP；歪了下一个五星必是 UP（角色 50%、光锥 75%）。
"""

from __future__ import annotations

import math
from typing import Any

from core.feature_api import api

Distribution = dict[int, float]


def _dataset(ctx) -> dict[str, Any]:
    data = ctx.data("gacha_pools") or {}
    if not data.get("pools"):
        raise ValueError("卡池数据缺失：modules/honkai-star-rail/data/gacha_pools.json")
    return data


def _pool(data: dict[str, Any], pool_id: str | None) -> dict[str, Any]:
    pools = data["pools"]
    wanted = str(pool_id or pools[0].get("id"))
    for pool in pools:
        if pool.get("id") == wanted:
            return pool
    raise ValueError(f"未知卡池 {wanted!r}；可选：{[p.get('id') for p in pools]}")


def rate_at(pool: dict[str, Any], n: int) -> float:
    """第 n 抽（自上次五星起算）出五星的概率。"""
    base = float(pool.get("baseRate") or 0)
    hard = int(pool.get("hardPity") or 90)
    if n >= hard:
        return 1.0
    start = int(pool.get("softPityStart") or hard)
    step = float(pool.get("softPityStep") or 0)
    if n < start:
        return min(1.0, base)
    return min(1.0, base + step * (n - start + 1))


def five_star_pmf(pool: dict[str, Any], start_pity: int = 0) -> Distribution:
    """距离下一个五星的抽数分布：{抽数: 概率}。"""
    hard = int(pool.get("hardPity") or 90)
    start_pity = max(0, int(start_pity))
    if start_pity >= hard:
        return {1: 1.0}

    out: Distribution = {}
    survival = 1.0
    n = start_pity
    while n < hard and survival > 1e-15:
        n += 1
        p = rate_at(pool, n)
        out[n - start_pity] = survival * p
        survival *= 1.0 - p
    return out


def _convolve(a: Distribution, b: Distribution) -> Distribution:
    out: Distribution = {}
    for ka, pa in a.items():
        if pa <= 0:
            continue
        for kb, pb in b.items():
            key = ka + kb
            out[key] = out.get(key, 0.0) + pa * pb
    return out


def _scale(dist: Distribution, factor: float) -> Distribution:
    return {k: v * factor for k, v in dist.items()}


def _add(a: Distribution, b: Distribution) -> Distribution:
    out = dict(a)
    for k, v in b.items():
        out[k] = out.get(k, 0.0) + v
    return out


def _summarize(dist: Distribution, per_pull_cost: float) -> dict[str, Any]:
    total = sum(dist.values())
    if total <= 0:
        raise ValueError("分布为空，无法统计")
    norm = {k: v / total for k, v in dist.items()}
    items = sorted(norm.items())

    mean = sum(k * v for k, v in items)
    variance = sum((k - mean) ** 2 * v for k, v in items)
    cumulative = 0.0
    cdf: list[dict[str, float]] = []
    for pulls, prob in items:
        cumulative += prob
        cdf.append({"pulls": pulls, "prob": prob, "cdf": min(1.0, cumulative)})

    def quantile(q: float) -> int:
        acc = 0.0
        for pulls, prob in items:
            acc += prob
            if acc >= q - 1e-12:
                return pulls
        return items[-1][0]

    return {
        "expectPulls": mean,
        "stdPulls": math.sqrt(variance),
        "medianPulls": quantile(0.5),
        "quantiles": {
            "50": quantile(0.5),
            "80": quantile(0.8),
            "90": quantile(0.9),
            "99": quantile(0.99),
        },
        "maxPulls": items[-1][0],
        "minPulls": items[0][0],
        "expectCurrency": mean * per_pull_cost,
        "quantileCurrency": {
            "50": quantile(0.5) * per_pull_cost,
            "80": quantile(0.8) * per_pull_cost,
            "90": quantile(0.9) * per_pull_cost,
        },
        "cdf": cdf,
    }


def _up_dist(
    pool: dict[str, Any], start_pity: int, guaranteed: bool, copies: int, up_chance: float
) -> Distribution:
    """拿到 copies 个当期 UP 的抽数分布。"""
    dist: Distribution = {0: 1.0}
    pity = start_pity
    for _ in range(copies):
        first = five_star_pmf(pool, pity)
        if guaranteed:
            need = first
            guaranteed = False
        else:
            # up_chance 直接中；否则要两个五星（第二个必中）
            second = five_star_pmf(pool, 0)
            need = _add(_scale(first, up_chance), _scale(_convolve(first, second), 1 - up_chance))
            guaranteed = False
        dist = _convolve(dist, need)
        pity = 0
    return dist


def _any_dist(pool: dict[str, Any], start_pity: int, copies: int) -> Distribution:
    """常驻池：拿到 copies 个五星（不分是不是 UP）。"""
    dist: Distribution = {0: 1.0}
    for index in range(copies):
        piece = five_star_pmf(pool, start_pity if index == 0 else 0)
        dist = _convolve(dist, piece)
    return dist


@api("pools")
def pools(payload: dict[str, Any], ctx) -> dict[str, Any]:
    """卡池列表 + 货币信息 + 参数来源。"""
    data = _dataset(ctx)
    return {
        "pools": data["pools"],
        "currency": data.get("currency") or {"name": "星琼", "perPull": 160},
        "meta": data.get("meta") or {},
    }


@api("single")
def single(payload: dict[str, Any], ctx) -> dict[str, Any]:
    """距离下一个五星。"""
    data = _dataset(ctx)
    pool = _pool(data, payload.get("pool"))
    pity = max(0, int(float(payload.get("pity") or 0)))
    cost = float((data.get("currency") or {}).get("perPull") or 160)
    hard = int(pool.get("hardPity") or 90)

    summary = _summarize(five_star_pmf(pool, pity), cost)
    summary.update(
        {
            "pool": pool,
            "pity": pity,
            "pityToHard": max(0, hard - pity),
            "kind": "fiveStar",
            "note": "这是“下一个五星”的分布，不区分是否 UP。",
        }
    )
    return summary


@api("plan")
def plan(payload: dict[str, Any], ctx) -> dict[str, Any]:
    """拿到 N 个当期 UP（或 N 个五星）需要多少抽。"""
    data = _dataset(ctx)
    pool = _pool(data, payload.get("pool"))
    pity = max(0, int(float(payload.get("pity") or 0)))
    copies = max(1, min(int(float(payload.get("copies") or 1)), 20))
    guaranteed = bool(payload.get("guaranteed"))
    cost = float((data.get("currency") or {}).get("perPull") or 160)
    hard = int(pool.get("hardPity") or 90)
    up_chance = pool.get("upChance")

    if up_chance is None:
        dist = _any_dist(pool, pity, copies)
        kind = "fiveStar"
        target_label = f"{copies} 个五星"
    else:
        dist = _up_dist(pool, pity, guaranteed, copies, float(up_chance))
        kind = "up"
        target_label = f"{copies} 个当期 UP"

    summary = _summarize(dist, cost)
    summary.update(
        {
            "pool": pool,
            "pity": pity,
            "copies": copies,
            "guaranteed": guaranteed,
            "kind": kind,
            "targetLabel": target_label,
            "pityToHard": max(0, hard - pity),
        }
    )

    have = payload.get("havePulls")
    if have not in (None, ""):
        have = max(0, int(float(have)))
        cumulative = 0.0
        for pulls, prob in sorted(dist.items()):
            if pulls <= have:
                cumulative += prob
        summary["havePulls"] = have
        summary["probWithinHave"] = cumulative
        summary["currencyWithinHave"] = have * cost

    if pity >= hard:
        summary["warning"] = "垫抽已达硬保底：下一抽必出五星。"
    elif guaranteed and up_chance is not None:
        summary["warning"] = "当前是大保底状态：下一个五星必定是当期 UP。"
    return summary


@api("check")
def check(payload: dict[str, Any], ctx) -> dict[str, Any]:
    """参数自检：模型算出的期望抽数取倒数，和官方综合概率对一下。"""
    data = _dataset(ctx)
    rows: list[dict[str, Any]] = []
    for pool in data["pools"]:
        dist = five_star_pmf(pool, 0)
        mean = sum(k * v for k, v in dist.items())
        official = pool.get("officialOverallRate")
        model_rate = 1.0 / mean if mean else 0.0
        deviation = abs(model_rate - float(official)) / float(official) if official else None
        rows.append(
            {
                "id": pool.get("id"),
                "name": pool.get("name"),
                "hardPity": pool.get("hardPity"),
                "baseRate": pool.get("baseRate"),
                "softPityStart": pool.get("softPityStart"),
                "modelExpectPulls": mean,
                "modelOverallRate": model_rate,
                "officialOverallRate": official,
                "deviation": deviation,
                "ok": deviation is not None and deviation < 0.02,
            }
        )
    return {
        "rows": rows,
        "note": "偏差在 2% 以内算通过；对不上通常说明游戏改过概率，去 data/gacha_pools.json 调软保底参数。",
    }
