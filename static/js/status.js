(() => {
  const root = document.querySelector('[data-status-url]');
  if (!root) return;
  const message = document.querySelector('#refresh-message');
  async function refresh() {
    if (document.hidden) return;
    try {
      const response = await fetch(root.dataset.statusUrl, {cache: 'no-store', credentials: 'same-origin'});
      if (!response.ok) throw new Error('status');
      const data = await response.json();
      document.querySelector('#public-status').textContent = data.status_label;
      document.querySelector('#public-date').textContent = data.due_date || 'После диагностики';
      const amount = data.total ?? data.estimate;
      document.querySelector('#public-cost').textContent = amount === null ? 'После диагностики' : `${amount} ₽`;
      const list = document.querySelector('#public-history');
      list.replaceChildren(...data.history.map(item => {
        const li = document.createElement('li');
        const title = document.createElement('strong'); title.textContent = item.label;
        const date = document.createElement('small'); date.textContent = new Date(item.at).toLocaleString('ru-RU');
        li.append(title, date); return li;
      }));
      message.textContent = `Обновлено в ${new Date().toLocaleTimeString('ru-RU')}. Следующая проверка через 45 секунд.`;
    } catch (_) { message.textContent = 'Не удалось обновить статус. Показаны последние данные; повторим через 45 секунд.'; }
  }
  refresh();
  setInterval(refresh, 45000);
})();
