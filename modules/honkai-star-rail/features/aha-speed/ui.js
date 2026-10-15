/* 【阿哈时刻】配速 —— 原版工具原封不动嵌入。
 *
 * `original.html` 是用户提供的原文件，逐字节原样保存，一个字符都没改
 * （tests/test_toolbox.py 里有 SHA256 + 字节数校验，防止以后被误改）。
 *
 * 这里只做两件事：
 *   1. 把原文件塞进 iframe —— DOM、样式、脚本、文字、预设全部是原版；
 *   2. 如果本地备了 Tailwind（vendor/tailwind.js），就把运行时那份 HTML 里指向
 *      CDN 的那一行换成本地文件地址，这样断网打开也不会掉样式。
 *      注意：替换只发生在内存里的这份副本上，磁盘上的 original.html 始终不动。
 */

async function exists(url) {
  try {
    const response = await fetch(url, { method: "HEAD" });
    return response.ok;
  } catch {
    return false;
  }
}

export default {
  title: "阿哈时刻配速",

  async mount(root, ctx) {
    const base =
      ctx.feature.baseUrl || `/modules/${ctx.moduleId}/features/${ctx.featureId}`;

    let html;
    try {
      const response = await fetch(`${base}/original.html`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      html = await response.text();
    } catch (err) {
      root.innerHTML = `<div class="card error">
        <h2>读不到原版文件</h2>
        <p class="error-text">${ctx.ui.escapeHtml(String(err.message))}</p>
        <p class="muted small">应该是 <code>${ctx.ui.escapeHtml(base)}/original.html</code> 丢了。</p>
      </div>`;
      return;
    }

    // 离线兜底：本地有 Tailwind 就把 CDN 引用换掉（只改内存副本）
    const vendorUrl = `${base}/vendor/tailwind.js`;
    if (await exists(vendorUrl)) {
      const absolute = new URL(vendorUrl, location.origin).href;
      html = html.replace('src="https://cdn.tailwindcss.com"', `src="${absolute}"`);
    }

    root.innerHTML = `<iframe class="aha-original-frame" title="【阿哈时刻】配速（原版工具）"></iframe>`;
    const frame = root.querySelector("iframe");
    frame.setAttribute("srcdoc", html);
  },

  unmount() {},
};
