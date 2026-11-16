import secrets
from datetime import timedelta
from decimal import Decimal
from django.conf import settings
from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from repairs.models import Client, Device, DeviceType, FaultCategory, NotificationTemplate, RepairOrder
from repairs.services.orders import event, execute


class Command(BaseCommand):
    help = 'Создать явно демонстрационные данные. Пароли случайные, сохраняются только в локальном demo-access.txt.'
    @transaction.atomic
    def handle(self, *args, **options):
        call_command('setup_roles', stdout=self.stdout)
        access = []
        specs = [('demo_reception', 'Приём', 'Демо', 'Приём'), ('demo_master', 'Мастер', 'Демо', 'Мастер'),
                 ('demo_quality', 'Контроль качества', 'Демо', 'Контролёр'), ('demo_manager', 'Руководитель', 'Демо', 'Руководитель'),
                 ('demo_admin', 'Администратор', 'Демо', 'Администратор')]
        users = {}
        for login, role, first, last in specs:
            user, created = User.objects.get_or_create(username=login, defaults={'first_name': first, 'last_name': last, 'is_staff': role == 'Администратор'})
            if created:
                password = secrets.token_urlsafe(18)
                user.set_password(password)
                user.save()
                access.append(f'{role}: {login} / {password}')
            user.groups.add(Group.objects.get(name=role))
            users[role] = user
        if access:
            path = settings.BASE_DIR / 'demo-access.txt'
            with path.open('a', encoding='utf-8') as stream:
                stream.write('ЛОКАЛЬНЫЕ ДЕМО-УЧЁТНЫЕ ЗАПИСИ. Не публиковать.\n' + '\n'.join(access) + '\n')
            self.stdout.write('Пароли новых демо-пользователей сохранены в service_center/demo-access.txt (не выводятся в журнал).')
        laptop, _ = DeviceType.objects.get_or_create(name='Ноутбук')
        phone, _ = DeviceType.objects.get_or_create(name='Смартфон')
        appliance, _ = DeviceType.objects.get_or_create(name='Бытовая техника')
        for name in ('Не включается', 'Перегрев', 'Механическое повреждение', 'Программный сбой'):
            FaultCategory.objects.get_or_create(name=name)
        category = FaultCategory.objects.get(name='Не включается')
        NotificationTemplate.objects.get_or_create(name='Смена статуса', defaults={'text': '{number}: {status}. Учебное уведомление.'})
        if RepairOrder.objects.exists():
            self.stdout.write('Заказы уже существуют — демонстрационные заказы повторно не добавлены.')
            return
        examples = [
            ('Демо · Клиент Альфа', laptop, 'Lenovo', 'IdeaPad 5', 'Не включается после отключения питания.', 'received'),
            ('Демо · Клиент Бета', phone, 'Samsung', 'Galaxy A54', 'Не заряжается через USB.', 'diagnosis'),
            ('Демо · Учебная мастерская', laptop, 'ASUS', 'VivoBook 15', 'Самопроизвольно выключается.', 'repair'),
            ('Демо · Клиент Гамма', appliance, 'Bosch', 'Serie 4', 'Не запускается цикл работы.', 'quality'),
            ('Демо · Клиент Дельта', laptop, 'Acer', 'Aspire 5', 'Не запускается операционная система.', 'ready'),
            ('Демо · Клиент Эпсилон', phone, 'Xiaomi', 'Redmi Note 12', 'Не работает кнопка питания.', 'issued'),
        ]
        for index, (name, kind, maker, model, problem, target) in enumerate(examples):
            client = Client.objects.create(name=name, phone='+7 (000) 000-00-00', email=f'demo{index}@example.invalid')
            device = Device.objects.create(kind=kind, manufacturer=maker, model=model, serial=f'DEMO-{index + 1:04d}')
            order = RepairOrder.objects.create(client=client, device=device, problem=problem, accessories='Учебный пример: устройство и кабель', appearance='Учебный пример: следы эксплуатации', created_at=timezone.now()-timedelta(days=index+1))
            event(order, users['Приём'])
            def act(action, data, role='Мастер'):
                nonlocal order
                order = execute(order.pk, users[role], action, data, order.version)
            act('assign', {'master': users['Мастер']}, 'Руководитель')
            if target == 'received': continue
            act('start', {})
            if target == 'diagnosis': continue
            act('diagnosis', {'result': 'Демонстрационная диагностика: обнаружена неисправность цепи питания.', 'category': category, 'required_parts': 'Учебная запись: разъём питания', 'estimate': Decimal('2500'), 'due_date': timezone.localdate()+timedelta(days=2-index)})
            if target == 'repair': continue
            act('work', {'description': 'Демо · восстановление цепи питания', 'minutes': 60, 'cost': Decimal('1500')})
            act('part', {'name': 'Демо · разъём питания', 'quantity': 1, 'price': Decimal('500')})
            act('to_quality', {})
            if target == 'quality': continue
            act('quality', {'passed': True, 'comment': 'Учебная проверка: функциональный тест пройден.'}, 'Контроль качества')
            if target == 'ready': continue
            import uuid
            act('payment', {'amount': Decimal('2000'), 'method': 'cash', 'request_key': uuid.uuid4()}, 'Приём')
            act('issue', {'issue_method': 'Учебная выдача клиенту', 'free_reason': ''}, 'Приём')
        call_command('send_notifications', stdout=self.stdout)
        self.stdout.write(self.style.SUCCESS('Созданы 6 демонстрационных заказов. Все имена, контакты и суммы — учебные.'))
