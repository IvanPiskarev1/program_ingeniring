(() => {
  const form = document.getElementById('order-form');
  if (!form) return;
  const status = document.getElementById('lookup-status');
  const field = name => document.getElementById(`id_${name}`);
  const fill = data => Object.entries(data).forEach(([key, value]) => {
    const input = field(key);
    if (input) { if (input.type === 'checkbox') input.checked = Boolean(value); else input.value = value ?? ''; }
  });
  const get = async url => {
    let response;
    try { response = await fetch(url, {headers: {'Accept': 'application/json'}, cache: 'no-store'}); }
    catch { throw new Error('Связь с сервером прервана. Используйте кнопку загрузки или повторите поиск.'); }
    if (!response.ok) throw new Error('Не удалось загрузить данные. Используйте кнопку загрузки или повторите поиск.');
    return response.json();
  };
  // Abort old searches and ignore out-of-order responses after a selection.
  function search(input, container, url, select) {
    let timer, revision = 0;
    input.addEventListener('input', () => {
      const current = ++revision;
      clearTimeout(timer); container.replaceChildren();
      if (input.value.trim().length < 2) return;
      timer = setTimeout(async () => {
        try {
          const data = await get(url + encodeURIComponent(input.value.trim()));
          if (current !== revision) return;
          if (!data.results.length) container.textContent = 'Совпадений не найдено.';
          data.results.forEach(item => {
            const button = document.createElement('button');
            button.type = 'button'; button.className = 'button secondary'; button.textContent = item.label;
            button.style.cssText = 'display:block;margin:8px 0;white-space:normal;text-align:left';
            button.addEventListener('click', async () => {
              ++revision; container.replaceChildren();
              try { await select(item); } catch (e) { status.textContent = e.message; }
            });
            container.append(button);
          });
        } catch (e) { if (current === revision) status.textContent = e.message; }
      }, 250);
    });
  }
  if (form.dataset.intake === '1') {
    document.getElementById('client-search-box').hidden = false;
    const client = field('existing_client'), device = field('existing_device');
    let devices = [], generation = 0;
    const catalog = field('catalog_model');
    let models = [];
    const modelsReady = get('/api/device-models/').then(data => { models = data.results; }).catch(e => { status.textContent = e.message; });
    catalog.addEventListener('change', async () => {
      const selected = catalog.value;
      await modelsReady;
      if (catalog.value !== selected) return;
      const model = models.find(m => String(m.id) === catalog.value);
      if (!model) return;
      device.value = '';
      fill({device_type: model.device_type, manufacturer: model.manufacturer, device_model: model.device_model, serial: ''});
      status.textContent = 'Модель выбрана. Введите серийный номер принимаемого устройства.';
    });
    ['device_type', 'manufacturer', 'device_model'].forEach(name => field(name).addEventListener('change', () => { catalog.value = ''; }));
    const clearDevice = () => fill({catalog_model: '', device_type: '', manufacturer: '', device_model: '', serial: '', accessories: ''});
    async function loadClient() {
      const id = client.value, current = ++generation;
      document.getElementById('client-loaded').value = '';
      fill({client_name: '', contact: '', phone: '', email: '', email_notifications: false});
      devices = []; device.replaceChildren(new Option('Новое изделие - заполнить ниже', '')); clearDevice();
      if (!id) return;
      const [info, list] = await Promise.all([get(`/api/clients/${id}/`), get(`/api/clients/${id}/devices/`)]);
      if (current !== generation || client.value !== id) return;
      fill(info); document.getElementById('client-loaded').value = '1';
      devices = list.results; devices.forEach(d => device.add(new Option(d.label, d.id)));
      status.textContent = 'Данные клиента загружены. Выберите изделие или заполните новое.';
    }
    form.addEventListener('submit', event => {
      if (event.submitter?.name === 'load_existing') return;
      if (client.value && !document.getElementById('client-loaded').value) {
        event.preventDefault(); status.textContent = 'Сначала загрузите данные выбранного клиента.';
      }
    });
    client.addEventListener('change', () => {
      if (!client.value) document.getElementById('new-client').click();
      else loadClient().catch(e => { status.textContent = e.message; });
    });
    device.addEventListener('change', () => { clearDevice(); const d = devices.find(d => String(d.id) === device.value); if (d) fill(d); });
    search(document.getElementById('client-query'), document.getElementById('client-results'), '/api/clients/search/?q=', async item => {
      client.value = item.id; await loadClient();
    });
    document.getElementById('new-client').addEventListener('click', () => {
      ++generation; client.value = ''; document.getElementById('client-loaded').value = '';
      fill({kind: 'person', client_name: '', contact: '', phone: '', email: '', email_notifications: false});
      device.replaceChildren(new Option('Новое изделие - заполнить ниже', '')); devices = []; clearDevice();
      document.getElementById('client-query').value = ''; document.getElementById('client-results').replaceChildren();
      status.textContent = 'Заполните данные нового клиента.';
    });
    // Preserve submitted edits after validation. Load only the device lookup map.
    if (client.value) {
      const id = client.value;
      get(`/api/clients/${id}/devices/`).then(data => { if (client.value === id) devices = data.results; }).catch(e => { status.textContent = e.message; });
    }
  }
  if (form.dataset.part === '1' || form.dataset.work === '1') {
    const work = form.dataset.work === '1';
    const choices = JSON.parse(document.getElementById('catalog-choices').textContent);
    field('price_item').addEventListener('change', () => {
      const item = choices.find(item => String(item.id) === field('price_item').value);
      if (!item) return;
      fill(work ? {description: item.name, cost: item.price} : {name: item.name, price: item.price});
      if (!work && !field('quantity').value) field('quantity').value = '1';
      status.textContent = 'Позиция выбрана. Проверьте данные и сохраните.';
    });
    (work ? ['description', 'cost'] : ['name', 'price']).forEach(name => field(name).addEventListener('input', () => { field('price_item').value = ''; }));
  }
  if (form.dataset.part === '1') {
    search(document.getElementById('part-query'), document.getElementById('part-results'), '/api/parts/search/?q=', item => {
      fill({price_item: item.id, name: item.name, price: item.price});
      if (!field('quantity').value) field('quantity').value = '1';
      status.textContent = 'Деталь выбрана. Укажите количество и сохраните.';
    });
    ['name', 'price'].forEach(name => field(name).addEventListener('input', () => { field('price_item').value = ''; }));
  }
})();
