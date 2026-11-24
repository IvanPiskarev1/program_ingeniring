from decimal import Decimal
import uuid

from django.urls import reverse
from repairs.models import Payment, RepairOrder
from .test_workflow import WorkflowFixture


class PrintFormsTests(WorkflowFixture):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.users['Приём'])
        self.intake = reverse('print_intake', args=[self.order.pk])
        self.issue = reverse('print_issue', args=[self.order.pk])

    def test_intake_details_and_signatures(self):
        self.order.accessories = 'Зарядное устройство'
        self.order.appearance = 'Царапина на крышке'
        self.order.save()
        response = self.client.get(self.intake)
        for text in ('Приём изделия', self.customer.name, self.order.problem,
                     'Зарядное устройство', 'Царапина на крышке', 'Принял', 'Сдал'):
            self.assertContains(response, text)
        for text in ('<strong>Выдал</strong>', '<strong>Получил</strong>', '<h2>Оплаты</h2>'):
            self.assertNotContains(response, text)
        self.assertContains(response, 'Подпись: __________________', count=2)
        self.assertNotContains(response, 'ФИО: ' + self.users['Приём'].username)
        self.assertContains(response, reverse('qr', args=[self.order.pk]))
        legacy = self.client.get(reverse('print_order', args=[self.order.pk]))
        self.assertContains(legacy, '<h1>Приём изделия</h1>', html=True)
        self.assertEqual(legacy.context['is_intake'], response.context['is_intake'])

    def test_unissued_form_is_blocked_and_button_hidden(self):
        self.assertContains(self.client.get(self.issue), 'Изделие ещё не выдано', status_code=409)
        response = self.client.get(reverse('order_detail', args=[self.order.pk]))
        self.assertContains(response, self.intake)
        self.assertNotContains(response, self.issue)
        RepairOrder.objects.filter(pk=self.order.pk).update(status='issued')
        self.assertEqual(self.client.get(self.issue).status_code, 409)

    def test_issued_form_preserves_work_payment_and_employee(self):
        self.ready()
        employee = self.users['Приём']
        employee.first_name = 'Анна'
        employee.last_name = 'Соколова'
        employee.save()
        self.act('payment', {'amount': Decimal('2500'), 'method': 'cash', 'request_key': uuid.uuid4()}, 'Приём')
        self.act('issue', {'free_reason': '', 'issue_method': 'Представителю'}, 'Приём')
        before = (self.order.version, Payment.objects.count(), self.order.history.count())
        response = self.client.get(self.issue)
        for text in ('Восстановление цепи', 'Разъём', 'Дата и время оплаты:',
                     'Дата и время выдачи:', 'Представителю', 'Анна Соколова',
                     'Замечания при получении', 'ФИО: __________________________'):
            self.assertContains(response, text)
        self.assertContains(response, 'Подпись: __________________', count=2)
        self.assertContains(response, '<strong>Выдал</strong>', html=True)
        self.assertContains(response, '<strong>Получил</strong>', html=True)
        self.assertNotContains(response, '<strong>Принял</strong>')
        self.assertNotContains(response, 'ФИО фактического получателя и замечания заполняются от руки при передаче изделия.')
        self.order.refresh_from_db()
        self.assertEqual(before, (self.order.version, Payment.objects.count(), self.order.history.count()))
        self.assertIn('no-store', response.headers['Cache-Control'])
        detail = self.client.get(reverse('order_detail', args=[self.order.pk]))
        self.assertContains(detail, self.intake)
        self.assertContains(detail, self.issue)

    def test_access_control(self):
        self.client.logout()
        for url in (self.intake, self.issue):
            self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.users['Мастер'])
        for url in (self.intake, self.issue):
            self.assertEqual(self.client.get(url).status_code, 404)
