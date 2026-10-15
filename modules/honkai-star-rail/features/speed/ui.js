/* 配速排轴：阈值计算 / 速查表 / 行动顺序模拟 */

const DEFAULT_UNITS = [
  { name: "主C", speed: 134, startAdvance: 0, everyNActions: 0, advancePercent: 0, advanceTarget: "self" },
  { name: "辅助", speed: 160, startAdvance: 0, everyNActions: 0, advancePercent: 0, advanceTarget: "self" },
  { name: "花火", speed: 168, startAdvance: 0, everyNActions: 3, advancePercent: 24, advanceTarget: "all" },
];

function num(id, root) {
  const el = root.querySelector(id);
  return el ? Number(el.value || 0) : 0;
}

function statCard(label, value, sub = "", accent = false) {
  return `<div class="stat ${accent ? "accent" : ""}">
    <div class="k">${label}</div>
    <div class="v">${value}</div>
    ${sub ? `<div class="k small">${sub}</div>` : ""}
  </div>`;
}

export default {
  title: "配速排轴",

  async mount(root, ctx) {
    let units = DEFAULT_UNITS.map((u) => ({ ...u }));

    root.innerHTML = `
      <div class="card">
        <h2>⚡ 阈值计算：N 轮 M 动需要多少速度</h2>
        <p class="muted small" id="presets"></p>
        <div class="row">
          <div class="field"><label>轮数</label><input id="cycles" class="input narrow" type="number" value="1" min="1" step="1" /></div>
          <div class="field"><label>动数</label><input id="actions" class="input narrow" type="number" value="2" min="1" step="1" /></div>
          <div class="field"><label>风套开大次数</label><input id="wind" class="input narrow" type="number" value="0" min="0" step="1" /></div>
          <div class="field"><label>叠五舞舞舞次数</label><input id="dance" class="input narrow" type="number" value="0" min="0" step="1" /></div>
          <div class="field"><label>其它拉条 %</label><input id="extra" class="input narrow" type="number" value="0" step="1" /></div>
          <div class="field check"><input id="vonwacq" type="checkbox" /><label for="vonwacq">翁瓦克（进战拉条 40%）</label></div>
          <button id="calc" class="btn">算一下</button>
        </div>
        <div id="threshold-result"></div>
      </div>

      <div class="card">
        <h2>📋 速度速查表（无拉条）</h2>
        <div class="row">
          <div class="field"><label>最多动数</label><input id="maxActions" class="input narrow" type="number" value="10" min="1" max="30" /></div>
          <div class="field"><label>最多轮数</label><input id="maxCycles" class="input narrow" type="number" value="4" min="1" max="10" /></div>
          <button id="table-btn" class="btn secondary">生成表格</button>
        </div>
        <div id="table-result"></div>
      </div>

      <div class="card">
        <h2>🎬 行动顺序模拟</h2>
        <p class="muted small">看这套配速下谁先动、每轮动几次。拉条用“每 N 次行动触发一次”近似（如风套/舞舞舞）。</p>
        <table class="data" id="units-table">
          <thead>
            <tr>
              <th>单位</th><th class="num">速度</th><th class="num">进战拉条 %</th>
              <th class="num">每 N 动</th><th class="num">拉条 %</th><th>目标</th><th></th>
            </tr>
          </thead>
          <tbody id="units-body"></tbody>
        </table>
        <div class="row" style="margin-top:10px">
          <button id="add-unit" class="ghost">＋ 加一个单位</button>
          <div class="field"><label>模拟轮数</label><input id="sim-cycles" class="input narrow" type="number" value="3" min="1" step="1" /></div>
          <button id="sim-btn" class="btn">开始模拟</button>
        </div>
        <div id="sim-result"></div>
      </div>
    `;

    /* ---------- 预设与常数 ---------- */
    let info = { constants: {}, presets: [], advanceSources: [] };
    try {
      info = await ctx.call("info");
    } catch (err) {
      root.querySelector("#presets").textContent = `读不到配速常数：${err.message}`;
    }
    const advance = info.constants?.advance || {};
    root.querySelector("#presets").innerHTML =
      "行动值 = 10000 ÷ 速度；时间 = 轮数 × 100 + 50。" +
      (info.presets?.length
        ? " 常见目标：" +
          info.presets
            .map((p) => `<span class="pill" data-preset="${p.cycles}-${p.actions}">${p.label} = ${p.expect}</span>`)
            .join("")
        : "");
    root.querySelectorAll("[data-preset]").forEach((tag) => {
      tag.style.cursor = "pointer";
      tag.addEventListener("click", () => {
        const [cycles, actions] = tag.dataset.preset.split("-");
        root.querySelector("#cycles").value = cycles;
        root.querySelector("#actions").value = actions;
        calc();
      });
    });
    const sources = (info.advanceSources || [])
      .map((s) => `<span class="pill">${s.name}：${s.detail}</span>`)
      .join("");
    if (sources) {
      root.querySelector("#presets").insertAdjacentHTML("beforeend", `<br/>${sources}`);
    }

    /* ---------- 阈值计算 ---------- */
    async function calc() {
      const box = root.querySelector("#threshold-result");
      box.innerHTML = `<div class="loading">计算中…</div>`;
      try {
        const res = await ctx.call("threshold", {
          cycles: num("#cycles", root),
          actions: num("#actions", root),
          windUlts: num("#wind", root),
          danceUlts: num("#dance", root),
          vonwacq: root.querySelector("#vonwacq").checked,
          extraAdvancePercent: num("#extra", root),
        });
        const cuts = res.cuts.length
          ? `<table class="data" style="margin-top:10px"><thead><tr><th>拉条来源</th><th class="num">折算路程</th></tr></thead><tbody>${res.cuts
              .map((c) => `<tr><td>${c.label}</td><td class="num">−${c.distance.toFixed(0)}</td></tr>`)
              .join("")}<tr><td><b>合计</b></td><td class="num"><b>−${res.cutDistance.toFixed(0)}</b></td></tr></tbody></table>`
          : "";
        box.innerHTML = `
          <div class="stat-grid" style="margin-top:12px">
            ${statCard("需求速度", res.achievable ? res.speedCeil : "随便", res.achievable ? `精确 ${res.speedExact.toFixed(2)}` : "拉条已够", true)}
            ${statCard("可用时间", res.totalTimeAV.toFixed(0), `行动值（${res.cycles} 轮）`)}
            ${statCard("需要路程", res.distance.toFixed(0), `${res.actions} 动`)}
            ${statCard("拉条折算", `−${res.cutDistance.toFixed(0)}`, res.cuts.length ? `${res.cuts.length} 项` : "无")}
          </div>
          <p class="formula" style="margin-top:12px">${res.formula}</p>
          <p class="hint">${res.note || ""}</p>
          ${cuts}
        `;
      } catch (err) {
        box.innerHTML = `<p class="error-text">${err.message}</p>`;
      }
    }
    root.querySelector("#calc").addEventListener("click", calc);
    root.querySelectorAll("#cycles,#actions,#wind,#dance,#extra,#vonwacq").forEach((el) =>
      el.addEventListener("change", calc),
    );

    /* ---------- 速查表 ---------- */
    async function buildTable() {
      const box = root.querySelector("#table-result");
      box.innerHTML = `<div class="loading">生成中…</div>`;
      try {
        const res = await ctx.call("table", {
          maxActions: num("#maxActions", root),
          maxCycles: num("#maxCycles", root),
        });
        box.innerHTML = `
          <table class="data" style="margin-top:12px">
            <thead><tr><th>动数 \ 轮数</th>${res.cycles
              .map((c, i) => `<th class="num">${c} 轮<span class="muted small">（${res.cycleTimes[i].toFixed(0)} AV）</span></th>`)
              .join("")}</tr></thead>
            <tbody>${res.rows
              .map(
                (row) =>
                  `<tr><td>${row.actions} 动</td>${row.speeds
                    .map((s) => `<td class="num">${s.toFixed(2)}</td>`)
                    .join("")}</tr>`,
              )
              .join("")}</tbody>
          </table>
          <p class="hint">${res.note}</p>
        `;
      } catch (err) {
        box.innerHTML = `<p class="error-text">${err.message}</p>`;
      }
    }
    root.querySelector("#table-btn").addEventListener("click", buildTable);

    /* ---------- 行动顺序模拟 ---------- */
    function renderUnits() {
      const body = root.querySelector("#units-body");
      body.innerHTML = units
        .map(
          (u, i) => `<tr data-i="${i}">
            <td><input class="input" data-k="name" value="${u.name}" style="min-width:80px" /></td>
            <td><input class="input narrow" data-k="speed" type="number" value="${u.speed}" step="0.1" /></td>
            <td><input class="input narrow" data-k="startAdvance" type="number" value="${u.startAdvance}" step="1" /></td>
            <td><input class="input narrow" data-k="everyNActions" type="number" value="${u.everyNActions}" min="0" step="1" /></td>
            <td><input class="input narrow" data-k="advancePercent" type="number" value="${u.advancePercent}" min="0" step="1" /></td>
            <td>
              <select class="input" data-k="advanceTarget">
                <option value="self" ${u.advanceTarget === "self" ? "selected" : ""}>自身</option>
                <option value="all" ${u.advanceTarget === "all" ? "selected" : ""}>全队</option>
              </select>
            </td>
            <td><button class="ghost small" data-del="${i}">删</button></td>
          </tr>`,
        )
        .join("");

      body.querySelectorAll("[data-k]").forEach((el) => {
        el.addEventListener("change", () => {
          const index = Number(el.closest("tr").dataset.i);
          const key = el.dataset.k;
          units[index][key] = key === "name" || key === "advanceTarget" ? el.value : Number(el.value || 0);
        });
      });
      body.querySelectorAll("[data-del]").forEach((el) => {
        el.addEventListener("click", () => {
          units.splice(Number(el.dataset.del), 1);
          if (!units.length) units.push({ ...DEFAULT_UNITS[0] });
          renderUnits();
        });
      });
    }

    root.querySelector("#add-unit").addEventListener("click", () => {
      units.push({ name: `单位${units.length + 1}`, speed: 100, startAdvance: 0, everyNActions: 0, advancePercent: 0, advanceTarget: "self" });
      renderUnits();
    });

    async function simulate() {
      const box = root.querySelector("#sim-result");
      box.innerHTML = `<div class="loading">模拟中…</div>`;
      try {
        const res = await ctx.call("simulate", {
          units,
          cycles: num("#sim-cycles", root),
        });
        const statsTable = `
          <table class="data" style="margin-top:12px">
            <thead><tr><th>单位</th><th class="num">速度</th><th class="num">行动值</th><th class="num">总出手</th><th>每轮出手</th></tr></thead>
            <tbody>${res.stats
              .map((s) => {
                const per = Object.entries(s.perCycle)
                  .sort((a, b) => Number(a[0]) - Number(b[0]))
                  .map(([c, n]) => `第${c}轮 ${n} 次`)
                  .join("，");
                return `<tr><td>${s.name}</td><td class="num">${s.speed}</td><td class="num">${s.baseAV.toFixed(1)}</td><td class="num">${s.actions}</td><td>${per || "—"}</td></tr>`;
              })
              .join("")}</tbody>
          </table>`;

        const timeline = res.timeline
          .map(
            (e) =>
              `<tr class="${e.index === 1 ? "highlight" : ""}"><td class="num">${e.index}</td><td class="num">${e.time.toFixed(2)}</td><td class="num">第 ${e.cycle} 轮</td><td>${e.unit}</td><td class="num">第 ${e.unitAction} 次</td></tr>`,
          )
          .join("");

        box.innerHTML = `
          <div class="stat-grid" style="margin-top:12px">
            ${statCard("模拟时长", res.timeLimit.toFixed(0), `行动值（${res.cycles} 轮）`)}
            ${statCard("总行动次数", res.timeline.length, "", true)}
          </div>
          <h3>每单位统计</h3>
          ${statsTable}
          <h3>行动顺序（前 200 条）</h3>
          <div style="max-height:340px;overflow:auto">
            <table class="data">
              <thead><tr><th class="num">#</th><th class="num">时间</th><th class="num">轮次</th><th>单位</th><th class="num">该单位第几次</th></tr></thead>
              <tbody>${res.timeline.slice(0, 200).map((e) => `<tr><td class="num">${e.index}</td><td class="num">${e.time.toFixed(2)}</td><td class="num">第 ${e.cycle} 轮</td><td>${e.unit}</td><td class="num">第 ${e.unitAction} 次</td></tr>`).join("")}</tbody>
            </table>
          </div>
          ${res.timeline.length > 200 ? '<p class="hint">只显示了前 200 条。</p>' : ""}
        `;
      } catch (err) {
        box.innerHTML = `<p class="error-text">${err.message}</p>`;
      }
    }
    root.querySelector("#sim-btn").addEventListener("click", simulate);

    renderUnits();
    calc();
    buildTable();
  },

  unmount() {},
};
