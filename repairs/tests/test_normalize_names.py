from unittest.mock import patch
from tempfile import TemporaryDirectory
from pathlib import Path
from django.test import TestCase, override_settings
from django.core.management import call_command
from django.contrib.auth.models import User, Group
from repairs.models import Client, Device, DeviceType, RepairOrder


class NormalizeNamesTests(TestCase):
    def test_names_keep_credentials_links_and_existing_records(self):
        user = User.objects.create(username='demo_master', password='unchanged-hash')
        group = Group.objects.create(name='Мастер')
        user.groups.add(group)
        customer = Client.objects.create(name='Демо · Клиент Альфа', phone='+70000000000')
        real = Client.objects.create(name='Мой клиент', phone='+70000000001')
        kind = DeviceType.objects.create(name='Ноутбук')
        device = Device.objects.create(kind=kind, manufacturer='Демо', model='Browser QA', serial='DEMO-0001')
        order = RepairOrder.objects.create(client=customer, device=device, master=user, problem='Не включается', accessories='Учебный пример: устройство и кабель')
        token, version = order.token, order.version
        # Django TestCase holds a transaction; isolate only SQLite backup IO.
        with TemporaryDirectory() as folder, override_settings(BASE_DIR=Path(folder)), patch('repairs.management.commands.normalize_names.sqlite3.connect'):
            with patch('repairs.management.commands.normalize_names.connection') as connection:
                connection.vendor = 'sqlite'
                call_command('normalize_names', apply=True)
                call_command('normalize_names', apply=True)
        user.refresh_from_db(); customer.refresh_from_db(); device.refresh_from_db(); order.refresh_from_db(); real.refresh_from_db()
        self.assertEqual(user.username, 'sergey.volkov')
        self.assertEqual(user.password, 'unchanged-hash')
        self.assertTrue(user.groups.filter(pk=group.pk).exists())
        self.assertEqual(customer.name, 'Александр Смирнов')
        self.assertEqual(real.name, 'Мой клиент')
        self.assertEqual((device.manufacturer, device.model, device.serial), ('HP', 'Pavilion 15', ''))
        self.assertEqual((order.client_id, order.master_id, order.device_id), (customer.pk, user.pk, device.pk))
        self.assertEqual((order.token, order.version), (token, version))
        self.assertEqual(order.accessories, 'Устройство и кабель')
