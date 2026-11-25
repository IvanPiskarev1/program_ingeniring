"""Read-only browser regression for master catalog selection and totals."""
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Thread
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.test import Client
from django.conf import settings
from django.core.wsgi import get_wsgi_application
from django.contrib.staticfiles.handlers import StaticFilesHandler
from playwright.sync_api import sync_playwright, expect
from repairs.models import RepairOrder, DeviceCatalogItem
from preview import create_server

server = create_server(StaticFilesHandler(get_wsgi_application()))
Thread(target=server.serve_forever, daemon=True).start()
url = f'http://127.0.0.1:{server.server_port}'
repair = RepairOrder.objects.filter(status='repair', master__is_active=True).first()
diag = RepairOrder.objects.filter(status='diagnosis', master__is_active=True).first()
assert repair and diag
before = [(o.pk, o.version, o.parts.count(), o.works.count()) for o in (repair, diag)]
def cookie(user):
    client = Client()
    client.force_login(user)
    return client.cookies[settings.SESSION_COOKIE_NAME].value
try:
    with ThreadPoolExecutor(max_workers=1) as pool:
        repair_cookie = pool.submit(cookie, repair.master).result()
        diag_cookie = pool.submit(cookie, diag.master).result()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='msedge', headless=True)
        errors = []
        context = browser.new_context(viewport={'width': 1440, 'height': 1000})
        context.add_cookies([{'name': settings.SESSION_COOKIE_NAME, 'value': repair_cookie, 'url': url}])
        page = context.new_page()
        page.on('pageerror', lambda e: errors.append(str(e)))
        for action, name, price in [('work', 'description', 'cost'), ('part', 'name', 'price')]:
            page.goto(f'{url}/orders/{repair.pk}/action/{action}/')
            data = page.locator('#catalog-choices').text_content()
            import json
            item = json.loads(data)[0]
            page.locator('#id_price_item').select_option(str(item['id']))
            expect(page.locator('#id_' + name)).to_have_value(item['name'])
            expect(page.locator('#id_' + price)).to_have_value(item['price'])
            page.locator('#id_' + name).fill('Ручная позиция мастера')
            expect(page.locator('#id_price_item')).to_have_value('')
            page.set_viewport_size({'width': 390, 'height': 844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        context.add_cookies([{'name': settings.SESSION_COOKIE_NAME, 'value': diag_cookie, 'url': url}])
        page.goto(f'{url}/orders/{diag.pk}/diagnostics/')
        data = json.loads(page.locator('#diagnostic-catalog').text_content())
        part, work = data['part'][0], data['work'][0]
        first = page.locator('.diagnostic-row').first
        first.get_by_label('Выбрать из справочника', exact=True).select_option(str(part['id']))
        first.locator('[name$="-quantity"]').fill('2')
        expect(page.locator('#id_estimate')).to_have_value(f"{float(part['price']) * 2:.2f}")
        page.get_by_role('button', name='Добавить позицию', exact=True).click()
        last = page.locator('.diagnostic-row').last
        last.locator('[name$="-kind"]').select_option('work')
        last.get_by_label('Выбрать из справочника', exact=True).select_option(str(work['id']))
        expected = float(part['price']) * 2 + float(work['price'])
        expect(page.locator('#id_estimate')).to_have_value(f'{expected:.2f}')
        page.locator('#id_diagnosis_price').fill('0')
        expect(page.locator('#estimate-summary')).to_contain_text(f'с диагностикой: {expected:.2f}')
        last.get_by_role('button', name='Удалить строку').click()
        expect(page.locator('#id_estimate')).to_have_value(f"{float(part['price']) * 2:.2f}")
        first.get_by_role('button', name='Удалить строку').click()
        expect(page.locator('#id_estimate')).to_have_value('0.00')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.screenshot(path='.local/browser/master-catalog-mobile.png', full_page=True)
        assert not errors, errors
        browser.close()
    for pk, version, parts, works in before:
        order = RepairOrder.objects.get(pk=pk)
        assert (order.version, order.parts.count(), order.works.count()) == (version, parts, works)
    print('PASS: Edge master work/part dropdowns autofill, manual reset; diagnosis dropdowns, quantities, sum, zero diagnosis, removal, mobile fit. No orders saved; no page errors.')
finally:
    server.shutdown()
    server.server_close()
