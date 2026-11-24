# Наполнение базы реалистичными данными сервисного центра.
# Клиенты, изделия, прайс-лист, сотрудники и 250 заказов на разных этапах.
import random
import uuid
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from repairs.models import (Client, Device, DeviceType, Diagnosis, FaultCategory,
                            NotificationTemplate, PriceItem, QualityCheck, RepairOrder,
                            RepairWork, UsedPart, Payment)
from repairs.permissions import ADMIN, MANAGER, MASTER, QUALITY, RECEPTION
from repairs.services.orders import event, execute

FIRST_NAMES = ['Анна', 'Сергей', 'Ирина', 'Дмитрий', 'Ольга', 'Алексей', 'Мария', 'Егор',
    'Наталья', 'Павел', 'Елена', 'Виктор', 'Юлия', 'Роман', 'Ксения', 'Андрей', 'Татьяна',
    'Михаил', 'Светлана', 'Николай', 'Дарья', 'Владимир', 'Полина', 'Артём', 'Оксана']
LAST_NAMES = ['Соколова', 'Волков', 'Морозова', 'Кузнецов', 'Орлова', 'Лебедев', 'Смирнова',
    'Козлов', 'Новикова', 'Фёдоров', 'Михайлова', 'Алексеев', 'Гусева', 'Титов', 'Павлова',
    'Комаров', 'Белова', 'Кириллов', 'Данилова', 'Зайцев']
COMPANIES = ['ООО «ТехноПром»', 'ООО «ГарантСтрой»', 'ИП Ковалёв А.С.', 'ООО «Вектор Плюс»',
    'ООО «РемонтСервис»', 'АО «Прогресс»', 'ООО «СтройМонтаж»', 'ИП Тарасова Е.В.',
    'ООО «ЛогистикПро»', 'ООО «БытСервис»']
STREETS = ['Ленина', 'Гагарина', 'Мира', 'Советская', 'Кирова', 'Пушкина', 'Чапаева',
    'Строителей', 'Победы', 'Садовая']

DEVICES = {
    'Смартфон': [
        ('Samsung', 'Galaxy A54'), ('Samsung', 'Galaxy S22'), ('Apple', 'iPhone 13'),
        ('Apple', 'iPhone 11'), ('Xiaomi', 'Redmi Note 12'), ('Xiaomi', 'Redmi 10'),
        ('Honor', 'Honor 90'), ('Huawei', 'P40 Lite'), ('Realme', 'Realme 10'),
        ('Motorola', 'Edge 30'),
    ],
    'Ноутбук': [
        ('Lenovo', 'IdeaPad 5'), ('Lenovo', 'ThinkPad E15'), ('ASUS', 'VivoBook 15'),
        ('ASUS', 'TUF Gaming F15'), ('HP', 'Pavilion 15'), ('HP', 'ProBook 450'),
        ('Dell', 'Inspiron 15'), ('Acer', 'Aspire 5'), ('MSI', 'Modern 14'),
        ('Huawei', 'MateBook D15'),
    ],
    'Бытовая техника': [
        ('Bosch', 'Serie 4 стиральная машина'), ('LG', 'F2J3 стиральная машина'),
        ('Samsung', 'WW70 стиральная машина'), ('Philips', 'Кофемашина Series 2200'),
        ('De\'Longhi', 'Кофемашина ECAM 22'), ('Bosch', 'Пылесос Serie 6'),
        ('Redmond', 'Мультиварка RK-M171'), ('Scarlett', 'Чайник SC-EK21S66'),
        ('Микс', 'Микроволновая печь MWS-1807'), ('Gorenje', 'Холодильник NRK6191'),
    ],
}

PROBLEMS = {
    'Смартфон': ['Не включается', 'Быстро разряжается', 'Разбит экран', 'Не заряжается', 'Не ловит сеть',
        'Не работает динамик', 'Залипла кнопка питания', 'Не работает камера', 'Перегревается', 'Не видит SIM-карту'],
    'Ноутбук': ['Не включается', 'Самопроизвольно выключается', 'Не работает клавиатура', 'Слабый звук',
        'Перегревается и шумит', 'Не видит жёсткий диск', 'Не заряжается от сети', 'Артефакты на экране',
        'Не работает Wi-Fi', 'Тормозит и перезагружается'],
    'Бытовая техника': ['Не запускается цикл', 'Не греет воду', 'Течёт вода', 'Шумит при работе',
        'Не включается', 'Не отжимает бельё', 'Перегорает предохранитель', 'Плохо крутится двигатель',
        'Не закрывается дверца', 'Ошибка на дисплее'],
}

DIAGNOSIS_RESULTS = {
    'Не включается': 'Диагностика показала неисправность цепи питания. Требуется замена компонентов питания.',
    'Быстро разряжается': 'Ёмкость аккумулятора снизилась до 62%. Рекомендуется замена батареи.',
    'Разбит экран': 'Трещины по всей поверхности дисплея. Требуется замена дисплейного модуля.',
    'Не заряжается': 'Окислен разъём зарядки, контакт нестабилен. Требуется чистка и замена разъёма.',
    'Не ловит сеть': 'Деградация антенного тракта. Требуется диагностика и замена антенного модуля.',
    'Не работает динамик': 'Обрыв шлейфа динамика. Требуется замена шлейфа.',
    'Залипла кнопка питания': 'Механический износ кнопки. Требуется замена кнопочного модуля.',
    'Не работает камера': 'Сбой шлейфа камеры. Требуется переподключение или замена шлейфа.',
    'Перегревается': 'Высохла термопаста, система охлаждения забита пылью. Нужна чистка и замена термопасты.',
    'Не видит SIM-карту': 'Повреждён коннектор SIM-ридера. Требуется замена.',
    'Самопроизвольно выключается': 'Перегрев процессора из-за высохшей термопасты. Нужна чистка и обслуживание.',
    'Не работает клавиатура': 'Часть клавиш не реагирует, повреждена матрица клавиатуры. Требуется замена.',
    'Слабый звук': 'Деградация динамиков. Требуется замена аудиомодуля.',
    'Не видит жёсткий диск': 'Диск выдаёт ошибки SMART. Рекомендуется замена на SSD.',
    'Не заряжается от сети': 'Изношен разъём питания. Требуется замена разъёма.',
    'Артефакты на экране': 'Проблема с видеочипом или шлейфом дисплея. Требуется диагностика платы.',
    'Не работает Wi-Fi': 'Неисправен Wi-Fi модуль. Требуется замена модуля.',
    'Тормозит и перезагружается': 'Деградация накопителя и нехватка памяти. Рекомендуется замена SSD и увеличение ОЗУ.',
    'Не запускается цикл': 'Неисправен модуль управления. Требуется диагностика платы и замена симистора.',
    'Не греет воду': 'Перегорел ТЭН. Требуется замена нагревательного элемента.',
    'Течёт вода': 'Изношена манжета люка. Требуется замена уплотнителя.',
    'Шумит при работе': 'Износ подшипников барабана. Требуется замена подшипникового узла.',
    'Не отжимает бельё': 'Неисправен таходатчик двигателя. Требуется замена датчика.',
    'Перегорает предохранитель': 'Короткое замыкание в цепи. Требуется поиск и устранение неисправности.',
    'Плохо крутится двигатель': 'Износ щёток двигателя. Требуется замена щёток.',
    'Не закрывается дверца': 'Сломан фиксатор замка. Требуется замена блокировки люка.',
    'Ошибка на дисплее': 'Сбой платы управления. Требуется перепрошивка или замена модуля.',
}

WORK_NAMES = ['Замена дисплея', 'Замена аккумулятора', 'Замена разъёма зарядки', 'Чистка системы охлаждения',
    'Замена термопасты', 'Замена клавиатуры', 'Замена шлейфа', 'Замена динамика', 'Ремонт цепи питания',
    'Замена кнопочного модуля', 'Замена антенного модуля', 'Замена камеры', 'Замена SIM-ридера',
    'Замена жёсткого диска на SSD', 'Увеличение оперативной памяти', 'Замена Wi-Fi модуля',
    'Прошивка системы', 'Замена ТЭНа', 'Замена манжеты люка', 'Замена подшипников',
    'Замена щёток двигателя', 'Замена замка люка', 'Ремонт платы управления', 'Чистка от пыли',
    'Диагностика платы', 'Пайка компонентов', 'Замена вентилятора', 'Замена матрицы ноутбука',
    'Восстановление после залития', 'Замена петли ноутбука', 'Чистка динамика', 'Настройка операционной системы',
    'Установка драйверов', 'Восстановление данных', 'Замена уплотнителя', 'Демонтаж и сборка узла',
    'Калибровка датчика', 'Замена фильтра', 'Обслуживание кофемашины', 'Удаление накипи',
    'Замена тена духовки', 'Ремонт дверцы', 'Замена уплотнительного кольца', 'Тестирование после ремонта']

PART_NAMES = ['Дисплейный модуль', 'Аккумулятор', 'Разъём зарядки (USB-C)', 'Разъём зарядки (Lightning)',
    'Кнопочный модуль', 'Шлейф динамика', 'Шлейф камеры', 'Динамик', 'Антенный модуль', 'SIM-ридер',
    'Клавиатура', 'Термопаста', 'Кулер охлаждения', 'SSD-накопитель 480 ГБ', 'Модуль оперативной памяти 8 ГБ',
    'Wi-Fi модуль', 'Матрица 15.6"', 'Шлейф матрицы', 'Разъём питания ноутбука', 'Петля ноутбука',
    'ТЭН 2 кВт', 'Манжета люка', 'Подшипниковый узел', 'Щётки двигателя', 'Замок люка',
    'Таходатчик', 'Симистор платы управления', 'Фильтр насоса', 'Уплотнительное кольцо', 'Виброамортизатор']

CATEGORIES = ['Питание', 'Механическое повреждение', 'Программный сбой', 'Перегрев', 'Износ деталей']


def realistic_phone(rng):
    return f'+7 ({rng.randint(900, 999)}) {rng.randint(100, 999)}-{rng.randint(10, 99)}-{rng.randint(10, 99)}'


def serial(rng, prefix):
    return f'{prefix}{rng.randint(1000000, 9999999)}'


def cat_by_problem(problem):
    mapping = {'Разбит экран': 'Механическое повреждение', 'Перегревается': 'Перегрев',
        'Тормозит и перезагружается': 'Программный сбой', 'Ошибка на дисплее': 'Программный сбой'}
    if problem in mapping:
        return mapping[problem]
    if any(word in problem for word in ['Не включается', 'Не заряжается', 'питания', 'предохранитель']):
        return 'Питание'
    if any(word in problem for word in ['Шумит', 'крутится', 'щётки', 'Не закрывается']):
        return 'Износ деталей'
    return 'Программный сбой'


class Command(BaseCommand):
    help = 'Создать реалистичные данные: сотрудники, клиенты, изделия, прайс-лист и 250 заказов.'
    @transaction.atomic
    def handle(self, *args, **options):
        rng = random.Random(20261124)
        # Сотрудники: фиксированные учётные записи, пароли задаёт администратор отдельно.
        staff = [
            ('andrey.priem', RECEPTION, 'Андрей', 'Приемщик'),
            ('anton.master', MASTER, 'Антон', 'Мастер'),
            ('maxim.master', MASTER, 'Максим', 'Мастер'),
            ('vadim.quality', QUALITY, 'Вадим', 'Контролёр'),
            ('ivan.manager', MANAGER, 'Иван', 'Менеджер'),
        ]
        for username, role, first, last in staff:
            user, created = User.objects.get_or_create(username=username, defaults={'first_name': first, 'last_name': last, 'is_staff': True})
            user.is_staff = True
            if created:
                user.set_password('12341234')
            user.save()
            user.groups.add(Group.objects.get(name=role))
        # Старые демо-пользователи отключаются, а не удаляются: на них есть ссылки из заказов.
        User.objects.filter(username__in=['pavel.orlov', 'demo', 'manager', 'master']).exclude(username='admin').update(is_active=False, is_staff=False)
        admin = User.objects.filter(username='admin').first()
        if not admin:
            admin = User.objects.create_superuser('admin', password='12341234')
        admin.first_name = ''
        admin.last_name = 'Администратор'
        admin.save()
        admin.groups.add(Group.objects.get(name=ADMIN))

        # Типы изделий, категории неисправностей и шаблон уведомления.
        kinds = {name: DeviceType.objects.get_or_create(name=name)[0] for name in DEVICES}
        cats = {name: FaultCategory.objects.get_or_create(name=name)[0] for name in CATEGORIES}
        NotificationTemplate.objects.get_or_create(name='Смена статуса', defaults={'text': '{number}: {status}.'})

        # Прайс-лист: диагностика, 40 работ и 30 деталей.
        PriceItem.objects.get_or_create(kind='diagnosis', name='Диагностика устройства', defaults={'price': Decimal('500.00')})
        for name in WORK_NAMES:
            PriceItem.objects.get_or_create(kind='work', name=name,
                defaults={'price': Decimal(rng.choice([500, 800, 1000, 1200, 1500, 1800, 2000, 2500, 3000, 3500]))})
        for name in PART_NAMES:
            PriceItem.objects.get_or_create(kind='part', name=name,
                defaults={'price': Decimal(rng.choice([300, 450, 600, 900, 1200, 1800, 2500, 3200, 4500, 6000, 8500]))})

        # 50 клиентов.
        if Client.objects.count() < 50:
            used_phones = set(Client.objects.values_list('phone', flat=True))
            while Client.objects.count() < 50:
                if rng.random() < 0.15:
                    name = rng.choice(COMPANIES)
                    contact = f'{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}'
                else:
                    name = f'{rng.choice(LAST_NAMES)} {rng.choice(FIRST_NAMES)}'
                    contact = ''
                phone = realistic_phone(rng)
                if phone in used_phones:
                    continue
                used_phones.add(phone)
                Client.objects.create(kind='company' if contact else 'person', name=name, contact=contact,
                    phone=phone, email='', email_notifications=rng.random() < 0.4)

        # Изделия: по 10 телефонов, ноутбуков и бытовой техники (по одному на строку каталога).
        devices = []
        for kind_name, catalog in DEVICES.items():
            for maker, model in catalog:
                device = Device.objects.filter(manufacturer=maker, model=model, kind=kinds[kind_name]).first()
                if not device:
                    device = Device.objects.create(kind=kinds[kind_name], manufacturer=maker, model=model, serial='')
                devices.append((device, kind_name))

        # 250 заказов: распределение по статусам правдоподобное.
        status_weights = [('issued', 110), ('ready', 20), ('quality', 15), ('repair', 40),
                          ('diagnosis', 30), ('received', 35)]
        plan = []
        for status, count in status_weights:
            plan.extend([status] * count)
        rng.shuffle(plan)
        now = timezone.now()
        masters = list(User.objects.filter(groups__name=MASTER))
        receptionist = User.objects.get(username='andrey.priem')
        quality_user = User.objects.get(username='vadim.quality')
        manager = User.objects.get(username='ivan.manager')
        work_items = list(PriceItem.objects.filter(kind='work'))
        part_items = list(PriceItem.objects.filter(kind='part'))
        diagnosis_item = PriceItem.objects.get(kind='diagnosis')

        created = 0
        clients = list(Client.objects.all())
        for index, target in enumerate(plan):
            if RepairOrder.objects.count() >= 250:
                break
            device, kind_name = rng.choice(devices)
            client = rng.choice(clients)
            problem = rng.choice(PROBLEMS[kind_name])
            created_at = now - timedelta(days=rng.randint(1, 90), hours=rng.randint(0, 9))
            if not device.serial:
                prefix = {'Смартфон': 'SM', 'Ноутбук': 'NB', 'Бытовая техника': 'BT'}[kind_name]
                device.serial = serial(rng, prefix)
                device.save()
            order = RepairOrder.objects.create(client=client, device=device, problem=problem,
                accessories=rng.choice(['Устройство, кабель питания', 'Устройство без аксессуаров', 'Устройство, чехол, кабель', 'Устройство и зарядное устройство']),
                appearance=rng.choice(['Следы эксплуатации, без повреждений', 'Царапины на корпусе', 'Потёртости', 'Следы залития на корпусе', 'Без видимых повреждений']),
                created_at=created_at, request_key=uuid.uuid4())
            order.master = rng.choice(masters) if target != 'received' else None
            if target != 'received':
                order.status = 'diagnosis'
            order.save()
            event(order, receptionist, '', f'Заказ {order.number} принят в сервисный центр.')
            if target == 'received':
                created += 1
                continue
            # Диагностика.
            diag_days = rng.randint(1, 4)
            order.status = 'repair'
            order.due_date = (created_at + timedelta(days=diag_days + rng.randint(2, 7))).date()
            diagnosis_price = diagnosis_item.price
            estimate = Decimal(rng.choice([1000, 1500, 2000, 2500, 3000, 4000, 5000])) + diagnosis_price
            order.estimate = estimate
            order.save()
            Diagnosis.objects.create(order=order, author=rng.choice(masters),
                result=DIAGNOSIS_RESULTS.get(problem, 'Проведена полная диагностика, выявлена неисправность. Требуется ремонт.'),
                category=cats[cat_by_problem(problem)],
                price=diagnosis_price, created_at=created_at + timedelta(days=diag_days))
            event(order, order.master, 'diagnosis', 'Диагностика завершена, заказ передан в ремонт.')
            if target == 'diagnosis':
                created += 1
                continue
            # Работы и детали из прайс-листа.
            for work in rng.sample(work_items, rng.randint(1, 3)):
                RepairWork.objects.create(order=order, author=order.master, description=work.name,
                    minutes=rng.choice([30, 45, 60, 90, 120]), cost=work.price,
                    created_at=created_at + timedelta(days=diag_days, hours=rng.randint(1, 48)))
            for part in rng.sample(part_items, rng.randint(0, 2)):
                UsedPart.objects.create(order=order, name=part.name, quantity=1, price=part.price)
            event(order, order.master, 'repair', 'Работы и детали добавлены в заказ.')
            if target == 'repair':
                created += 1
                continue
            # Контроль качества.
            order.status = 'quality'
            order.save()
            event(order, order.master, 'repair', 'Заказ передан на контроль качества.')
            if target == 'quality':
                created += 1
                continue
            passed = rng.random() < 0.85
            QualityCheck.objects.create(order=order, passed=passed, author=quality_user,
                comment='Проверка пройдена, изделие готово к выдаче.' if passed else 'Выявлен дефект после ремонта, требуется доработка.',
                created_at=created_at + timedelta(days=diag_days + 2))
            if not passed:
                event(order, quality_user, 'to_quality', 'Заказ возвращён в ремонт по результатам контроля.')
                created += 1
                continue
            order.status = 'ready'
            order.save()
            event(order, quality_user, 'quality_ok', 'Контроль пройден, заказ готов к выдаче.')
            if target == 'ready':
                created += 1
                continue
            # Выдача.
            issued_at = created_at + timedelta(days=diag_days + rng.randint(3, 10))
            order.status = 'issued'
            order.issued_at = issued_at
            order.issued_by = manager
            order.save()
            Payment.objects.create(order=order, amount=order.final_total, method='cash', author=manager, request_key=uuid.uuid4(), created_at=issued_at)
            event(order, manager, 'issue', 'Изделие выдано клиенту, оплата принята.')
        self.stdout.write(self.style.SUCCESS(f'Готово: заказов {RepairOrder.objects.count()}, клиентов {Client.objects.count()}, позиций прайс-листа {PriceItem.objects.count()}.'))
