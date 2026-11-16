(() => {
  const theme = document.querySelector('#theme');
  try { if (localStorage.getItem('asui-theme') === 'dark') document.body.dataset.theme = 'dark'; } catch (_) {}
  theme?.addEventListener('click', () => {
    const next = document.body.dataset.theme === 'dark' ? 'light' : 'dark';
    document.body.dataset.theme = next;
    try { localStorage.setItem('asui-theme', next); } catch (_) {}
  });
  document.querySelector('#print-document')?.addEventListener('click', () => window.print());
  document.querySelectorAll('form[method="post"]').forEach(form => form.addEventListener('submit', () => {
    form.querySelectorAll('button[type="submit"]').forEach(button => { button.disabled = true; button.setAttribute('aria-busy', 'true'); });
  }));
  window.addEventListener('pageshow', () => document.querySelectorAll('button[aria-busy]').forEach(button => { button.disabled = false; button.removeAttribute('aria-busy'); }));
})();
