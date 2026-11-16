import io
import sqlite3
from contextlib import closing
import tempfile
import uuid
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook
from repairs.models import Client, Device, DeviceType, Payment, RepairOrder, RepairWork, UsedPart
from repairs.services.reports import report_data
from .test_workflow import WorkflowFixture


class ReportingTests(WorkflowFixture):
    def test_payment_date_not_intake_date(self):
        self.ready()
        RepairOrder.objects.filter(pk=self.order.pk).update(created_at=timezone.now()-timedelta(days=45))
        self.act('payment', {'amount': Decimal('2000'), 'method':'cash', 'request_key':uuid.uuid4()}, 'Приём')
        data = report_data(timezone.localdate(), timezone.localdate())
        self.assertEqual(data['received'], 0)
        self.assertEqual(data['demo_revenue'], Decimal('2000'))
        self.assertEqual(data['real_revenue'], 0)
    def test_export_metrics_and_formula_defense(self):
        self.ready()
        self.act('payment', {'amount':Decimal('2000'), 'method':'cash', 'request_key':uuid.uuid4()}, 'Приём')
        self.device.manufacturer = '=1+1'; self.device.save()
        self.client.force_login(self.users['Руководитель'])
        response = self.client.get(reverse('reports'), {'format':'xlsx'})
        book = load_workbook(io.BytesIO(response.content))
        rows = list(book.active.values)
        self.assertIn(('Учебные оплаты, ₽ (не выручка)', '2000.00', None, None), rows)
        device_row = next(row for row in rows if row[0] == self.order.number)
        self.assertTrue(device_row[1].startswith("'="))
        response = self.client.get(reverse('reports'), {'format':'csv'})
        self.assertIn("'=1+1", response.content.decode('utf-8-sig'))
        self.assertContains(self.client.get(reverse('reports'), {'start':'2026-12-01','end':'2026-01-01'}), 'Начало периода')
    def test_database_constraints_and_bad_input(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            UsedPart.objects.create(order=self.order, name='Bad', quantity=0, price=0)
        self.client.force_login(self.users['Приём'])
        response = self.client.post(reverse('intake'), {'request_key':uuid.uuid4(), 'kind':'person', 'client_name':'Test','phone':'bad','device_type':self.kind.pk,'manufacturer':'Test','device_model':'Test','problem':'Test'})
        self.assertContains(response, 'Введите телефон')
        self.assertEqual(RepairOrder.objects.count(), 1)
    def test_admin_cannot_escalate_privileges(self):
        call_command('setup_roles', stdout=io.StringIO())
        admin = self.users['Администратор']; admin.is_staff=True; admin.save()
        self.client.force_login(admin)
        target = self.users['Мастер']
        response = self.client.post(f'/admin/auth/user/{target.pk}/change/', {'username':target.username,'first_name':'Test','last_name':'Test','email':'','is_active':'on','is_superuser':'on','is_staff':'on','groups':[Group.objects.get(name='Администратор').pk]})
        self.assertEqual(response.status_code, 200)
        target.refresh_from_db()
        self.assertFalse(target.is_superuser)
        self.assertFalse(target.is_staff)
        self.assertFalse(target.groups.filter(name='Администратор').exists())
        self.assertEqual(self.client.get('/admin/auth/group/').status_code,403)
    def test_all_action_forms_render_and_csrf(self):
        root = User.objects.create_superuser('forms-root')
        self.client.force_login(root)
        self.assertEqual(self.client.get(reverse('order_action',args=[self.order.pk,'assign'])).status_code,200)
        self.ready()
        for action in ('payment','issue'):
            self.assertEqual(self.client.get(reverse('order_action',args=[self.order.pk,action])).status_code,200)
        from django.test import Client as Browser
        browser = Browser(enforce_csrf_checks=True); browser.force_login(root)
        self.assertEqual(browser.post(reverse('order_action',args=[self.order.pk,'issue']), {}).status_code,403)


class BackupTests(TestCase):
    def test_backup_restores_consistent_database(self):
        # Test the real sqlite backup implementation against a separate file DB.
        from django.test import override_settings
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp)/'source.sqlite3'
            with closing(sqlite3.connect(source)) as connection:
                connection.execute('create table repairs_test (number text, status text)')
                connection.execute("insert into repairs_test values ('АС-000001', 'repair')")
                connection.commit()
            databases = {'default': {'ENGINE':'django.db.backends.sqlite3','NAME':str(source)}}
            with override_settings(DATABASES=databases):
                call_command('backup_database', output=str(Path(temp)/'copies'), stdout=io.StringIO())
            backup = next((Path(temp)/'copies').glob('*.sqlite3'))
            with closing(sqlite3.connect(backup)) as restored:
                self.assertEqual(restored.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
                self.assertEqual(restored.execute('select * from repairs_test').fetchone(), ('АС-000001','repair'))
