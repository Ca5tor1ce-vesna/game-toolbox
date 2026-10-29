/* 共用选择菜单；保留原 select 和 change 事件，兼容动态页面与持久化。 */
window.GT_INSTALL_SELECT_MENU = () => {
  let select = null, menu = null, index = -1;
  let colorTarget = null, colorMenu = null;
  function closeColor() { colorMenu?.remove(); colorMenu = colorTarget = null; }
  function openColor(target) {
    close(); closeColor(); colorTarget = target;
    colorMenu = document.createElement('div'); colorMenu.className = 'gt-color-menu';
    colorMenu.setAttribute('role', 'group'); colorMenu.setAttribute('aria-label', '颜色选择');
    const title = document.createElement('strong'); title.textContent = '选择颜色'; colorMenu.append(title);
    const hex = document.createElement('input'); hex.type = 'text'; hex.className = 'gt-color-hex'; hex.setAttribute('aria-label', '颜色十六进制值'); hex.value = target.value; colorMenu.append(hex);
    const sliders = [];
    for (const label of ['红', '绿', '蓝']) {
      const row = document.createElement('label'); row.textContent = label;
      const slider = document.createElement('input'); slider.type = 'range'; slider.min = '0'; slider.max = '255'; slider.setAttribute('aria-label', label); row.append(slider); colorMenu.append(row); sliders.push(slider);
    }
    const syncSliders = () => sliders.forEach((slider, i) => { slider.value = parseInt(target.value.slice(1 + i * 2, 3 + i * 2), 16); });
    const update = value => { target.value = value; hex.value = target.value; syncSliders(); target.dispatchEvent(new Event('input', {bubbles:true})); target.dispatchEvent(new Event('change', {bubbles:true})); };
    sliders.forEach(slider => slider.addEventListener('input', () => update('#' + sliders.map(s => Number(s.value).toString(16).padStart(2, '0')).join(''))));
    hex.addEventListener('change', () => { if (/^#[\da-f]{6}$/i.test(hex.value)) update(hex.value); else hex.value = target.value; });
    const done = document.createElement('button'); done.type = 'button'; done.textContent = '完成'; done.onclick = () => { closeColor(); target.focus(); }; colorMenu.append(done);
    (target.closest('dialog[open]') || document.body).append(colorMenu); syncSliders();
    const rect = target.getBoundingClientRect(); colorMenu.style.left = `${Math.max(8, Math.min(rect.left, innerWidth - colorMenu.offsetWidth - 8))}px`;
    colorMenu.style.top = `${Math.max(8, Math.min(rect.bottom + 4, innerHeight - colorMenu.offsetHeight - 8))}px`;
  }
  function close(restore = false) {
    const previous = select;
    if (menu) menu.remove();
    if (previous) previous.removeAttribute('aria-expanded');
    select = menu = null;
    if (restore && previous?.isConnected) previous.focus();
  }
  function enabled() { return [...menu.querySelectorAll('[role="option"]:not([aria-disabled="true"])')]; }
  function highlight(i) {
    const choices = enabled();
    if (!choices.length) return;
    index = (i + choices.length) % choices.length;
    choices.forEach((item, n) => item.classList.toggle('is-current', n === index));
    choices[index].scrollIntoView({block: 'nearest'});
  }
  function choose(item) {
    const target = select, option = target.options[Number(item.dataset.index)];
    if (!option || option.disabled || option.parentElement?.disabled) return;
    const changed = target.selectedIndex !== option.index;
    target.selectedIndex = option.index;
    close(true);
    if (changed) { target.dispatchEvent(new Event('input', {bubbles: true})); target.dispatchEvent(new Event('change', {bubbles: true})); }
  }
  function open(target) {
    close();
    if (target.disabled || target.multiple || target.size > 1) return;
    select = target;
    menu = document.createElement('div');
    menu.className = 'gt-select-menu'; menu.setAttribute('role', 'listbox');
    const theme = getComputedStyle(target);
    const accent = theme.getPropertyValue('--accent').trim();
    if (accent) { menu.style.setProperty('--accent-strong', accent); menu.style.setProperty('--accent-soft', `color-mix(in srgb, ${accent} 14%, white)`); }
    menu.setAttribute('aria-label', target.getAttribute('aria-label') || target.labels?.[0]?.textContent?.trim() || '选择');
    let group = null;
    [...target.options].forEach((option, i) => {
      const parent = option.parentElement;
      if (parent?.tagName === 'OPTGROUP' && parent !== group) {
        group = parent; const heading = document.createElement('div'); heading.className = 'gt-select-group'; heading.textContent = parent.label; menu.append(heading);
      } else if (parent?.tagName !== 'OPTGROUP') group = null;
      const row = document.createElement('div'); row.setAttribute('role', 'option'); row.dataset.index = i;
      row.setAttribute('aria-selected', String(option.selected)); row.setAttribute('aria-disabled', String(option.disabled || !!parent?.disabled));
      row.textContent = option.textContent; menu.append(row);
    });
    (target.closest('dialog[open]') || document.body).append(menu); target.setAttribute('aria-expanded', 'true');
    const rect = target.getBoundingClientRect();
    menu.style.width = `${Math.max(rect.width, 180)}px`;
    menu.style.left = `${Math.max(8, Math.min(rect.left, innerWidth - menu.offsetWidth - 8))}px`;
    const below = innerHeight - rect.bottom, above = rect.top;
    menu.style.maxHeight = `${Math.max(80, Math.min(300, Math.max(below, above) - 12))}px`;
    menu.style.top = below >= 180 || below >= above ? `${rect.bottom + 4}px` : `${Math.max(8, rect.top - menu.offsetHeight - 4)}px`;
    const choices = enabled(); index = Math.max(0, choices.findIndex(row => Number(row.dataset.index) === target.selectedIndex)); highlight(index);
  }
  document.addEventListener('mousedown', event => {
    const color = event.target.closest('input[type="color"]');
    if (color && !color.disabled) { event.preventDefault(); color.focus(); if (colorTarget === color) closeColor(); else openColor(color); return; }
    if (colorMenu && !colorMenu.contains(event.target)) closeColor();
    const target = event.target.closest('select');
    if (target && !target.disabled && !target.multiple && target.size <= 1) { event.preventDefault(); target.focus(); if (select === target) close(); else open(target); }
    else if (menu && !menu.contains(event.target)) close();
  }, true);
  document.addEventListener('click', event => {
    if (event.target.closest('input[type="color"]')) { event.preventDefault(); return; }
    const item = event.target.closest('.gt-select-menu [role="option"]');
    if (item && menu?.contains(item)) { event.preventDefault(); choose(item); }
  });
  document.addEventListener('click', event => {
    const target = event.target.closest('select');
    if (target && !target.disabled && !target.multiple && target.size <= 1) event.preventDefault();
  }, true);
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && colorMenu) { event.preventDefault(); const previous = colorTarget; closeColor(); previous?.focus(); return; }
    if (event.target.matches('input[type="color"]') && ['Enter', ' '].includes(event.key)) { event.preventDefault(); if (colorTarget === event.target) closeColor(); else openColor(event.target); return; }
    const target = event.target.closest('select');
    if (!target || target.disabled || target.multiple || target.size > 1) return;
    if (select !== target) {
      if (['Enter', ' ', 'ArrowDown', 'ArrowUp'].includes(event.key)) { event.preventDefault(); open(target); }
      return;
    }
    if (event.key === 'Escape' || event.key === 'Tab') { if (event.key === 'Escape') event.preventDefault(); close(); }
    else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') { event.preventDefault(); highlight(index + (event.key === 'ArrowDown' ? 1 : -1)); }
    else if (event.key === 'Home' || event.key === 'End') { event.preventDefault(); highlight(event.key === 'Home' ? 0 : enabled().length - 1); }
    else if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); const item = enabled()[index]; if (item) choose(item); }
    else if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) { const choices = enabled(); const found = choices.findIndex(item => item.textContent.trim().toLocaleLowerCase().startsWith(event.key.toLocaleLowerCase())); if (found >= 0) { event.preventDefault(); highlight(found); } }
  });
  document.addEventListener('scroll', event => { if (menu && !menu.contains(event.target)) close(); if (colorMenu && !colorMenu.contains(event.target)) closeColor(); }, true);
  window.addEventListener('resize', () => { close(); closeColor(); });
};
window.GT_INSTALL_SELECT_MENU();

window.GT_DIALOG = (message, confirm = false) => new Promise(resolve => {
  const dialog = document.createElement('dialog');
  dialog.className = 'gt-dialog';
  const text = document.createElement('p'); text.textContent = message;
  const actions = document.createElement('div'); actions.className = 'gt-dialog-actions';
  if (confirm) { const cancel = document.createElement('button'); cancel.type = 'button'; cancel.textContent = '取消'; cancel.onclick = () => dialog.close('cancel'); actions.append(cancel); }
  const ok = document.createElement('button'); ok.type = 'button'; ok.className = 'gt-dialog-primary'; ok.textContent = '确定'; ok.onclick = () => dialog.close('ok'); actions.append(ok);
  dialog.append(text, actions); document.body.append(dialog);
  dialog.addEventListener('close', () => { const accepted = dialog.returnValue === 'ok'; dialog.remove(); resolve(accepted); }, { once: true });
  dialog.showModal(); (confirm ? actions.firstElementChild : ok).focus();
});
