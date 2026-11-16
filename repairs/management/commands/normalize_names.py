"""Replace placeholder display data, without changing workflow or credentials."""
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from repairs.models import (Client, Device, RepairOrder, Diagnosis, RepairWork,
                            UsedPart, QualityCheck, StatusHistory)

USERS = {
    'demo_reception': ('anna.sokolova', 'Анна', 'Соколова'),
    'demo_master': ('sergey.volkov', 'Сергей', 'Волков'),
    'demo_quality': ('elena.morozova', 'Елена', 'Морозова'),
    'demo_manager': ('andrey.kuznetsov', 'Андрей', 'Кузнецов'),
    'demo_admin': ('pavel.orlov', 'Павел', 'Орлов'),
}
CLIENT_NAMES = [
    'Александр Смирнов', 'Мария Кузнецова', 'Дмитрий Соколов',
    'Ольга Попова', 'Алексей Васильев', 'Наталья Морозова',
    'Михаил Новиков', 'Екатерина Фёдорова', 'Иван Павлов',
    'Татьяна Семёнова', 'Артём Козлов',
]
LAPTOPS = [('HP', 'Pavilion 15'), ('Dell', 'Inspiron 15 3520'),
           ('Lenovo', 'ThinkPad E14'), ('ASUS', 'Zenbook 14'), ('Acer', 'Swift 3')]
MARKER = re.compile(r'демо|demo|учеб|browser qa', re.I)
PREFIX = re.compile(r'^(?:(?:Демо\s*[·:—-]?\s*)|(?:Демонстрационная\s+диагностика:\s*)|(?:Учебн\w*\s+(?:пример|запись|проверка|выдача|контрольная\s+проверка)\s*:\s*)|(?:Учебн\w*\s+))', re.I)


def clean_text(value):
    value = value.replace('Учебный браузерный сценарий: не включается', 'Не включается')
    old = None
    while value != old:
        old = value
        value = PREFIX.sub('', value).strip()
    return value[:1].upper() + value[1:]


class Command(BaseCommand):
    help = 'Переименовать заполнители в базе. Имена вымышленные; пароли и права сохраняются.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Применить с резервной копией SQLite.')

    def handle(self, *args, **options):
        User = get_user_model()
        for old, (login, first, last) in USERS.items():
            if User.objects.filter(username=old).exists() and User.objects.filter(username=login).exists():
                raise CommandError(f'Логин {login} уже занят. Изменения не выполнены.')
        if not options['apply']:
            self.stdout.write('Для применения используйте --apply. Имена вымышленные, не реальные клиентские данные.')
            return
        if connection.vendor != 'sqlite':
            raise CommandError('Резервирование настроено только для SQLite.')
        folder = settings.BASE_DIR / '.local' / 'backups'
        folder.mkdir(parents=True, exist_ok=True)
        backup = folder / f'before_names_{datetime.now():%Y%m%d_%H%M%S_%f}.sqlite3'
        connection.ensure_connection()
        with sqlite3.connect(str(backup)) as target:
            connection.connection.backup(target)
        counts = {'users': 0, 'clients': 0, 'devices': 0, 'texts': 0}
        with transaction.atomic():
            for old, (login, first, last) in USERS.items():
                counts['users'] += User.objects.filter(username=old).update(username=login, first_name=first, last_name=last)
            clients = list(Client.objects.order_by('pk'))
            placeholder_clients = [c for c in clients if MARKER.search(c.name)]
            if len(placeholder_clients) > len(CLIENT_NAMES):
                raise CommandError('Не хватает согласованных замен для клиентов; транзакция отменена.')
            for client, name in zip(placeholder_clients, CLIENT_NAMES):
                client.name = name
                fields = ['name']
                if MARKER.search(client.contact):
                    client.contact = name
                    fields.append('contact')
                client.save(update_fields=fields)
                counts['clients'] += 1
            # Placeholder e-mails must not look like real contact details.
            Client.objects.filter(email__startswith='demo', email__endswith='@example.invalid').update(email='')
            index = 0
            for device in Device.objects.order_by('pk'):
                fields = []
                if MARKER.search(device.manufacturer + ' ' + device.model):
                    device.manufacturer, device.model = LAPTOPS[index % len(LAPTOPS)]
                    index += 1
                    fields.extend(['manufacturer', 'model'])
                if MARKER.search(device.serial):
                    # Unknown serials must not be fabricated.
                    device.serial = ''
                    fields.append('serial')
                if fields:
                    device.save(update_fields=fields)
                    counts['devices'] += 1
            for model, fields in [
                (RepairOrder, ['problem', 'accessories', 'appearance', 'issue_method', 'free_reason']),
                (Diagnosis, ['result', 'required_parts']), (RepairWork, ['description']),
                (UsedPart, ['name']), (QualityCheck, ['comment']), (StatusHistory, ['comment']),
            ]:
                for obj in model.objects.all():
                    changed = []
                    for field in fields:
                        value = getattr(obj, field)
                        cleaned = clean_text(value)
                        if cleaned != value:
                            setattr(obj, field, cleaned)
                            changed.append(field)
                    if changed:
                        obj.save(update_fields=changed)
                        counts['texts'] += 1
        mapping = settings.BASE_DIR / 'account-names.txt'
        mapping.write_text('Новые логины; пароли и роли остались прежними.\n' + '\n'.join(
            f'{old} → {login}: {first} {last}' for old, (login, first, last) in USERS.items()
        ) + '\n', encoding='utf-8')
        self.stdout.write(f'Updated: {counts}. Backup: {Path(backup).relative_to(settings.BASE_DIR)}')
