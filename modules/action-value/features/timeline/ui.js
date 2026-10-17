/* 行动值排轴 —— 前端
 *
 * 四个页签：
 *   行动轴   —— 速度（基础白值 + 光锥白字）× (1 + 百分比) + 固定速度 + 行迹速度 → 每一动的 AV 落在第几轮
 *   回能曲线 —— 按行动序列叠能量，区分「文案 / 固定 / 通用」来源，看第几动满能
 *   爻光机制 —— 笑点 / 结界（覆盖自己 3 次正常行动） / 阿哈额外回合 / 回能节奏
 *   速度方案 —— 几套速度并排比，窗口内各能打几次行动
 */

const ROUND_CLASS = { 1: "", 2: "is-round2", 3: "is-round3", 4: "is-round4" };

function esc(v) {
  return String(v ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

function num(v, digits = 2) {
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  return n.toFixed(digits);
}

export default {
  title: "行动值排轴",

  async mount(root, ctx) {
    const state = {
      tab: "timeline",
      charId: "1502",
      catalog: [],
      excluded: [],
      lightconeBaseSpeed: 0,
      speedPct: 18,
      speedFlat: 25,
      advancePct: 0,
      delayPct: 0,
      rounds: 4,
      rotation: "战技,普攻,普攻,普攻,普攻",
      err: 20,
      hitEnergy: 0,
      actions: 12,
      actionsPerUlt: 5,
      eidolon: 0,
      skillLevel: 10,
      pathAscension: false,
      presets: [],
      presetId: "",
    };
    let last = null;
    let busy = false;

    try {
      const cat = await ctx.call("catalog");
      state.catalog = cat.characters || [];
      state.excluded = cat.excludedCharacters || [];
      if (state.catalog.length && !state.catalog.some((c) => c.id === state.charId)) {
        state.charId = state.catalog[0].id;
      }
    } catch (err) {
      root.innerHTML = `<div class="av-wrap"><div class="av-warn">读取角色目录失败：${esc(err.message || err)}</div></div>`;
      return;
    }
    try {
      const lst = await ctx.call("preset");
      state.presets = lst.presets || [];
    } catch {
      state.presets = [];
    }

    function rotationList() {
      return state.rotation
        .split(/[,，\s]+/)
        .map((s) => s.trim())
        .filter((s) => s === "普攻" || s === "战技");
    }

    function currentCatalogItem() {
      return (
        state.catalog.find((c) => c.id === state.charId) ||
        state.excluded.find((c) => c.id === state.charId) ||
        null
      );
    }

    function shell() {
      const chars = state.catalog
        .map(
          (c) =>
            `<option value="${esc(c.id)}"${c.id === state.charId ? " selected" : ""}>` +
            `${esc(c.name)}（${esc(c.pathName || c.path)}·基础${num(c.baseSpeed, 0)}+行迹${num(c.traceSpeed || 0, 0)}·上限${esc(c.maxSp)}）</option>`
        )
        .join("");
      const excludedOpts = state.excluded.length
        ? `<optgroup label="特殊能量（这套回能公式不适用）">` +
          state.excluded
            .map(
              (c) =>
                `<option value="${esc(c.id)}"${c.id === state.charId ? " selected" : ""}>` +
                `${esc(c.name)}（${esc(c.pathName || c.path)}·${esc(c.specialResource || "特殊能量")}）</option>`
            )
            .join("") +
          `</optgroup>`
        : "";
      const presetOpts = [`<option value="">（不套用，手填速度）</option>`]
        .concat(
          state.presets.map((p) => {
            const bits = [p.lightconeId ? `光锥${p.lightconeId}` : null, p.eidolon ? `E${p.eidolon}` : null]
              .filter(Boolean)
              .join(" · ");
            return (
              `<option value="${esc(p.characterId)}"${p.characterId === state.presetId ? " selected" : ""}>` +
              `${esc(p.name)}${bits ? "（" + esc(bits) + "）" : ""} · ${esc(p.savedAt || "")}</option>`
            );
          })
        )
        .join("");
      return `
      <div class="av-wrap">
        <div class="av-tabs">
          ${[
            ["timeline", "行动轴"],
            ["energy", "回能曲线"],
            ["kit", "爻光机制"],
            ["compare", "速度方案"],
          ]
            .map(
              ([k, label]) =>
                `<button class="av-tab${state.tab === k ? " is-on" : ""}" data-tab="${k}">${label}</button>`
            )
            .join("")}
        </div>
        <div class="av-bar">
          <label class="field"><span>套用「配速查询」的配装</span>
            <select id="av-preset">${presetOpts}</select></label>
          <label class="field"><span>角色（87名适用 + 7名特殊）</span>
            <select id="av-char">${chars}${excludedOpts}</select></label>
          <label class="field"><span>光锥白字</span>
            <input class="input narrow" id="av-lcbase" type="number" step="1" value="${state.lightconeBaseSpeed}"></label>
          <label class="field"><span>速度 %</span>
            <input class="input narrow" id="av-pct" type="number" step="1" value="${state.speedPct}"></label>
          <label class="field"><span>固定速度</span>
            <input class="input narrow" id="av-flat" type="number" step="1" value="${state.speedFlat}"></label>
          <label class="field"><span>拉条 %</span>
            <input class="input narrow" id="av-adv" type="number" step="1" value="${state.advancePct}"></label>
          <label class="field"><span>延后 %</span>
            <input class="input narrow" id="av-delay" type="number" step="1" value="${state.delayPct}"></label>
          <label class="field"><span>轮数</span>
            <input class="input narrow" id="av-rounds" type="number" min="1" max="20" value="${state.rounds}"></label>
          <button class="btn" id="av-run">算</button>
        </div>
        ${
          state.presets.length === 0
            ? `<div class="hint">「配速查询」里还没保存过配装 —— 去那边选好光锥/星魂/遗器后点保存，这里就能直接套用。</div>`
            : ""
        }
        <div id="av-out"></div>
      </div>`;
    }

    function renderTabs() {
      root.querySelectorAll(".av-tab").forEach((btn) => {
        btn.addEventListener("click", () => {
          state.tab = btn.dataset.tab;
          root.querySelectorAll(".av-tab").forEach((b) =>
            b.classList.toggle("is-on", b.dataset.tab === state.tab)
          );
          draw();
        });
      });
    }

    function bindBar() {
      const map = {
        "av-char": (v) => { state.charId = v; },
        "av-preset": (v) => { state.presetId = v; },
        "av-lcbase": (v) => { state.lightconeBaseSpeed = Number(v) || 0; },
        "av-pct": (v) => { state.speedPct = Number(v) || 0; },
        "av-flat": (v) => { state.speedFlat = Number(v) || 0; },
        "av-adv": (v) => { state.advancePct = Number(v) || 0; },
        "av-delay": (v) => { state.delayPct = Number(v) || 0; },
        "av-rounds": (v) => { state.rounds = Math.max(1, Number(v) || 1); },
      };
      Object.entries(map).forEach(([id, set]) => {
        const el = root.querySelector(`#${id}`);
        if (el) el.addEventListener("change", () => { set(el.value); draw(); });
      });
      const run = root.querySelector("#av-run");
      if (run) run.addEventListener("click", () => draw());
    }

    async function draw() {
      if (busy) return;
      busy = true;
      const out = root.querySelector("#av-out");
      out.innerHTML = `<div class="av-note">计算中…</div>`;
      try {
        if (state.tab === "timeline") {
          last = state.presetId
            ? await ctx.call("plan", {
                presetCharacterId: state.presetId,
                rounds: state.rounds,
                maxActions: 30,
              })
            : await ctx.call("plan", {
                characterId: state.charId,
                lightconeBaseSpeed: state.lightconeBaseSpeed,
                speedPct: state.speedPct,
                speedFlat: state.speedFlat,
                advancePct: state.advancePct,
                delayPct: state.delayPct,
                rounds: state.rounds,
                maxActions: 30,
              });
          out.innerHTML = viewTimeline(last);
        } else if (state.tab === "energy") {
          last = await ctx.call("energy", {
            characterId: state.charId,
            rotation: rotationList(),
            actions: state.actions,
            err: state.err,
            hitEnergy: state.hitEnergy,
            skillLevel: state.skillLevel,
            eidolon: state.eidolon,
          });
          out.innerHTML = viewEnergy(last);
        } else if (state.tab === "kit") {
          last = await ctx.call("yaoguang", {
            actions: state.actions,
            rotation: rotationList(),
            openingSkill: true,
            err: state.err,
            hitEnergy: state.hitEnergy,
            actionsPerUlt: state.actionsPerUlt,
            eidolon: state.eidolon,
            skillLevel: state.skillLevel,
            pathAscension: state.pathAscension,
          });
          out.innerHTML = viewKit(last);
        } else {
          last = await ctx.call("compare", {
            characterId: state.charId,
            lightconeBaseSpeed: state.lightconeBaseSpeed,
            rounds: state.rounds,
            advancePct: state.advancePct,
          });
          out.innerHTML = viewCompare(last);
        }
        bindExtra();
      } catch (err) {
        out.innerHTML = `<div class="card"><div class="av-warn">${esc(err.message || err)}</div></div>`;
      } finally {
        busy = false;
      }
    }

    function bindExtra() {
      const rot = root.querySelector("#av-rotation");
      if (rot) rot.addEventListener("change", () => { state.rotation = rot.value; draw(); });
      const err = root.querySelector("#av-err");
      if (err) err.addEventListener("change", () => { state.err = Number(err.value) || 0; draw(); });
      const hit = root.querySelector("#av-hit");
      if (hit) hit.addEventListener("change", () => { state.hitEnergy = Number(hit.value) || 0; draw(); });
      const acts = root.querySelector("#av-actions");
      if (acts) acts.addEventListener("change", () => { state.actions = Math.max(1, Number(acts.value) || 1); draw(); });
      const apu = root.querySelector("#av-apu");
      if (apu) apu.addEventListener("change", () => { state.actionsPerUlt = Number(apu.value) || 0; draw(); });
      const eid = root.querySelector("#av-eid");
      if (eid) eid.addEventListener("change", () => { state.eidolon = Number(eid.value) || 0; draw(); });
      const asc = root.querySelector("#av-ascend");
      if (asc) asc.addEventListener("change", () => { state.pathAscension = asc.checked; draw(); });
    }

    function viewTimeline(res) {
      const windowAv = res.window.av;
      const preset = res.appliedPreset || null;
      const breakdown = preset ? preset.speedBreakdown || [] : [];
      const advanceItems = (res.advance && res.advance.items) || [];
      const catItem = currentCatalogItem();
      const dots = res.actions
        .map((row) => {
          const left = Math.min(100, (row.av / windowAv) * 100);
          return `<div class="av-dot ${ROUND_CLASS[row.round] || ""}" style="left:${left}%"
                  title="第 ${row.index} 动 · AV ${num(row.av)} · 第 ${row.round} 轮"></div>
                <div class="av-dotlabel" style="left:${left}%">${row.index}</div>`;
        })
        .join("");
      const lines = [];
      for (let r = 1; r <= state.rounds; r += 1) {
        const av = r === 1 ? 0 : 150 + (r - 2) * 100;
        lines.push(`<div class="av-gridline" style="left:${Math.min(100, (av / windowAv) * 100)}%"></div>
                    <div class="av-gridlabel" style="left:${Math.min(100, (av / windowAv) * 100)}%">第${r}轮</div>`);
      }
      const rows = res.actions
        .map(
          (row) => `
        <tr>
          <td class="num">${row.index}</td>
          <td class="num">${num(row.av, 3)}</td>
          <td class="num">${num(row.gap, 3)}</td>
          <td class="num">${num(row.speed, 2)}</td>
          <td class="num">${row.round}</td>
          <td class="num">${row.advancePctUsed ? num(row.advancePctUsed, 1) + "%" : "—"}</td>
        </tr>`
        )
        .join("");

      const presetBlock = preset
        ? `
        <div class="card">
          <div class="av-summary">
            <span class="av-chip is-good">套用配装：<b>${esc(preset.name)}</b>（速度来自配速查询）${preset.savedAt ? " · " + esc(preset.savedAt) : ""}</span>
            ${preset.hasTimeline ? `<span class="av-chip is-warn">这套配置有随行动变化的加速</span>` : ""}
          </div>
          ${
            breakdown.length
              ? `<table class="data">
            <thead><tr><th>速度构成</th><th class="num">类型</th><th class="num">数值</th></tr></thead>
            <tbody>${breakdown
              .map(
                (b) => `<tr><td>${esc(b.label)}</td>
              <td class="num">${b.kind === "pct" ? "百分比" : "固定"}</td>
              <td class="num">${b.kind === "pct" ? num(b.value, 1) + "%" : "+" + num(b.value, 1)}</td></tr>`
              )
              .join("")}
            </tbody></table>`
              : ""
          }
          ${
            advanceItems.length
              ? `<div class="hint">拉条来源：${advanceItems
                  .map((i) => `${esc(i.label || i.name || "拉条")} ${num(i.percent ?? i.value, 0)}%`)
                  .join(" · ")}</div>`
              : ""
          }
        </div>`
        : "";

      const spd = res.speed || {};
      return `
        ${presetBlock}
        <div class="card">
          <div class="av-summary">
            <span class="av-chip">基础白值 <b>${num(spd.base, 0)}</b>${preset ? "（速度来自配速查询）" : ""}</span>
            ${!preset ? `<span class="av-chip">光锥白字 <b>+${num(spd.lightconeBase ?? 0, 0)}</b></span>` : ""}
            <span class="av-chip">速度百分比 <b>+${num(spd.pct ?? 0, 1)}%</b></span>
            <span class="av-chip">固定速度 <b>+${num(spd.flat ?? 0, 1)}</b></span>
            ${!preset ? `<span class="av-chip">行迹速度 <b>+${num(spd.trace ?? 0, 1)}</b>（百分比外）</span>` : ""}
            <span class="av-chip is-good">最终速度 <b>${num(spd.final, 2)}</b></span>
            <span class="av-chip">公式 <b>${esc(spd.formula || "")}</b></span>
            <span class="av-chip">窗口 <b>${num(windowAv, 0)} AV</b>（<b>${res.actionCount}</b> 动）</span>
            <span class="av-chip">拉条 <b>${num(res.advance.pct, 1)}%</b> = -${num(res.advance.distance, 0)} 距离</span>
            ${res.delay && res.delay.pct ? `<span class="av-chip is-warn">延后 <b>${num(res.delay.pct, 1)}%</b> = +${num(res.delay.distance, 0)} 距离</span>` : ""}
          </div>
          ${catItem && catItem.mechanismNote ? `<div class="hint" style="margin-top:8px;">角色机制备注：${esc(catItem.mechanismNote)}</div>` : ""}
          <div class="av-scroll">
            <div class="av-track" style="width:100%;min-width:${Math.max(520, res.actionCount * 54)}px">
              <div class="av-grid">${lines.join("")}</div>
              ${dots}
            </div>
          </div>
          <div class="hint">
            横向是行动值 0 → ${num(windowAv, 0)}（窗口）。第 1 轮 ≤ 150 AV，之后每 100 AV 一轮。
            单次行动上的拉条只扣减当前剩余路程（最低到 0），多出的部分不进入下一动。
          </div>
        </div>
        <div class="card">
          <h3>每一动</h3>
          <table class="data av-table">
            <thead><tr><th>动</th><th class="num">AV</th><th class="num">间隔</th>
              <th class="num">速度</th><th class="num">轮次</th><th class="num">拉条抵扣</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
          <div class="hint">各轮动数：${Object.entries(res.perRound).map(([r, n]) => `第${r}轮 ${n} 动`).join(" · ")}</div>
        </div>`;
    }

    function srcTag(info) {
      let cls = "is-generic";
      let label = "通用兜底值";
      if (info.source === "文案") {
        cls = "is-text";
        label = "来自技能文案（吃ERR）";
      } else if (info.source === "固定" || info.fixed) {
        cls = "is-fixed";
        label = "固定能量（不吃 ERR）";
      } else if (info.source === "手动") {
        cls = "is-manual";
        label = "手动覆盖";
      }
      return `<span class="av-src ${cls}">${num(info.value, 0)} · ${label}</span>`;
    }

    function abilityRow(slot, table) {
      const info = table[slot] || { value: 0, source: "通用" };
      return `<tr><td>${esc(slot)}</td><td class="num">${srcTag(info)}</td></tr>`;
    }

    function viewEnergy(res) {
      const table = res.energyTable || {};
      const catItem = currentCatalogItem();
      const rows = res.rows
        .map(
          (row) => `
        <tr>
          <td class="num">${row.index}</td>
          <td>${esc(row.actedWith)}</td>
          <td class="num">+${num(row.gain, 1)}</td>
          <td class="num ${row.canUlt ? "is-full" : ""}">${num(row.energy, 1)}</td>
          <td>${row.canUlt ? "可开大" : ""}</td>
          <td class="av-note">${esc((row.detail || []).join("；"))}${row.note ? " · " + esc(row.note) : ""}</td>
        </tr>`
        )
        .join("");
      return `
        <div class="av-bar">
          <label class="field"><span>自己的行动序列（循环）</span>
            <input class="input wide" id="av-rotation" value="${esc(state.rotation)}"></label>
          <label class="field"><span>能量恢复效率 %</span>
            <input class="input narrow" id="av-err" type="number" value="${state.err}"></label>
          <label class="field"><span>每动受击回能</span>
            <input class="input narrow" id="av-hit" type="number" value="${state.hitEnergy}"></label>
          <label class="field"><span>模拟动数</span>
            <input class="input narrow" id="av-actions" type="number" min="1" max="60" value="${state.actions}"></label>
        </div>
        <div class="card">
          <div class="av-summary">
            <span class="av-chip">角色 <b>${esc(res.character?.name || "")}</b></span>
            <span class="av-chip">能量上限 <b>${num(res.maxSp, 0)}</b></span>
            <span class="av-chip ${res.firstFullAction ? "is-good" : "is-warn"}">
              第一次满能：<b>${res.firstFullAction ? `第 ${res.firstFullAction} 动` : "模拟范围内没满"}</b></span>
            <span class="av-chip">能量恢复效率 <b>${num(res.err, 1)}%</b></span>
          </div>
          ${catItem && catItem.mechanismNote ? `<div class="hint" style="margin-top:8px;">排轴与回能机制：${esc(catItem.mechanismNote)}</div>` : ""}
          <div class="hint">
            常规回能：<code>实际回能 = 基础回能 × (1 + ERR%)</code>；标为<strong>固定</strong>的回能（如流萤战技、停云大招、星神★阿哈愿力）不乘 ERR。
          </div>
          <table class="data">
            <thead><tr><th>回能来源</th><th>数值与来源</th></tr></thead>
            <tbody>
              ${Object.keys(table)
                .map((s) => abilityRow(s, table))
                .join("")}
            </tbody>
          </table>
        </div>
        <div class="card">
          <h3>能量曲线</h3>
          <table class="data av-table">
            <thead><tr><th>动</th><th>使用</th><th class="num">本次回能</th>
              <th class="num">当前能量</th><th>状态</th><th>明细</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>`;
    }

    function viewKit(res) {
      const kit = res.kit || {};
      const skill = kit.skill || {};
      const ult = kit.ult || {};
      const talent = kit.talent || {};
      const rows = res.rows
        .map(
          (row) => `
        <tr>
          <td class="num">${row.index}</td>
          <td>${esc(row.actedWith)}</td>
          <td class="num">${num(row.energy, 1)}</td>
          <td class="num">${row.spunk}</td>
          <td class="num ${row.fieldActive ? "is-full" : ""}">${row.fieldLeft}</td>
          <td class="av-note">${esc((row.notes || []).join(" / "))}</td>
        </tr>`
        )
        .join("");
      const rankRows = kit.eidolonNotes || {};
      return `
        <div class="av-bar">
          <label class="field"><span>能量恢复效率 %</span>
            <input class="input narrow" id="av-err" type="number" value="${state.err}"></label>
          <label class="field"><span>每动受击回能</span>
            <input class="input narrow" id="av-hit" type="number" value="${state.hitEnergy}"></label>
          <label class="field"><span>模拟动数</span>
            <input class="input narrow" id="av-actions" type="number" min="1" max="40" value="${state.actions}"></label>
          <label class="field"><span>每几动开一次大</span>
            <input class="input narrow" id="av-apu" type="number" min="0" value="${state.actionsPerUlt}"></label>
          <label class="field"><span>星魂</span>
            <select id="av-eid">
              ${[0, 1, 2, 3, 4, 5, 6]
                .map((e) => `<option value="${e}"${e === state.eidolon ? " selected" : ""}>E${e}</option>`)
                .join("")}
            </select></label>
          <label class="field"><span>欢愉命途升格</span>
            <input id="av-ascend" type="checkbox" ${state.pathAscension ? "checked" : ""}>
          </label>
        </div>
        <div class="card">
          <div class="av-summary">
            <span class="av-chip">能量上限 <b>${num(res.maxSp, 0)}</b></span>
            <span class="av-chip ${res.firstFullAction ? "is-good" : "is-warn"}">
              第一次满能 <b>${res.firstFullAction ? `第 ${res.firstFullAction} 动` : "范围内没满"}</b></span>
            <span class="av-chip">开大 <b>${res.totals.ults}</b> 次</span>
            <span class="av-chip">阿哈额外回合 <b>${res.totals.extraTurnsForAha}</b> 个</span>
            <span class="av-chip">笑点 <b>${res.totals.spunk}</b></span>
          </div>
          <div class="av-kit">
            <div class="av-kitcard"><h4>战技 · ${esc(skill.name || "")}</h4>
              <p>展开结界 <b>${esc(skill.fieldTurns)}</b> 回合（随爻光自己的回合开始递减，覆盖自身 3 次正常行动）；
                 全队欢愉度提高爻光欢愉度的 <b>${skill.elationShare != null ? num(skill.elationShare * 100, 2) + "%" : "—"}</b>；
                 爻光施放普攻/战技后获得 <b>${esc(skill.spunkPerAction)}</b> 个笑点。</p></div>
            <div class="av-kitcard"><h4>终结技 · ${esc(ult.name || "")}</h4>
              <p>获得 <b>${esc(ult.spunk)}</b> 个笑点；使阿哈立即获得 1 个额外回合（不消耗笑点）；
                 全队全属性抗性穿透 +<b>${ult.resPen != null ? num(ult.resPen * 100, 2) + "%" : "—"}</b>，
                 持续 <b>${esc(ult.resPenTurns)}</b> 回合。</p></div>
            <div class="av-kitcard"><h4>天赋 · ${esc(talent.name || "")}</h4>
              <p>持有【好活当赏】时，我方目标施放攻击后触发【大吉大利】，额外造成
                 <b>${talent.elationDamage != null ? num(talent.elationDamage * 100, 2) + "%" : "—"}</b> 欢愉伤害
                 ${talent.ascensionBonus ? `（原倍率 ${num((talent.elationDamageBase || 0) * 100, 2)}%，固有行迹提高原倍率的 ${num(talent.ascensionBonus * 100, 0)}%）` : ""}；
                 该次攻击若消耗战技点则额外触发 1 次（本推演不模拟战技点）；触发不视为 1 次攻击。</p></div>
            <div class="av-kitcard"><h4>固有行迹 · ${esc((kit.inherentTrace || {}).name || "—")}</h4>
              <p>${kit.inherentTrace
                ? (kit.inherentTrace.active
                  ? "命途升格已计入：【大吉大利】按上面的提高后倍率，开大固定回能 +"
                    + esc(kit.inherentTrace.ultEnergy) + "、笑点 +" + esc(kit.inherentTrace.ultSpunk) + "。"
                  : "未开启。勾选「欢愉命途升格」后，【大吉大利】倍率提高原倍率的 "
                    + num((kit.inherentTrace.dajiBonus || 0) * 100, 0)
                    + "%，开大固定回能 +" + esc(kit.inherentTrace.ultEnergy)
                    + "、笑点 +" + esc(kit.inherentTrace.ultSpunk) + "。")
                : "—"}</p></div>
            <div class="av-kitcard"><h4>额外行迹</h4>
              <p>${(kit.extraTraces || []).map(esc).join(" · ") || "—"}</p></div>
          </div>
          ${rankRows.E2 ? `<div class="av-note">当前 E${state.eidolon} 生效的星魂要点：${esc(rankRows[`E${state.eidolon}`] || "")}</div>` : ""}
        </div>
        <div class="card">
          <h3>笑点 / 结界 / 回能节奏</h3>
          <table class="data av-table">
            <thead><tr><th>动</th><th>使用</th><th class="num">能量</th><th class="num">笑点</th>
              <th class="num">结界剩</th><th>说明</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
        <div class="card">
          <h3>本推演<b>不</b>假设的东西</h3>
          <div class="av-note">${(res.assumptions || []).map((a) => `· ${esc(a)}`).join("<br>")}</div>
        </div>`;
    }

    function viewCompare(res) {
      const rows = res.rows
        .map(
          (row) => `
        <tr>
          <td>${esc(row.label)}</td>
          <td class="num">${num(row.pct, 0)}%</td>
          <td class="num">${num(row.flat, 0)}</td>
          <td class="num">${num(row.speed, 2)}</td>
          <td class="num ${row.actions >= 8 ? "is-full" : ""}">${row.actions}</td>
          <td class="num">${num(row.lastAv, 1)}</td>
        </tr>`
        )
        .join("");
      const req = res.requiredForActions || {};
      const src = res.baseSource || {};
      return `
        <div class="card">
          <div class="av-summary">
            <span class="av-chip">基础速度白值 <b>${num(res.base, 1)}</b></span>
            <span class="av-chip">行迹速度 <b>+${num(src.traceSpeed || 0, 1)}</b>（百分比外）</span>
            <span class="av-chip">窗口 <b>${num(res.window.av, 0)} AV</b>（${res.window.rounds} 轮）</span>
            <span class="av-chip">拉条 <b>${num(res.advancePct, 0)}%</b></span>
          </div>
          <table class="data av-table">
            <thead><tr><th>方案</th><th class="num">速度 %</th><th class="num">固定速度</th>
              <th class="num">最终速度</th><th class="num">窗口内动数</th><th class="num">最后一动 AV</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
          <div class="hint">
            闭式解：<code>需求速度 = (动数 × 10000 − 拉条总量) ÷ 窗口 AV</code><br>
            ${Object.entries(req)
              .map(([n, v]) => `${n} 动需要 <b>${num(v, 2)}</b>`)
              .join(" · ")}
          </div>
        </div>`;
    }

    root.innerHTML = shell();
    renderTabs();
    bindBar();
    await draw();

    return () => {
      busy = true;
    };
  },

  unmount() {},
};
