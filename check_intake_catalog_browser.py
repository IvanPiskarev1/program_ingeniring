"""Read-only browser acceptance; does not submit orders or change clients."""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
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
with sync_playwright() as pw:
    browser = pw.chromium.launch(channel='msedge', headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('requestfailed', lambda req: errors.append(f'{req.method} {req.url.split("?")[0]}: {req.failure}'))
    import os
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()
    from django.contrib.auth.models import User
    from django.test import Client
    from django.conf import settings
    def session_cookie():
        client = Client()
        user = User.objects.filter(is_active=True, groups__name='Приём').first()
        assert user, 'Reception account required'
        client.force_login(user)
        return client.cookies[settings.SESSION_COOKIE_NAME].value
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=1) as executor:
        cookie = executor.submit(session_cookie).result()
    page.context.add_cookies([{'name': settings.SESSION_COOKIE_NAME,
        'value': cookie, 'url': url}])
    page.goto(url + '/orders/new/')
    page.get_by_role('searchbox', name='Поиск по ФИО, телефону или почте').fill('Алексеев')
    page.get_by_role('button', name='Алексеев Андрей · +7 (943) 376-46-55', exact=True).click()
    expect(page.get_by_label('Имя / организация', exact=True)).to_have_value('Алексеев Андрей')
    expect(page.get_by_label('Телефон', exact=True)).to_have_value('+7 (943) 376-46-55')
    select = page.get_by_label('Ранее принятое изделие', exact=True)
    expect(select.locator('option')).not_to_have_count(1)
    select.select_option(index=1)
    expect(page.get_by_label('Производитель', exact=True)).not_to_have_value('')
    expect(page.get_by_label('Модель', exact=True)).not_to_have_value('')
    page.get_by_role('button', name='Новый клиент', exact=True).click()
    expect(page.get_by_label('Имя / организация', exact=True)).to_have_value('')
    expect(select).to_have_value('')
    catalog = page.get_by_label('Модель из справочника (новое изделие)', exact=True)
    assert catalog.locator('option').count() >= 55
    page.get_by_label('Комплектность', exact=True).fill('Кабель клиента')
    catalog.select_option(label='Apple iPhone 12')
    expect(page.get_by_label('Производитель', exact=True)).to_have_value('Apple')
    expect(page.get_by_label('Модель', exact=True)).to_have_value('iPhone 12')
    expect(page.get_by_label('Серийный номер', exact=True)).to_have_value('')
    expect(page.get_by_label('Комплектность', exact=True)).to_have_value('Кабель клиента')
    Path('.local/browser').mkdir(parents=True, exist_ok=True)
    page.screenshot(path='.local/browser/intake-model-catalog.png', full_page=True)
    page.goto(url + '/price/?q=AS-P-00001')
    expect(page.get_by_text('Найдено позиций: 1', exact=True)).to_be_visible()
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Page overflow'
    assert not errors, errors
    browser.close()
    print('PASS: real Edge; client search and selection, editable fields, device autofill, new-client reset, SKU search, mobile layout; no request/page errors. No orders submitted.')
