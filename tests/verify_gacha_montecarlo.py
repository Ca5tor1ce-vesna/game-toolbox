"""用蒙特卡洛交叉验证抽卡解析解。

解析解（api.py 里的卷积）容易写错而自己看不出来，所以用独立实现的随机模拟对拍一次。
这个脚本不进常规测试（要跑几秒），想验证时手动跑：

    <python> tests/verify_gacha_montecarlo.py 200000
"""

from __future__ import annotations

import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import feature_api, registry  # noqa: E402

MODULE_ID = "honkai-star-rail"


def _load() -> None:
    modules, errors = registry.scan()
    for module in modules:
        for feature in module.features:
            assert feature.dir is not None
            api_path = feature.dir / feature.api_file
            if api_path.is_file():
                feature_api.load_feature_api(
                    module.id, feature.id, api_path, module.dir, feature.dir, errors
                )


def call(feature: str, action: str, payload: dict | None = None):
    return feature_api.call(MODULE_ID, feature, action, payload or {})


def simulate_once(rng: random.Random, pool: dict, pity: int, guaranteed: bool, need_up: bool) -> int:
    """独立实现的抽卡模拟：返回拿到目标所需抽数。"""
    hard = pool["hardPity"]
    base = pool["baseRate"]
    start = pool["softPityStart"]
    step = pool["softPityStep"]
    up_chance = pool.get("upChance")

    pulls = 0
    counter = pity  # 距离上一个五星已抽次数
    while True:
        pulls += 1
        counter += 1
        if counter >= hard:
            p = 1.0
        elif counter < start:
            p = base
        else:
            p = min(1.0, base + step * (counter - start + 1))

        if rng.random() < p:
            counter = 0
            if not need_up or up_chance is None:
                return pulls
            if guaranteed or rng.random() < up_chance:
                return pulls
            guaranteed = True  # 歪了，下一个五星必是 UP


class TestMonteCarlo(unittest.TestCase):
    N = 200_000

    @classmethod
    def setUpClass(cls) -> None:
        _load()
        pools = call("gacha", "pools")["pools"]
        cls.pools = {p["id"]: p for p in pools}
        cls.rng = random.Random(20261014)

    def compare(self, pool_id: str, copies: int, guaranteed: bool, tolerance: float) -> None:
        pool = self.pools[pool_id]
        analytic = call(
            "gacha",
            "plan",
            {"pool": pool_id, "copies": copies, "guaranteed": guaranteed},
        )
        total = 0
        results = []
        for _ in range(self.N):
            pulls = 0
            g = guaranteed
            for _ in range(copies):
                pulls += simulate_once(self.rng, pool, 0, g, True)
                g = False
            results.append(pulls)
            total += pulls
        empirical_mean = total / self.N
        results.sort()
        empirical_median = results[self.N // 2]
        empirical_p80 = results[int(self.N * 0.8)]
        empirical_p90 = results[int(self.N * 0.9)]

        print(
            f"  {pool['name']} × {copies}{'（大保底）' if guaranteed else ''}："
            f"期望 解析 {analytic['expectPulls']:.2f} / 模拟 {empirical_mean:.2f} | "
            f"中位 解析 {analytic['medianPulls']} / 模拟 {empirical_median} | "
            f"80% 解析 {analytic['quantiles']['80']} / 模拟 {empirical_p80} | "
            f"90% 解析 {analytic['quantiles']['90']} / 模拟 {empirical_p90}"
        )
        self.assertAlmostEqual(
            empirical_mean / analytic["expectPulls"], 1.0, delta=tolerance,
            msg=f"{pool_id} 期望偏差过大",
        )

    def test_character_single_guaranteed(self) -> None:
        self.compare("character_event", 1, True, 0.01)

    def test_character_single_fifty_fifty(self) -> None:
        self.compare("character_event", 1, False, 0.01)

    def test_character_two_copies(self) -> None:
        self.compare("character_event", 2, False, 0.02)

    def test_lightcone_single(self) -> None:
        self.compare("lightcone_event", 1, False, 0.01)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        TestMonteCarlo.N = int(sys.argv[1])
    print(f"蒙特卡洛验证（每个用例 {TestMonteCarlo.N} 次模拟）：")
    unittest.main(verbosity=2, argv=[sys.argv[0]])
