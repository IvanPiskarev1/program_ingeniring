"""Verify print layout using existing records; no order or payment changes."""
import os
import re
import sys
from pathlib import Path

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.utils import timezone
from playwright.sync_api import sync_playwright, expect
from repairs.models import RepairOrder
from repairs.management.commands.normalize_names import USERS

base = Path(__file__).resolve().parent
url = sys.argv[1].rstrip('/')
assert url.startswith('http://127.0.0.1:')
passwords = {}
for line in (base / 'demo-access.txt').read_text(encoding='utf-8').splitlines():
    match = re.search(r'(demo_\w+) / (\S+)', line)
    if match:
        passwords[match[1]] = match[2]
order = RepairOrder.objects.filter(issued_at__isnull=False, payments__isnull=False).first()
assert order is not None, 'Need an existing issued order with payment'
payments = list(order.payments.all())
with sync_playwright() as pw:
    browser = pw.chromium.launch(channel='msedge', headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('response', lambda response: errors.append(f'HTTP {response.status}') if response.status >= 400 else None)
    page.goto(url + '/accounts/login/')
    page.locator('input[name="username"]').fill(USERS['demo_reception'][0])
    page.locator('input[name="password"]').fill(passwords['demo_reception'])
    page.get_by_role('button', name='Войти в систему →').click()
    expect(page).to_have_url(re.compile('/dashboard/$'))
    page.goto(url + f'/orders/{order.pk}/')
    page.get_by_role('link', name='Печать приёма', exact=True).click()
    expect(page.get_by_role('heading', name='Приём изделия', exact=True)).to_be_visible()
    expect(page.locator('.signatures')).to_contain_text('Принял')
    expect(page.locator('.signatures')).to_contain_text('Сдал')
    assert 'Выдал' not in page.locator('.signatures').inner_text()
    page.emulate_media(media='print')
    expect(page.locator('.print-actions')).to_be_hidden()
    page.screenshot(path=str(base / '.local' / 'print-intake-check.png'), full_page=True)
    page.emulate_media(media='screen')
    page.get_by_role('link', name='Вернуться в карточку', exact=True).click()
    page.get_by_role('link', name='Печать выдачи', exact=True).click()
    expect(page.get_by_role('heading', name='Выдача изделия', exact=True)).to_be_visible()
    expect(page.locator('.signatures')).to_contain_text('Выдал')
    expect(page.locator('.signatures')).to_contain_text('Получил')
    expect(page.get_by_role('heading', name='Замечания при получении', exact=True)).to_be_visible()
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile overflow'
    page.screenshot(path=str(base / '.local' / 'print-issue-mobile-check.png'), full_page=True)
    page.set_viewport_size({'width': 1440, 'height': 1000})
    expect(page.get_by_role('heading', name='Оплаты', exact=True)).to_be_visible()
    expect(page.get_by_role('heading', name='Выдача', exact=True)).to_be_visible()
    text = page.locator('article.print-document').inner_text()
    assert 'Дата и время выдачи: ' + timezone.localtime(order.issued_at).strftime('%d.%m.%Y %H:%M') in text
    for payment in payments:
        assert 'Дата и время оплаты: ' + timezone.localtime(payment.created_at).strftime('%d.%m.%Y %H:%M') in text
    page.emulate_media(media='print')
    expect(page.locator('.print-actions')).to_be_hidden()
    page.get_by_role('heading', name='Оплаты', exact=True).scroll_into_view_if_needed()
    page.screenshot(path=str(base / '.local' / 'print-times-check.png'))
    assert not errors, errors
    browser.close()
print('PASS: Edge print page shows stored issue/payment timestamps; print actions hidden; no page/HTTP errors. Orders unchanged.')
