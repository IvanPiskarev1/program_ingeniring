"""Read-only real-browser resource/console check, without credentials or secret URLs."""
import sys
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.launch(channel='msedge', headless=True)
    page = browser.new_page()
    issues = []
    page.on('console', lambda message: issues.append({'type': message.type, 'text': message.text, 'location': message.location}) if message.type == 'error' else None)
    page.on('response', lambda response: issues.append({'status': response.status, 'url': response.url}) if response.status >= 400 else None)
    page.goto(sys.argv[1])
    page.wait_for_timeout(2000)
    print(issues)
    browser.close()
    if issues: raise SystemExit(1)
