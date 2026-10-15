/* 外观与排版：改的是工具箱自己的样子。
   改动**即时预览**（直接改 CSS 变量），点「保存」才写进 userdata。 */

export default {
  async mount(root, ctx) {
    const data = await ctx.call("load");
    const defaults = data.defaults;
    const labels = data.labels || {};
    const fontChoices = data.fontChoices || [];

    /** 深合并：draft 里缺的用默认值补上，保证预览总是完整的。 */
    function merge(base, patch) {
      const out = JSON.parse(JSON.stringify(base));
      for (const [group, value] of Object.entries(patch || {})) {
        if (value && typeof value === "object" && !Array.isArray(value)) {
          out[group] = { ...(out[group] || {}), ...value };
        } else {
          out[group] = value;
        }
      }
      return out;
    }

    /** 只把「和默认值不一样」的键存下来 —— 以后我改默认配色，用户没动过的部分会跟着更新。 */
    function diffFromDefaults(theme) {
      const out = {};
      for (const group of ["colors", "fonts", "layout", "text"]) {
        const patch = {};
        for (const [key, value] of Object.entries(theme[group] || {})) {
          const base = (defaults[group] || {})[key];
          if (String(value) !== String(base)) patch[key] = value;
        }
        if (Object.keys(patch).length) out[group] = patch;
      }
      return out;
    }

    let draft = merge(defaults, data.theme || {});
    const hasTheme = () => !!(window.GTTheme && window.GTTheme.apply);

    function preview() {
      if (hasTheme()) window.GTTheme.apply(draft);
    }

    const PRESETS = {
      "默认深色": {},
      "浅色": {
        colors: {
          bg: "#f4f6f9", panel: "#ffffff", panel2: "#eef1f6", border: "#d3d9e3",
          text: "#1b1f27", muted: "#5b6473", accent: "#b0790a", accent2: "#5b4bd6",
          good: "#1f9d55", warn: "#b7791f", bad: "#c53030",
        },
      },
      "高对比": {
        colors: {
          bg: "#000000", panel: "#0b0b0b", panel2: "#151515", border: "#6b7280",
          text: "#ffffff", muted: "#c9cdd4", accent: "#ffd447", accent2: "#8f7dff",
          good: "#4ade80", warn: "#ffcc66", bad: "#ff6b6b",
        },
        layout: { radius: 4 },
      },
      "紧凑": {
        layout: { viewPadding: 10, cardPadding: 10, radius: 6, sidebarWidth: 214 },
        fonts: { baseSize: 13, lineHeight: 1.45 },
      },
      "大字": {
        fonts: { baseSize: 17, lineHeight: 1.78 },
        layout: { radius: 14, cardPadding: 20 },
      },
    };

    const colorRows = Object.entries(labels.colors || {})
      .map(
        ([key, name]) => `
        <div class="ap-row">
          <span class="ap-label">${name}</span>
          <input type="color" data-color="${key}" value="${draft.colors[key]}" />
          <input class="input ap-hex" type="text" data-color-text="${key}" value="${draft.colors[key]}" />
        </div>`,
      )
      .join("");

    const numberRows = Object.entries(labels.numbersMeta || {})
      .map(([key, meta]) => {
        const group = meta.group;
        const value = draft[group][key];
        const step = meta.max <= 3 ? 0.05 : 1;
        return `
        <div class="ap-row">
          <span class="ap-label">${meta.label}</span>
          <input type="range" data-number="${key}" min="${meta.min}" max="${meta.max}" step="${step}" value="${value}" />
          <span class="ap-value" data-number-value="${key}">${value}${meta.unit}</span>
        </div>`;
      })
      .join("");

    const fontOptions = (selected) =>
      fontChoices
        .map(
          (choice) =>
            `<option value="${choice.value.replace(/"/g, "&quot;")}" ${
              choice.value === selected ? "selected" : ""
            }>${choice.label}</option>`,
        )
        .join("");

    root.innerHTML = `
      <div class="card">
        <h2>🎨 外观与排版</h2>
        <p class="hint">改哪里都能立刻看到效果（实时预览）。满意了点「保存」，会写进
          <code>userdata/interface/theme.json</code>，升级工具箱不会丢。只保存你改过的项，
          没动过的会跟着我以后更新的默认值走。</p>
        <div class="row" style="margin-top:10px">
          ${Object.keys(PRESETS)
            .map((name) => `<button class="btn secondary" data-preset="${name}">${name}</button>`)
            .join("")}
          <button class="ghost" id="ap-reset">恢复默认</button>
        </div>
      </div>

      <div class="card">
        <h2>🎨 配色</h2>
        <div class="ap-grid">${colorRows}</div>
      </div>

      <div class="card">
        <h2>🔤 字体与字号</h2>
        <div class="ap-grid">
          <div class="ap-row">
            <span class="ap-label">界面字体</span>
            <select class="input" id="ap-sans">
              ${fontOptions(draft.fonts.sans)}
              <option value="__custom__">自定义…（在下面填）</option>
            </select>
          </div>
          <div class="ap-row">
            <span class="ap-label">自定义字体</span>
            <input class="input" id="ap-sans-custom" placeholder='例如 "Noto Sans SC", sans-serif' value="${draft.fonts.sans.replace(
              /"/g,
              "&quot;",
            )}" />
          </div>
          <div class="ap-row">
            <span class="ap-label">等宽字体（数字/公式）</span>
            <input class="input" id="ap-mono" value="${draft.fonts.mono.replace(/"/g, "&quot;")}" />
          </div>
          ${numberRows}
        </div>
      </div>

      <div class="card">
        <h2>📐 布局</h2>
        <div class="ap-grid" id="ap-layout-note">
          <p class="hint">圆角、侧边栏宽度、内容留白、卡片内边距在上一张卡片的滑块里一起调。</p>
        </div>
      </div>

      <div class="card">
        <h2>✏️ 界面文字</h2>
        <div class="ap-grid">
          ${Object.entries(labels.text || {})
            .map(
              ([key, name]) => `
            <div class="ap-row">
              <span class="ap-label">${name}</span>
              <input class="input" data-text="${key}" maxlength="40" value="${(draft.text[key] || "").replace(
                /"/g,
                "&quot;",
              )}" />
            </div>`,
            )
            .join("")}
        </div>
      </div>

      <div class="card">
        <h2>💾 保存与备份</h2>
        <div class="row">
          <button class="btn" id="ap-save">保存</button>
          <button class="btn secondary" id="ap-export">导出主题 JSON</button>
          <button class="btn secondary" id="ap-import">导入主题 JSON</button>
        </div>
        <textarea id="ap-json" class="input" rows="5" style="margin-top:10px;width:100%;font-family:var(--mono)"
          placeholder="这里会显示当前主题的 JSON；粘贴别人的主题后点「导入主题 JSON」也能应用。"></textarea>
        <p class="hint" id="ap-note"></p>
      </div>
    `;

    const note = (text, kind = "") => {
      const element = root.querySelector("#ap-note");
      element.textContent = text;
      element.className = kind === "bad" ? "error-text" : "hint";
    };

    /* ---------------- 实时预览的绑定 ---------------- */

    root.querySelectorAll("[data-color]").forEach((input) => {
      input.addEventListener("input", () => {
        const key = input.dataset.color;
        draft.colors[key] = input.value;
        const twin = root.querySelector(`[data-color-text="${key}"]`);
        if (twin) twin.value = input.value;
        preview();
      });
    });

    root.querySelectorAll("[data-color-text]").forEach((input) => {
      input.addEventListener("change", () => {
        const key = input.dataset.colorText;
        if (!/^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.test(input.value.trim())) {
          note(`颜色要写成 #123456 或 #abc 这种格式：${input.value}`, "bad");
          input.value = draft.colors[key];
          return;
        }
        draft.colors[key] = input.value.trim().toLowerCase();
        const twin = root.querySelector(`[data-color="${key}"]`);
        if (twin) twin.value = draft.colors[key];
        note("");
        preview();
      });
    });

    root.querySelectorAll("[data-number]").forEach((input) => {
      input.addEventListener("input", () => {
        const key = input.dataset.number;
        const meta = labels.numbersMeta[key];
        draft[meta.group][key] = Number(input.value);
        const label = root.querySelector(`[data-number-value="${key}"]`);
        if (label) label.textContent = `${input.value}${meta.unit}`;
        preview();
      });
    });

    root.querySelectorAll("[data-text]").forEach((input) => {
      input.addEventListener("input", () => {
        draft.text[input.dataset.text] = input.value;
        preview();
      });
    });

    root.querySelector("#ap-sans").addEventListener("change", (event) => {
      if (event.target.value === "__custom__") {
        root.querySelector("#ap-sans-custom").focus();
        return;
      }
      draft.fonts.sans = event.target.value;
      root.querySelector("#ap-sans-custom").value = event.target.value;
      preview();
    });
    root.querySelector("#ap-sans-custom").addEventListener("change", (event) => {
      if (!event.target.value.trim()) return;
      draft.fonts.sans = event.target.value.trim();
      preview();
    });
    root.querySelector("#ap-mono").addEventListener("change", (event) => {
      if (!event.target.value.trim()) return;
      draft.fonts.mono = event.target.value.trim();
      preview();
    });

    /* ---------------- 预设 / 保存 / 重置 / 导入导出 ---------------- */

    root.querySelectorAll("[data-preset]").forEach((button) => {
      button.addEventListener("click", () => {
        const preset = PRESETS[button.dataset.preset];
        draft = merge(defaults, preset);
        // 重新渲染控件（预设会一次改很多项）
        mount(root, ctx);
        if (hasTheme()) window.GTTheme.apply(draft);
      });
    });

    root.querySelector("#ap-save").addEventListener("click", async () => {
      const payload = diffFromDefaults(draft);
      const result = await ctx.call("save", { theme: payload });
      note(`已保存到 ${result.path}（只存了你改过的 ${Object.keys(payload).length} 组设置）`);
    });

    root.querySelector("#ap-reset").addEventListener("click", async () => {
      await ctx.call("reset", {});
      draft = merge(defaults, {});
      if (hasTheme()) window.GTTheme.apply({});
      mount(root, ctx);
    });

    root.querySelector("#ap-export").addEventListener("click", () => {
      const text = JSON.stringify(diffFromDefaults(draft), null, 2);
      root.querySelector("#ap-json").value = text;
      try {
        const blob = new Blob([text], { type: "application/json" });
        const link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = "game-toolbox-theme.json";
        link.click();
        URL.revokeObjectURL(link.href);
        note("已导出（同时显示在下面的文本框里，可以直接复制）");
      } catch (err) {
        note("导出下载被浏览器拦了，不过 JSON 已经显示在下面的文本框里，复制即可。");
      }
    });

    root.querySelector("#ap-import").addEventListener("click", async () => {
      const text = root.querySelector("#ap-json").value.trim();
      if (!text) {
        note("先把主题 JSON 粘到下面的文本框里", "bad");
        return;
      }
      let parsed;
      try {
        parsed = JSON.parse(text);
      } catch (err) {
        note(`JSON 解析失败：${err.message}`, "bad");
        return;
      }
      const result = await ctx.call("save", { theme: parsed });
      draft = merge(defaults, result.theme || {});
      if (hasTheme()) window.GTTheme.apply(draft);
      note("导入完成并已保存");
      mount(root, ctx);
    });

    note("改动会立刻生效；点「保存」才会记住。");
    return () => {};
  },

  unmount() {},
};
