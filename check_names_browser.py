"""Read-only real browser check of renamed database records. No credentials printed."""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
import re
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
from repairs.management.commands.normalize_names import USERS
base = Path(__file__).resolve().parent
url = sys.argv[1].rstrip('/')
assert url.startswith('http://127.0.0.1:')
passwords = {}
for line in (base / 'demo-access.txt').read_text(encoding='utf-8').splitlines():
    match = re.search(r'(demo_\w+) / (\S+)', line)
    if match:
        passwords[match[1]] = match[2]
with sync_playwright() as pw:
    browser = pw.chromium.launch(channel='msedge', headless=True)
    page = browser.new_page(viewport={'width':1440, 'height':1000})
    errors = []
    page.on('pageerror', lambda err: errors.append(str(err)))
    page.on('response', lambda response: errors.append(f'HTTP {response.status}') if response.status >= 400 else None)
    page.goto(url + '/accounts/login/')
    page.locator('input[name="username"]').fill(USERS['demo_reception'][0])
    page.locator('input[name="password"]').fill(passwords['demo_reception'])
    page.get_by_role('button', name='Войти в систему →').click()
    expect(page).to_have_url(re.compile('/dashboard/$'))
    expect(page.get_by_text('Анна Соколова', exact=True)).to_be_visible()
    page.goto(url + '/clients/')
    expect(page.get_by_text('Александр Смирнов', exact=True)).to_be_visible()
    assert not re.search(r'демо|browser qa', page.locator('main').inner_text(), re.I)
    page.goto(url + '/orders/1/')
    expect(page.get_by_text('Александр Смирнов →', exact=True)).to_be_visible()
    assert not re.search(r'демо|browser qa', page.locator('main').inner_text(), re.I)
    assert not errors, errors
    browser.close()
print('PASS: real Edge login with renamed account and unchanged password; clients and order display updated names; no page/HTTP errors.')
