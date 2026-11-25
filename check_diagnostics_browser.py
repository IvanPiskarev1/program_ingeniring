"""Browser acceptance without saving diagnoses or changing orders."""
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.conf import settings
from django.test import Client
from repairs.models import RepairOrder, PriceItem, WorkCatalogItem

# A fresh, self-contained server avoids cached templates in old previews.
# It is loopback-only and shuts down when this verification process exits.
import atexit
from threading import Thread
from django.core.wsgi import get_wsgi_application
from django.contrib.staticfiles.handlers import StaticFilesHandler
from preview import create_server
server = create_server(StaticFilesHandler(get_wsgi_application()))
Thread(target=server.serve_forever, daemon=True).start()
atexit.register(server.server_close)
atexit.register(server.shutdown)
url = f'http://127.0.0.1:{server.server_port}'
order = RepairOrder.objects.filter(status='diagnosis', master__is_active=True).select_related('master').first()
assert order, 'Existing diagnosis order required'
from repairs.models import DeviceCatalogItem
model = DeviceCatalogItem.objects.filter(kind=order.device.kind, manufacturer=order.device.manufacturer, model=order.device.model).first()
part = (model.parts.all() if model else PriceItem.objects.filter(kind='part')).filter(is_active=True).exclude(sku='').first()
work = (model.works.all() if model else WorkCatalogItem.objects.all()).filter(is_active=True).first()
assert part and work
before = (order.version, order.parts.count(), order.works.count())

def session_cookie():
    client = Client()
    client.force_login(order.master)
    return client.cookies[settings.SESSION_COOKIE_NAME].value

with ThreadPoolExecutor(max_workers=1) as executor:
    cookie = executor.submit(session_cookie).result()
with sync_playwright() as pw:
    browser = pw.chromium.launch(channel='msedge', headless=True)
    errors = []
    for javascript in (True, False):
        context = browser.new_context(java_script_enabled=javascript, viewport={'width': 1440, 'height': 1000})
        context.add_cookies([{'name': settings.SESSION_COOKIE_NAME, 'value': cookie, 'url': url}])
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('requestfailed', lambda req: errors.append(f'{req.method} {req.url.split("?")[0]}: {req.failure}'))
        page.goto(f'{url}/orders/{order.pk}/diagnostics/')
        expect(page.get_by_role('heading', name='Диагностика', exact=True)).to_be_visible()
        result = page.locator('[name="result"]')
        result.fill('Проверено питание устройства')
        if javascript:
            row = page.locator('.diagnostic-row').first
            row.locator('[name$="-name"]').fill(part.sku)
            row.locator('.suggestions button').filter(has_text=part.name).first.click()
            expect(row.locator('[name$="-price"]')).to_have_value(str(part.price))
            expect(row.locator('[name$="-catalog_id"]')).to_have_value(str(part.pk))
            page.get_by_role('button', name='Добавить позицию', exact=True).click()
            row = page.locator('.diagnostic-row').last
            row.locator('[name$="-kind"]').select_option('work')
            row.locator('[name$="-name"]').fill(work.name[:15])
            row.locator('.suggestions button').filter(has_text=work.name).first.click()
            expect(row.locator('[name$="-price"]')).to_have_value(str(work.price))
            row.locator('[name$="-name"]').fill('Восстановление контактов платы')
            row.locator('.suggestions button').filter(has_text='Использовать').click()
            expect(row.locator('[name$="-catalog_id"]')).to_have_value('')
            row.locator('[name$="-price"]').fill('750')
            page.set_viewport_size({'width': 390, 'height': 844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Horizontal overflow'
            Path('.local/browser').mkdir(parents=True, exist_ok=True)
            page.screenshot(path='.local/browser/diagnostics-mobile.png', full_page=True)
            row.get_by_role('button', name='Удалить строку').click()
            expect(page.locator('.diagnostic-row')).to_have_count(1)
        else:
            page.locator('summary').click()
            page.locator('[name="q"]').fill(part.sku)
            page.get_by_role('button', name='Найти', exact=True).click()
            page.get_by_role('button').filter(has_text=f'Добавить: {part.name}').click()
            expect(page.locator('.diagnostic-row')).to_have_count(2)
            page.locator('.diagnostic-row').last.get_by_role('button', name='Удалить строку').click()
            expect(page.locator('.diagnostic-row')).to_have_count(1)
            expect(page.locator('[name="result"]')).to_have_value('Проверено питание устройства')
            expect(page.locator('[name="items-0-catalog_id"]')).to_have_value('')
        context.close()
    browser.close()
assert not errors, errors
order.refresh_from_db()
assert (order.version, order.parts.count(), order.works.count()) == before
print('PASS: Edge diagnostics; part/work lookup and prices, manual entry, row add/remove, mobile fit; without JavaScript search/add/remove preserves fields. No diagnosis saved; order unchanged. No page/request errors.')
