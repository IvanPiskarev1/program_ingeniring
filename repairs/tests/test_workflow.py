import uuid
from decimal import Decimal
from datetime import timedelta
from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from repairs.models import Client, Device, DeviceType, EstimateRevision, FaultCategory, Payment, RepairOrder, RepairWork
from repairs.services.orders import Conflict, event, execute


class WorkflowFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.users = {}
        for role in ('Приём', 'Мастер', 'Контроль качества', 'Руководитель', 'Администратор'):
            group = Group.objects.create(name=role)
            user = User.objects.create_user(username=f'u{len(cls.users)}', password='OnlyForUnitTests_928')
            user.groups.add(group)
            cls.users[role] = user
        cls.kind = DeviceType.objects.create(name='Ноутбук')
        cls.category = FaultCategory.objects.create(name='Питание')
        cls.customer = Client.objects.create(name='Тест · Клиент', phone='+70000000000')
        cls.device = Device.objects.create(kind=cls.kind, manufacturer='Test', model='Notebook', serial='S1')
    def setUp(self):
        self.order = RepairOrder.objects.create(client=self.customer, device=self.device, problem='Не включается')
        event(self.order, self.users['Приём'])
    def act(self, action, data=None, role='Мастер'):
        self.order.refresh_from_db()
        self.order = execute(self.order.pk, self.users[role], action, data or {}, self.order.version)
        return self.order
    def repair(self):
        self.act('assign', {'master': self.users['Мастер']}, 'Руководитель')
        self.act('start')
        self.act('diagnosis', {'result': 'Неисправна цепь питания', 'category': self.category, 'required_parts': '', 'estimate': Decimal('2000'), 'due_date': timezone.localdate()+timedelta(days=2)})
        self.act('work', {'description': 'Восстановление цепи', 'minutes': 45, 'cost': Decimal('1500')})
        self.act('part', {'name': 'Разъём', 'quantity': 2, 'price': Decimal('250')})
    def ready(self):
        self.repair()
        self.act('to_quality')
        self.act('quality', {'passed': True, 'comment': 'Тест пройден'}, 'Контроль качества')


class WorkflowTests(WorkflowFixture):
    def test_full_cycle_and_rework(self):
        self.repair()
        self.act('to_quality')
        self.act('quality', {'passed': False, 'comment': 'Повторно проверить контакт'}, 'Контроль качества')
        with self.assertRaises(ValidationError): self.act('to_quality')
        self.act('work', {'description': 'Доработка контакта', 'minutes': 15, 'cost': Decimal('0')})
        self.act('to_quality')
        self.act('quality', {'passed': True, 'comment': 'Повторный тест пройден'}, 'Контроль качества')
        self.assertEqual(self.order.final_total, Decimal('2500'))
        self.assertEqual(self.order.estimate_revisions.count(), 4)
        self.assertFalse(self.order.estimate_overrun)
        with self.assertRaises(ValidationError): self.act('issue', {'free_reason': '', 'issue_method': 'Лично'}, 'Приём')
        self.act('payment', {'amount': Decimal('2500'), 'method': 'cash', 'request_key': uuid.uuid4()}, 'Приём')
        self.act('issue', {'free_reason': '', 'issue_method': 'Лично'}, 'Приём')
        self.assertEqual(self.order.status, 'issued')
        self.assertEqual(self.order.checks.count(), 2)
        self.assertEqual(self.order.history.count(), 8)
        self.assertEqual(self.order.history.filter(notification__isnull=False).count(), 8)
        self.assertIsNotNone(self.order.issued_at)
    def test_estimate_can_be_approved_only_at_current_total_or_higher(self):
        self.repair()
        self.client.force_login(self.users['Приём'])
        response = self.client.post(reverse('order_action', args=[self.order.pk, 'approve_estimate']), {'amount': '2400', 'note': 'Согласовано по телефону', 'version': self.order.version})
        self.assertEqual(response.status_code, 403)
        for role in ('Приём', 'Руководитель', 'Администратор'):
            self.client.force_login(self.users[role])
            response = self.client.get(reverse('order_detail', args=[self.order.pk]))
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, 'Зафиксировать согласование цены')
            self.assertNotContains(response, '/action/approve_estimate/')
            self.assertContains(response, 'История сметы')
            response = self.client.get(reverse('order_action', args=[self.order.pk, 'approve_estimate']))
            self.assertEqual(response.status_code, 403)
        self.order.refresh_from_db()
        self.assertIsNone(self.order.approved_estimate)
        self.order = execute(self.order.pk, self.users['Приём'], 'approve_estimate', {'amount': Decimal('2600'), 'note': 'Клиент согласовал'}, self.order.version)
        self.assertEqual(self.order.approved_estimate, Decimal('2600'))
        self.assertEqual(self.order.estimate_approved_by, self.users['Приём'])

    def test_stale_work_is_rejected_without_duplicate(self):
        self.repair()
        version = self.order.version
        data = {'description': 'Одна операция', 'minutes': 1, 'cost': Decimal('100')}
        execute(self.order.pk, self.users['Мастер'], 'work', data, version)
        with self.assertRaises(Conflict): execute(self.order.pk, self.users['Мастер'], 'work', data, version)
        self.assertEqual(self.order.works.filter(description='Одна операция').count(), 1)
    def test_payment_retry_and_overpayment(self):
        self.ready()
        version = self.order.version
        data = {'amount': Decimal('2500'), 'method': 'cash', 'request_key': uuid.uuid4()}
        self.act('payment', data, 'Приём')
        with self.assertRaises(Conflict): execute(self.order.pk, self.users['Приём'], 'payment', data, version)
        self.assertEqual(Payment.objects.count(), 1)
        with self.assertRaises(ValidationError): self.act('payment', {'amount': Decimal('1'), 'method': 'cash', 'request_key': uuid.uuid4()}, 'Приём')
    def test_wrong_role_and_foreign_order(self):
        with self.assertRaises(PermissionDenied): self.act('assign', {'master': self.users['Мастер']}, 'Приём')
        self.client.force_login(self.users['Мастер'])
        self.assertEqual(self.client.get(reverse('order_detail', args=[self.order.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('order_api', args=[self.order.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('reports')).status_code, 403)
    def test_illegal_issue_and_missing_works(self):
        with self.assertRaises(ValidationError): self.act('issue', {'free_reason': '', 'issue_method': 'Лично'}, 'Приём')
        self.act('assign', {'master': self.users['Мастер']}, 'Руководитель')
        self.act('start')
        with self.assertRaises(ValidationError): self.act('to_quality')
    def test_reception_cannot_post_master_operation(self):
        self.repair()
        self.client.force_login(self.users['Приём'])
        response = self.client.post(reverse('order_action', args=[self.order.pk, 'work']), {'description':'Обход', 'minutes': 1, 'cost': '0', 'version': self.order.version})
        self.assertEqual(response.status_code, 403)
    def test_public_api_minimal_and_secret(self):
        response = self.client.get(reverse('public_api', args=[self.order.token]))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        for forbidden in ('phone', 'client', 'serial', 'problem', 'comment', 'token'):
            self.assertNotIn(forbidden, data)
        self.assertNotIn(self.customer.phone, response.content.decode())
        self.assertEqual(self.client.get(reverse('public_api', args=['not-a-token'])).status_code, 404)
        self.assertIn('no-store', response.headers['Cache-Control'])
    def test_public_lookup_and_staff_auth(self):
        self.assertEqual(self.client.get(reverse('orders')).status_code, 302)
        self.assertEqual(self.client.post(reverse('track'), {'number': self.order.number, 'code': 'wrong'}).status_code, 200)
        response = self.client.post(reverse('track'), {'number': self.order.number, 'code': self.order.token})
        self.assertRedirects(response, reverse('public_status', args=[self.order.token]))
    def test_intake_validation_idempotence_and_repeated_device(self):
        self.client.force_login(self.users['Приём'])
        data = {'request_key': str(uuid.uuid4()), 'existing_client': self.customer.pk, 'kind': 'person', 'existing_device': self.device.pk, 'problem': 'Повторное обращение'}
        response = self.client.post(reverse('intake'), data)
        self.assertEqual(response.status_code, 302)
        self.client.post(reverse('intake'), data)
        self.assertEqual(self.device.orders.count(), 2)
        self.assertEqual(Client.objects.count(), 1)
        bad = self.client.post(reverse('intake'), {'request_key': str(uuid.uuid4()), 'kind': 'person'})
        self.assertContains(bad, 'Заполните поле')
        self.assertEqual(RepairOrder.objects.count(), 2)
    def test_all_staff_pages_render(self):
        user = User.objects.create_superuser('test_admin', password='OnlyForUnitTests_928')
        self.client.force_login(user)
        for name, args in [('dashboard', []), ('orders', []), ('intake', []), ('order_detail', [self.order.pk]), ('clients', []), ('client', [self.customer.pk]), ('device', [self.device.pk]), ('masters', []), ('reports', []), ('print_order', [self.order.pk])]:
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 200)
        self.assertEqual(self.client.get(reverse('qr', args=[self.order.pk]))['Content-Type'], 'image/png')
    def test_notifications_idempotent(self):
        from django.core import mail
        from django.test import override_settings
        # Without consent or address the event is queued as skipped, never sent.
        event(self.order, self.users['Приём'])
        skipped = self.order.history.first().notification
        self.assertEqual(skipped.state, 'skipped')
        # With consent the queued message is sent once; a repeated run must not resend.
        self.customer.email = 'client@example.com'
        self.customer.email_notifications = True
        self.customer.save()
        event(self.order, self.users['Приём'])
        with override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend'):
            call_command('send_notifications', verbosity=0)
            call_command('send_notifications', verbosity=0)
        notification = self.order.history.last().notification
        notification.refresh_from_db()
        self.assertEqual(notification.state, 'sent')
        self.assertEqual(notification.attempts, 1)
        self.assertEqual(notification.recipient, 'client@example.com')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.order.number, mail.outbox[0].subject)
    def test_blocked_user_cannot_sign_in(self):
        user = self.users['Мастер']; user.is_active=False; user.save()
        self.assertFalse(self.client.login(username=user.username, password='OnlyForUnitTests_928'))
    def test_admin_cannot_edit_workflow_records(self):
        user = User.objects.create_superuser('root', password='OnlyForUnitTests_928')
        self.client.force_login(user)
        response = self.client.get(f'/admin/repairs/repairorder/{self.order.pk}/change/')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="status"')
