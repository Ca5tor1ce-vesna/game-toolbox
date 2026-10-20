/* 抽卡规划：期望 / 分位 / 星琼成本 / 概率曲线 / 参数自检 */

function statCard(label, value, sub = "", accent = false) {
  return `<div class="stat ${accent ? "accent" : ""}">
    <div class="k">${label}</div>
    <div class="v ${String(value).length > 9 ? "small" : ""}">${value}</div>
    ${sub ? `<div class="k small">${sub}</div>` : ""}
  </div>`;
}

function cdfChart(cdf, marks = []) {
  if (!cdf || !cdf.length) return "";
  const W = 640;
  const H = 200;
  const left = 46;
  const right = 14;
  const top = 14;
  const bottom = 30;
  const maxX = cdf[cdf.length - 1].pulls;
  const minX = cdf[0].pulls;
  const spanX = Math.max(1, maxX - minX);

  const px = (pulls) => left + ((pulls - minX) / spanX) * (W - left - right);
  const py = (prob) => H - bottom - prob * (H - top - bottom);

  const points = cdf.map((d) => `${px(d.pulls).toFixed(1)},${py(d.cdf).toFixed(1)}`).join(" ");
  const area = `${px(minX).toFixed(1)},${py(0).toFixed(1)} ${points} ${px(maxX).toFixed(1)},${py(0).toFixed(1)}`;

  const guides = [0.5, 0.8]
    .map((q) => {
      const y = py(q).toFixed(1);
      return `<line x1="${left}" y1="${y}" x2="${W - right}" y2="${y}" stroke="#2c3240" stroke-dasharray="4 4" />
        <text x="${left - 6}" y="${Number(y) + 4}" fill="#8f97a8" font-size="10" text-anchor="end">${q * 100}%</text>`;
    })
    .join("");

  // 分位标签可能挨得很近（比如 80% 与 90% 只差几抽），太挤就只画线不写字
  let lastLabelX = -Infinity;
  const markLines = (marks || [])
    .map((m) => {
      const x = px(m.pulls);
      const showLabel = x - lastLabelX >= 34;
      if (showLabel) lastLabelX = x;
      const line = `<line x1="${x.toFixed(1)}" y1="${top}" x2="${x.toFixed(1)}" y2="${H - bottom}" stroke="#7c6cf0" stroke-width="1" stroke-dasharray="3 3" />`;
      const label = showLabel
        ? `<text x="${x.toFixed(1)}" y="${top - 2}" fill="#7c6cf0" font-size="10" text-anchor="middle">${m.label} ${m.pulls}</text>`
        : "";
      return line + label;
    })
    .join("");

  const ticks = 5;
  const xTicks = Array.from({ length: ticks }, (_, i) => {
    const value = Math.round(minX + (spanX * i) / (ticks - 1));
    return `<text x="${px(value).toFixed(1)}" y="${H - 8}" fill="#8f97a8" font-size="10" text-anchor="middle">${value}</text>`;
  }).join("");

  return `<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="累计概率曲线">
    <rect x="0" y="0" width="${W}" height="${H}" fill="transparent" />
    ${guides}
    <polygon points="${area}" fill="rgba(232,184,75,0.14)" />
    <polyline points="${points}" fill="none" stroke="#e8b84b" stroke-width="2" />
    <line x1="${left}" y1="${py(0).toFixed(1)}" x2="${W - right}" y2="${py(0).toFixed(1)}" stroke="#2c3240" />
    ${markLines}
    ${xTicks}
    <text x="${left}" y="${H - 8}" fill="#8f97a8" font-size="10">抽数</text>
  </svg>`;
}


/** 用户输入/后端回显的文本插进 HTML 前必须转义（含引号：会进 value="…"）。 */
function esc(text) {
  return String(text ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export default {
  title: "抽卡规划",

  async mount(root, ctx) {
    root.innerHTML = `
      <div class="card">
        <h2>🎲 算算要准备多少抽</h2>
        <div class="row">
          <div class="field"><label>卡池</label><select id="pool" class="input wide"></select></div>
          <div class="field"><label>当前垫抽（距上次五星）</label><input id="pity" class="input narrow" type="number" value="0" min="0" step="1" /></div>
          <div class="field"><label>目标个数</label><input id="copies" class="input narrow" type="number" value="1" min="1" max="20" step="1" /></div>
          <div class="field"><label>手上还有多少抽</label><input id="have" class="input narrow" type="number" value="" min="0" step="1" placeholder="可留空" /></div>
          <div class="field check" id="guaranteed-wrap">
            <input id="guaranteed" type="checkbox" /><label for="guaranteed">当前是大保底</label>
          </div>
          <button id="go" class="btn">计算</button>
        </div>
        <p class="hint" id="pool-hint"></p>
      </div>

      <div id="result"></div>

      <div class="card">
        <h2>🧪 参数自检</h2>
        <p class="muted small">用模型算出的期望抽数取倒数，和官方公布的综合概率对比。对不上说明游戏改过概率。</p>
        <button id="check" class="btn secondary">跑一次自检</button>
        <div id="check-result"></div>
      </div>
    `;

    let dataset = { pools: [], currency: { name: "星琼", perPull: 160 }, meta: {} };
    try {
      dataset = await ctx.call("pools");
    } catch (err) {
      root.querySelector("#pool-hint").innerHTML = `<span class="error-text">读不到卡池数据：${esc(err.message)}</span>`;
    }

    const poolSelect = root.querySelector("#pool");
    poolSelect.innerHTML = (dataset.pools || [])
      .map((p) => `<option value="${p.id}">${p.name}（${p.hardPity} 抽保底${p.upChance ? `，UP ${p.upChance * 100}%` : ""}）</option>`)
      .join("");

    const currency = dataset.currency || { name: "星琼", perPull: 160 };
    ctx.persistence?.restoreForms(root);
    const currentPool = () => (dataset.pools || []).find((p) => p.id === poolSelect.value) || {};

    function updatePoolHint() {
      const pool = currentPool();
      // 卡池没读到（数据坏了/接口报错）时保留错误提示，不要用 NaN/undefined 盖掉它
      if (!pool || pool.baseRate === undefined) return;
      const hasUp = pool.upChance !== null && pool.upChance !== undefined;
      root.querySelector("#guaranteed-wrap").classList.toggle("hidden", !hasUp);
      root.querySelector("#pool-hint").innerHTML =
        `基础 5★ 概率 ${(pool.baseRate * 100).toFixed(1)}% · 软保底从第 ${pool.softPityStart} 抽起每抽 +${(pool.softPityStep * 100).toFixed(0)}% · 硬保底 ${pool.hardPity} 抽` +
        (hasUp ? ` · UP 概率 ${pool.upChance * 100}%（歪了下次必中）` : " · 常驻池没有 UP 概念") +
        `<br/>数据版本 ${dataset.meta?.version || "?"}；每抽 ${currency.perPull} ${currency.name}。`;
    }
    poolSelect.addEventListener("change", updatePoolHint);
    updatePoolHint();

    async function run() {
      const box = root.querySelector("#result");
      box.innerHTML = `<div class="card"><div class="loading">计算中…</div></div>`;
      const haveRaw = root.querySelector("#have").value;
      try {
        const res = await ctx.call("plan", {
          pool: poolSelect.value,
          pity: Number(root.querySelector("#pity").value || 0),
          copies: Number(root.querySelector("#copies").value || 1),
          guaranteed: root.querySelector("#guaranteed").checked,
          havePulls: haveRaw === "" ? null : Number(haveRaw),
        });

        const q = res.quantiles;
        const haveBlock =
          res.probWithinHave === undefined
            ? ""
            : `<div class="stat accent">
                 <div class="k">手上 ${res.havePulls} 抽能拿到的概率</div>
                 <div class="v">${(res.probWithinHave * 100).toFixed(1)}%</div>
                 <div class="k small">${res.currencyWithinHave.toLocaleString("zh-CN")} ${currency.name}</div>
               </div>`;

        const marks = [
          { pulls: res.medianPulls, label: "中位" },
          { pulls: q["80"], label: "80%" },
          { pulls: q["90"], label: "90%" },
        ];

        const rows = res.cdf.filter((d) => d.pulls % Math.max(1, Math.ceil(res.maxPulls / 40)) === 0 || d.pulls === res.maxPulls);
        const table = `
          <div style="max-height:300px;overflow:auto;margin-top:12px">
            <table class="data">
              <thead><tr><th class="num">抽数</th><th class="num">这一抽出货</th><th class="num">累计概率</th></tr></thead>
              <tbody>${rows
                .map(
                  (d) =>
                    `<tr class="${d.pulls === res.medianPulls || d.pulls === q["80"] ? "highlight" : ""}">
                      <td class="num">${d.pulls}</td><td class="num">${(d.prob * 100).toFixed(2)}%</td><td class="num">${(d.cdf * 100).toFixed(1)}%</td>
                    </tr>`,
                )
                .join("")}</tbody>
            </table>
          </div>`;

        box.innerHTML = `
          <div class="card">
            <h2>结果：${res.targetLabel}${res.pity ? `（已垫 ${res.pity} 抽）` : ""}</h2>
            ${res.warning ? `<p class="warnbar" style="margin:0 0 12px">${res.warning}</p>` : ""}
            <div class="stat-grid">
              ${statCard("期望抽数", res.expectPulls.toFixed(1), `±${res.stdPulls.toFixed(1)}`)}
              ${statCard("中位数", res.medianPulls, "一半人比这少", true)}
              ${statCard("80% 把握", q["80"], `90% 需要 ${q["90"]} 抽`)}
              ${statCard("期望成本", res.expectCurrency.toLocaleString("zh-CN"), currency.name)}
              ${statCard("最坏情况", res.maxPulls, `硬保底上限 · 90% 成本约 ${(q["90"] * currency.perPull).toLocaleString("zh-CN")} ${currency.name}`)}
              ${haveBlock}
            </div>
            <h3>累计概率曲线</h3>
            ${cdfChart(res.cdf, marks)}
            <p class="hint">横轴是抽数，纵轴是“这么多抽内拿到的概率”。紫线是中位 / 80% / 90% 分位。</p>
            <h3>概率明细</h3>
            ${table}
          </div>
        `;
      } catch (err) {
        box.innerHTML = `<div class="card error"><p class="error-text">${esc(err.message)}</p></div>`;
      }
    }
    root.querySelector("#go").addEventListener("click", run);

    async function runCheck() {
      const box = root.querySelector("#check-result");
      box.innerHTML = `<div class="loading">自检中…</div>`;
      try {
        const res = await ctx.call("check", {});
        box.innerHTML = `
          <table class="data" style="margin-top:12px">
            <thead><tr><th>卡池</th><th class="num">硬保底</th><th class="num">模型期望抽数</th><th class="num">模型综合概率</th><th class="num">官方综合概率</th><th>结果</th></tr></thead>
            <tbody>${res.rows
              .map(
                (r) => `<tr>
                  <td>${r.name}</td>
                  <td class="num">${r.hardPity}</td>
                  <td class="num">${r.modelExpectPulls.toFixed(2)}</td>
                  <td class="num">${(r.modelOverallRate * 100).toFixed(3)}%</td>
                  <td class="num">${r.officialOverallRate ? (r.officialOverallRate * 100).toFixed(3) + "%" : "—"}</td>
                  <td>${r.ok ? "✅ 通过" : r.deviation === null ? "—" : `⚠️ 偏差 ${(r.deviation * 100).toFixed(1)}%`}</td>
                </tr>`,
              )
              .join("")}</tbody>
          </table>
          <p class="hint">${res.note}</p>
        `;
      } catch (err) {
        box.innerHTML = `<p class="error-text">${esc(err.message)}</p>`;
      }
    }
    root.querySelector("#check").addEventListener("click", runCheck);

    run();
    updatePoolHint();
  },

  unmount() {},
};
