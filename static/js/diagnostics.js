(() => {
  const box = document.getElementById('diagnostic-rows');
  if (!box) return;
  const total = document.getElementById('id_items-TOTAL_FORMS');
  const status = document.getElementById('diagnostic-status');
  const catalog = JSON.parse(document.getElementById('diagnostic-catalog').textContent);
  const estimate = document.getElementById('id_estimate');
  function recalculate() {
    let sum = 0, count = 0;
    box.querySelectorAll('.diagnostic-row').forEach(row => {
      const value = key => row.querySelector(`[name$="-${key}"]`).value;
      if (!value('name').trim() && !value('catalog_id')) return;
      count++;
      sum += Math.round(Number(value('price') || 0) * 100) * Number(value('quantity') || 0);
    });
    if (count || estimate.readOnly) estimate.value = (sum / 100).toFixed(2);
    estimate.readOnly = count > 0;
    const diagnosis = Number(document.getElementById('id_diagnosis_price').value || 0);
    document.getElementById('estimate-summary').textContent = `Ремонт: ${Number(estimate.value || 0).toFixed(2)} ₽; с диагностикой: ${(Number(estimate.value || 0) + diagnosis).toFixed(2)} ₽`;
  }
  box.addEventListener('input', recalculate);
  document.getElementById('id_diagnosis_price').addEventListener('input', recalculate);
  estimate.addEventListener('input', recalculate);
  function renumber() {
    [...box.children].forEach((row, i) => {
      row.querySelectorAll('[name], [id], label[for]').forEach(el => {
        ['name', 'id', 'for'].forEach(attr => {
          if (el.hasAttribute(attr)) el.setAttribute(attr, el.getAttribute(attr).replace(/items-\d+-/g, `items-${i}-`));
        });
      });
    });
    total.value = box.children.length;
    recalculate();
  }
  function bind(row) {
    const field = name => row.querySelector(`[name$="-${name}"]`);
    const name = field('name'), price = field('price'), kind = field('kind'), id = field('catalog_id');
    const results = row.querySelector('.suggestions');
    let timer, controller;
    const remove = row.querySelector('.remove-row');
    remove.type = 'button';
    remove.onclick = () => { clearTimeout(timer); controller?.abort(); row.remove(); renumber(); status.textContent = ''; };
    function reset() { id.value = ''; picker.value = ''; results.replaceChildren(); clearTimeout(timer); controller?.abort(); }
    const picker = document.createElement('select');
    picker.setAttribute('aria-label', 'Выбрать из справочника');
    const label = document.createElement('label');
    label.textContent = 'Выбрать из справочника'; label.append(picker);
    row.querySelector('legend').after(label);
    function options() {
      picker.replaceChildren(new Option('Ввести вручную или выбрать позицию', ''));
      (catalog[kind.value] || []).forEach(item => picker.add(new Option(`${item.name} - ${item.price} ₽`, item.id)));
      picker.value = id.value;
    }
    picker.addEventListener('change', () => {
      const item = (catalog[kind.value] || []).find(item => String(item.id) === picker.value);
      if (!item) { reset(); return; }
      id.value = item.id; name.value = item.name; price.value = item.price;
      if (!field('quantity').value) field('quantity').value = '1';
      results.replaceChildren(); recalculate();
    });
    options();
    kind.onchange = () => { reset(); options(); recalculate(); };
    price.addEventListener('input', reset);
    name.addEventListener('input', () => {
      reset(); clearTimeout(timer);
      const q = name.value.trim();
      if (q.length < 2) return;
      timer = setTimeout(async () => {
        controller = new AbortController();
        const manual = () => {
          const button = document.createElement('button');
          button.type = 'button'; button.className = 'button secondary';
          button.textContent = `Использовать "${q}" как новую позицию`;
          button.onclick = () => { id.value = ''; name.value = q; results.replaceChildren(); price.focus(); };
          results.append(button);
        };
        try {
          const response = await fetch(`/api/${kind.value === 'work' ? 'works' : 'parts'}/search/?q=${encodeURIComponent(q)}&model_id=${encodeURIComponent(document.getElementById('diagnostics-form').dataset.modelId || '')}`, {signal: controller.signal, cache: 'no-store'});
          if (!response.ok) throw new Error('lookup');
          const data = await response.json();
          if (name.value.trim() !== q) return;
          results.replaceChildren();
          data.results.slice(0, 10).forEach(item => {
            const button = document.createElement('button');
            button.type = 'button'; button.className = 'button secondary'; button.textContent = item.label;
            button.onclick = () => { id.value = item.id; name.value = item.name; price.value = item.price; picker.value = item.id; results.replaceChildren(); recalculate(); };
            results.append(button);
          });
          manual(); status.textContent = '';
        } catch (error) {
          if (error.name !== 'AbortError') { results.replaceChildren(); manual(); status.textContent = 'Поиск недоступен. Можно ввести позицию вручную или повторить поиск.'; }
        }
      }, 250);
    });
  }
  [...box.children].forEach(bind);
  recalculate();
  document.getElementById('add-row').addEventListener('click', event => {
    event.preventDefault();
    if (box.children.length >= 100) { status.textContent = 'Не более 100 позиций.'; return; }
    const template = document.getElementById('diagnostic-empty');
    const fragment = document.createElement('div');
    fragment.innerHTML = template.innerHTML.replace(/__prefix__/g, total.value);
    const row = fragment.firstElementChild; box.append(row); renumber(); bind(row);
    row.querySelector('select').focus();
  });
})();
