/* 功能与文字：改名 / 图标 / 说明 / 隐藏 / 排序。
   编辑自动保存，外壳导航刷新页面后应用。 */

export default {
  async mount(root, ctx) {
    const data = await ctx.call("load");
    const modules = data.modules || [];
    const overrides = data.overrides || {};
    const labels = overrides.labels || {};
    const hidden = new Set(overrides.hidden || []);
    const order = overrides.order || {};

    /** 只提交和默认不一样的项（避免把当前值固化成覆盖，以后我改默认值就带不动了）。 */
    function currentOverrides() {
      const out = { labels: {}, hidden: [], order: {} };
      for (const nameInput of root.querySelectorAll("[data-name]")) {
        const key = nameInput.dataset.name;
        const iconInput = root.querySelector(`[data-icon="${key}"]`);
        const descInput = root.querySelector(`[data-desc="${key}"]`);
        const base = nameInput.dataset.base;
        const baseIcon = iconInput ? iconInput.dataset.base : "";
        const baseDesc = descInput ? descInput.dataset.base : "";
        const entry = {};
        if (nameInput.value.trim() && nameInput.value.trim() !== base) entry.name = nameInput.value.trim();
        if (iconInput && iconInput.value.trim() && iconInput.value.trim() !== baseIcon) {
          entry.icon = iconInput.value.trim();
        }
        if (descInput && descInput.value.trim() && descInput.value.trim() !== baseDesc) {
          entry.description = descInput.value.trim();
        }
        if (Object.keys(entry).length) out.labels[key] = entry;
      }
      for (const box of root.querySelectorAll("[data-hide]")) {
        if (box.checked) out.hidden.push(box.dataset.hide);
      }
      for (const input of root.querySelectorAll("[data-order]")) {
        const key = input.dataset.order;
        const base = Number(input.dataset.base || 100);
        const value = Number(input.value || base);
        if (value !== base) out.order[key] = value;
      }
      if (!Object.keys(out.labels).length) delete out.labels;
      if (!out.hidden.length) delete out.hidden;
      if (!Object.keys(out.order).length) delete out.order;
      return out;
    }

    const moduleBlocks = modules
      .map((module) => {
        const moduleKey = `module:${module.id}`;
        const features = module.features
          .map((feature) => {
            const key = `${module.id}/${feature.id}`;
            const label = labels[key] || {};
            return `
            <div class="nav-edit-feature">
              <label class="nav-edit-hide" title="勾上就在侧边栏里隐藏这个功能">
                <input type="checkbox" data-hide="${key}" ${hidden.has(key) ? "checked" : ""} /> 隐藏
              </label>
              <input class="input nav-edit-icon" data-icon="${key}" data-base="${feature.icon}" value="${(
                label.icon || feature.icon
              ).replace(/"/g, "&quot;")}" maxlength="4" title="图标（一个 emoji 就行）" />
              <input class="input nav-edit-name" data-name="${key}" data-base="${feature.name.replace(
                /"/g,
                "&quot;",
              )}" value="${(label.name || feature.name).replace(/"/g, "&quot;")}" maxlength="24" />
              <input class="input nav-edit-desc" data-desc="${key}" data-base="${feature.description.replace(
                /"/g,
                "&quot;",
              )}" value="${(label.description || feature.description).replace(
                /"/g,
                "&quot;",
              )}" maxlength="160" placeholder="功能说明（鼠标悬停时显示）" />
              <label class="nav-edit-order" title="越小越靠前">
                顺序
                <input class="input nav-edit-order-input" type="number" data-order="${key}" data-base="${
                  feature.order
                }" value="${order[key] ?? feature.order}" min="0" max="999" />
              </label>
            </div>`;
          })
          .join("");
        const moduleLabel = labels[moduleKey] || {};
        return `
        <div class="nav-edit-module">
          <div class="nav-edit-module-head">
            <label class="nav-edit-hide" title="勾上就整个模块都不显示">
              <input type="checkbox" data-hide="${moduleKey}" ${hidden.has(moduleKey) ? "checked" : ""} /> 隐藏模块
            </label>
            <input class="input nav-edit-icon" data-icon="${moduleKey}" data-base="${module.icon}" value="${(
              moduleLabel.icon || module.icon
            ).replace(/"/g, "&quot;")}" maxlength="4" />
            <input class="input nav-edit-name" data-name="${moduleKey}" data-base="${module.name.replace(
              /"/g,
              "&quot;",
            )}" value="${(moduleLabel.name || module.name).replace(/"/g, "&quot;")}" maxlength="24" />
            <label class="nav-edit-order" title="越小越靠前">
              模块顺序
              <input class="input nav-edit-order-input" type="number" data-order="${moduleKey}" data-base="${
                module.order
              }" value="${order[moduleKey] ?? module.order}" min="0" max="999" />
            </label>
          </div>
          ${features || '<p class="hint">这个模块还没有功能</p>'}
        </div>`;
      })
      .join("");

    root.innerHTML = `
      <div class="card">
        <h2>🧩 功能与文字</h2>
        <p class="hint">改这里只影响你自己的这份：功能名、图标、说明、显示/隐藏、侧边栏顺序。
          改动存到 <code>userdata/shell-overrides.json</code>（升级不丢，也不会进发给别人的包）。
          导航是外壳渲染的，所以保存后需要刷新页面才看得到。</p>
        <div class="row" style="margin-top:10px">
          <button class="btn" id="nav-save">保存</button>
          <button class="btn secondary" id="nav-save-reload">保存并刷新</button>
          <button class="ghost" id="nav-reset">恢复默认</button>
        </div>
        <p class="hint" id="nav-note"></p>
      </div>
      <div class="card">
        <h2>📚 模块与功能</h2>
        <div class="nav-edit-list">${moduleBlocks || '<p class="hint">没有扫描到模块</p>'}</div>
      </div>
    `;

    const note = (text) => {
      root.querySelector("#nav-note").textContent = text;
    };

    root.querySelector("#nav-save").addEventListener("click", async () => {
      const result = await ctx.call("save", { overrides: currentOverrides() });
      const count =
        Object.keys(result.overrides.labels || {}).length +
        (result.overrides.hidden || []).length +
        Object.keys(result.overrides.order || {}).length;
      note(`已保存 ${count} 项改动到 ${result.path}；刷新页面生效。`);
    });
    const autoSave = window.GT_LOCAL_STATE.autoCommit(root, () => ({ overrides: currentOverrides() }), payload => ctx.call("save", payload));
    this.unmount = () => autoSave.stop();

    root.querySelector("#nav-save-reload").addEventListener("click", async () => {
      await autoSave.stop();
      await ctx.call("save", { overrides: currentOverrides() });
      location.reload();
    });

    root.querySelector("#nav-reset").addEventListener("click", async () => {
      await autoSave.stop(false);
      await ctx.call("reset", {});
      ctx.persistence?.reset();
      location.reload();
    });

    note("编辑内容会自动保存到本机；导航名称、可见性和排序刷新页面后生效。");
    return () => {};
  },

  unmount() {},
};
