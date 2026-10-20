/* 文字替换：列出所有可改的固定文案，输入新文字 → 保存 → 刷新生效 */

export default {
  async mount(root, ctx) {
    const data = await ctx.call("load");
    const groups = data.groups || [];

    const blocks = groups
      .map(
        (group) => `
        <div class="texts-group">
          <h3>${group.scope}（${group.items.length} 条）</h3>
          ${group.items
            .map(
              (item) => `
            <div class="texts-row">
              <code class="texts-key" title="${item.key}">${item.key}</code>
              <span class="texts-default" title="默认文案">${item.default}</span>
              <input class="input texts-input" data-key="${item.key}" data-default="${item.default.replace(
                /"/g,
                "&quot;",
              )}" value="${(item.current || "").replace(/"/g, "&quot;")}" placeholder="（留空 = 用默认）" maxlength="200" />
            </div>`,
            )
            .join("")}
        </div>`,
      )
      .join("");

    root.innerHTML = `
      <div class="card">
        <h2>✏️ 文字替换</h2>
        <p class="hint">共 ${data.count} 条可改文案，当前改过 ${data.changed} 条。
          左边是 key（程序里的唯一名字），中间是默认文案，右边填你的说法——**留空就用默认**。
          改动存进 <code>userdata/shell-overrides.json</code> 的 <code>texts</code> 段，
          升级不丢、也不会进发给别人的包。</p>
        <div class="row" style="margin-top:10px">
          <button class="btn" id="tx-save">保存</button>
          <button class="btn secondary" id="tx-save-reload">保存并刷新</button>
          <button class="ghost" id="tx-reset">全部恢复默认</button>
        </div>
        <p class="hint" id="tx-note"></p>
      </div>
      ${blocks || '<div class="card"><p class="hint">没有找到可替换的文案（功能里还没打 key）。</p></div>'}
    `;

    const note = (text) => {
      root.querySelector("#tx-note").textContent = text;
    };

    function collect() {
      const texts = {};
      root.querySelectorAll("[data-key]").forEach((input) => {
        const value = input.value.trim();
        if (value && value !== input.dataset.default) texts[input.dataset.key] = value;
      });
      return texts;
    }

    root.querySelector("#tx-save").addEventListener("click", async () => {
      const result = await ctx.call("save", { texts: collect() });
      note(`已保存 ${Object.keys(result.texts).length} 条文字替换到 ${result.path}；刷新页面生效。`);
    });
    const autoSave = window.GT_LOCAL_STATE.autoCommit(root, () => ({ texts: collect() }), payload => ctx.call("save", payload));
    this.unmount = () => autoSave.stop();

    root.querySelector("#tx-save-reload").addEventListener("click", async () => {
      await autoSave.stop();
      await ctx.call("save", { texts: collect() });
      location.reload();
    });

    root.querySelector("#tx-reset").addEventListener("click", async () => {
      await autoSave.stop(false);
      await ctx.call("reset", {});
      ctx.persistence?.reset();
      location.reload();
    });

    note("留空 = 用默认文案。编辑内容自动保存到本机，刷新页面生效。");
    return () => {};
  },

  unmount() {},
};
