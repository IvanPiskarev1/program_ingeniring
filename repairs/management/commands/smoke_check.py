import io
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from django.conf import settings
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.test import Client
from repairs.models import RepairOrder


class Command(BaseCommand):
    help = 'Неизменяющая проверка страниц на существующей БД и восстановления её копии. Не заменяет браузер.'
    def handle(self, *args, **options):
        checked = 0
        for role in ('Приём', 'Мастер', 'Контроль качества', 'Руководитель', 'Администратор'):
            user = User.objects.filter(groups__name=role, is_active=True).order_by('pk').first()
            if not user: raise CommandError(f'Нет активного сотрудника роли: {role}')
            username = user.username
            client = Client(HTTP_HOST='localhost')
            client.force_login(user)
            paths = ['/dashboard/','/orders/','/api/orders/']
            if role in ('Приём', 'Руководитель', 'Администратор'): paths += ['/clients/']
            if role in ('Приём', 'Мастер'): paths += ['/price/']
            if role == 'Руководитель': paths += ['/masters/','/reports/','/reports/?format=csv','/reports/?format=xlsx']
            if role == 'Администратор': paths += ['/admin/']
            for path in paths:
                result = client.get(path)
                if result.status_code != 200: raise CommandError(f'{username} {path}: {result.status_code}')
                checked += 1
            client.logout()
        client = Client(HTTP_HOST='localhost')
        for path in ('/','/track/','/accounts/login/'):
            if client.get(path).status_code != 200: raise CommandError(path)
            checked += 1
        order = RepairOrder.objects.first()
        if order:
            for path in (f'/track/{order.token}/',f'/api/public/status/{order.token}/'):
                if client.get(path).status_code != 200: raise CommandError('Public order check failed')
                checked += 1
        expected_orders = RepairOrder.objects.count()
        expected_history = sum(o.history.count() for o in RepairOrder.objects.all())
        with tempfile.TemporaryDirectory(dir=settings.BASE_DIR) as folder:
            call_command('backup_database',output=folder,stdout=io.StringIO())
            backup = next(Path(folder).glob('*.sqlite3'))
            with closing(sqlite3.connect(backup)) as restored:
                if restored.execute('select count(*) from repairs_repairorder').fetchone()[0] != expected_orders:
                    raise CommandError('Order backup mismatch')
                if restored.execute('select count(*) from repairs_statushistory').fetchone()[0] != expected_history:
                    raise CommandError('History backup mismatch')
        self.stdout.write(self.style.SUCCESS(f'PASS: {checked} page/API responses; backup restored: {expected_orders} orders, {expected_history} history events. Browser/network NOT checked.'))
