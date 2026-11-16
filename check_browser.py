"""Real Edge/Playwright acceptance against an already running loopback server.
Only synthetic demonstration records are created; credentials are never printed.
"""
import re
import sys
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, expect

BASE = Path(__file__).resolve().parent
url = sys.argv[1].rstrip('/')
if urlparse(url).hostname not in ('localhost', '127.0.0.1'):
    raise SystemExit('Loopback URL required')
access = {}
for line in (BASE / 'demo-access.txt').read_text(encoding='utf-8').splitlines():
    match = re.search(r'(demo_\w+) / (\S+)', line)
    if match:
        access[match[1]] = match[2]
artifacts = BASE / '.local' / 'browser'
artifacts.mkdir(parents=True, exist_ok=True)

with sync_playwright() as pw:
    browser = pw.chromium.launch(channel='msedge', headless=True)
    context = browser.new_context(viewport={'width':1440,'height':1000})
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)
    page.on('response', lambda response: errors.append(f'HTTP {response.status}') if response.status >= 400 else None)

    def fit():
        page.wait_for_function('Array.from(document.images).every(i => i.complete)', timeout=10000)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Horizontal page overflow'
        assert not page.locator('img').evaluate_all('(images) => images.some(i => !i.complete || i.naturalWidth === 0)'), 'Broken image'

    def login(role):
        if page.get_by_role('button', name='Выйти', exact=True).count():
            page.get_by_role('button', name='Выйти', exact=True).click()
        page.goto(url + '/accounts/login/')
        page.locator('input[name="username"]').fill('demo_' + role)
        page.locator('input[name="password"]').fill(access['demo_' + role])
        page.get_by_role('button', name='Войти в систему →').click()
        expect(page).to_have_url(re.compile('/dashboard/$'))
        expect(page.get_by_role('heading', name=re.compile('Всё о ремонтах'))).to_be_visible()

    def field(label, value):
        page.get_by_label(re.compile(r'^' + re.escape(label) + r'\s*\*?$')).fill(str(value))

    def action(name):
        page.get_by_role('link', name=name, exact=True).click()

    def submit(name):
        page.get_by_role('button', name=name, exact=True).click()
        expect(page.get_by_text('Изменения сохранены.', exact=True)).to_be_visible()

    page.goto(url)
    expect(page.get_by_role('heading', name='Ремонт с понятной историей.')).to_be_visible()
    fit()
    page.screenshot(path=str(artifacts/'home-desktop.png'), full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    fit()
    page.get_by_role('link', name='Проверить ремонт →').click()
    field('Номер заказа','АС-000001')
    field('Секретный код доступа','wrong-code')
    page.get_by_role('button',name='Показать статус →').click()
    expect(page.get_by_text('Номер или код доступа не совпали. Проверьте заказ-наряд.',exact=True)).to_be_visible()
    fit()
    page.screenshot(path=str(artifacts/'track-mobile.png'),full_page=True)
    page.set_viewport_size({'width':1440,'height':1000})
    login('reception')
    page.screenshot(path=str(artifacts/'dashboard-desktop.png'),full_page=True)
    action('+ Принять устройство')
    field('Имя / организация','Демо · Браузерная проверка')
    field('Телефон','+7 (000) 000-00-00')
    page.get_by_label('Тип техники',exact=True).select_option(label='Ноутбук')
    field('Производитель','Демо')
    field('Модель','Browser QA')
    field('Серийный номер','DEMO-BROWSER-QA')
    field('Заявленная неисправность','Учебная браузерная проверка: не включается')
    page.get_by_role('button',name='Принять устройство',exact=True).click()
    expect(page.get_by_role('heading',name=re.compile('АС-'))).to_be_visible()
    order_path = urlparse(page.url).path
    number = page.get_by_role('heading',level=1).inner_text()
    token = page.locator('code.break').inner_text()
    fit()
    page.get_by_role('link',name='Заказ-наряд ↗').click()
    expect(page.get_by_role('heading', name='Заказ-наряд '+number)).to_be_visible()
    expect(page.get_by_role('img',name='QR-код клиентского статуса')).to_be_visible()
    page.wait_for_load_state('networkidle')
    fit()
    page.emulate_media(media='print')
    assert page.locator('.header').evaluate('(el) => getComputedStyle(el).display') == 'none'
    page.pdf(path=str(artifacts/'order-print.pdf'), format='A4',print_background=True)
    page.emulate_media(media='screen')
    page.goto(url+order_path)
    login('manager')
    page.goto(url+order_path)
    action('Назначить мастера')
    page.get_by_label(re.compile(r'^Мастер\s*\*?$')).select_option(label='demo_master')
    submit('Назначить мастера')
    login('master')
    page.goto(url+order_path)
    action('Начать диагностику'); submit('Начать диагностику')
    action('Сохранить диагностику и начать ремонт')
    field('Результаты диагностики','Учебная проверка цепи питания')
    page.get_by_label(re.compile(r'^Категория\s*\*?$')).select_option(label='Не включается')
    field('Предварительная стоимость, ₽','2000')
    field('Плановая дата','2026-12-01')
    submit('Диагностика')
    action('Добавить работу')
    field('Выполненная работа','Учебное восстановление питания')
    field('Трудозатраты, мин','30');field('Стоимость работы, ₽','1500')
    submit('Добавить работу')
    action('Добавить деталь')
    field('Деталь','Учебный разъём');field('Количество','2');field('Цена за единицу, ₽','250')
    submit('Добавить деталь')
    action('Передать на контроль');submit('Передать на контроль')
    login('quality');page.goto(url+order_path)
    action('Провести контроль качества')
    page.get_by_label(re.compile(r'^Результат\s*\*?$')).select_option('no')
    field('Comment','Учебная проверка: повторить тест нагрузки')
    submit('Контроль качества')
    expect(page).to_have_url(url+'/orders/')
    login('master');page.goto(url+order_path)
    action('Добавить работу')
    field('Выполненная работа','Учебная доработка');field('Трудозатраты, мин','10');field('Стоимость работы, ₽','0')
    submit('Добавить работу')
    action('Передать на контроль');submit('Передать на контроль')
    login('quality');page.goto(url+order_path)
    action('Провести контроль качества')
    page.get_by_label(re.compile(r'^Результат\s*\*?$')).select_option('yes')
    field('Comment','Учебный функциональный тест пройден')
    submit('Контроль качества')
    login('reception');page.goto(url+order_path)
    action('Зарегистрировать оплату')
    field('Сумма оплаты, ₽','2000')
    page.get_by_label(re.compile(r'^Способ расчёта\s*\*?$')).select_option('cash')
    page.get_by_role('button',name='Зарегистрировать оплату',exact=True).click()
    expect(page.get_by_text('Запись об оплате сохранена.',exact=True)).to_be_visible()
    action('Выдать устройство');submit('Выдача устройства')
    expect(page.locator('.head-actions .status')).to_have_text('Выдано')
    page.set_viewport_size({'width':390,'height':844});fit()
    action('Заказ-наряд ↗');fit()
    page.goto(url+order_path)
    page.get_by_role('button',name='Выйти',exact=True).click()
    page.goto(url+'/track/')
    field('Номер заказа',number);field('Секретный код доступа',token)
    page.get_by_role('button',name='Показать статус →').click()
    expect(page.locator('#public-status')).to_have_text('Выдано')
    expect(page.locator('#public-cost')).to_have_text('2000.00 ₽')
    expect(page.locator('#refresh-message')).to_contain_text('Обновлено')
    fit()
    page.get_by_role('button',name='Переключить цветовую тему').click()
    expect(page.locator('body')).to_have_attribute('data-theme','dark')
    fit()
    page.screenshot(path=str(artifacts/'status-mobile-dark.png'),full_page=True)
    page.set_viewport_size({'width':1440,'height':1000})
    login('manager')
    page.get_by_role('link',name='Отчёты',exact=True).click()
    expect(page.get_by_role('heading',name='Результаты периода')).to_be_visible()
    with page.expect_download() as download:
        page.get_by_role('link',name='Скачать XLSX').click()
    assert download.value.suggested_filename.endswith('.xlsx')
    fit()
    page.screenshot(path=str(artifacts/'reports-desktop.png'),full_page=True)
    context.close();browser.close()
    assert not errors, errors
    print('PASS: real Edge browser; desktop/mobile; intake, all five workflow stages, QC rework, payment/issue, QR image, print PDF, public tracking/polling, theme, XLSX; no console/page/HTTP errors.')
    print(f'Synthetic order: {number}. Screenshots/PDF stored privately in .local/browser.')
