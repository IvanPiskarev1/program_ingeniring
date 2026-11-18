import uuid
from datetime import datetime, timezone as datetime_timezone
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from repairs.models import Payment, RepairOrder
from .test_workflow import WorkflowFixture


class PrintTimesTests(WorkflowFixture):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.users['Приём'])
        self.url = reverse('print_order', args=[self.order.pk])

    def test_print_before_payment_and_issue(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'Оплаты ещё не зарегистрированы.')
        self.assertContains(response, 'Изделие ещё не выдано.')
        self.assertNotContains(response, 'Дата и время оплаты:')
        self.assertNotContains(response, 'Дата и время выдачи:')

    def test_print_all_payments_and_issue_in_local_time(self):
        times = [datetime(2026, 11, 17, 20, 15, tzinfo=datetime_timezone.utc),
                 datetime(2026, 11, 18, 7, 35, tzinfo=datetime_timezone.utc)]
        for at, amount, method in zip(times, ['500.00', '1500.00'], ['cash', 'card']):
            Payment.objects.create(order=self.order, amount=Decimal(amount), method=method,
                                   request_key=uuid.uuid4(), author=self.users['Приём'], created_at=at)
        issued = datetime(2026, 11, 18, 8, 45, tzinfo=datetime_timezone.utc)
        RepairOrder.objects.filter(pk=self.order.pk).update(
            status='issued', issued_at=issued, issue_method='Лично владельцу')
        with timezone.override('Europe/Moscow'):
            response = self.client.get(self.url)
        self.assertContains(response, 'Дата и время оплаты:', count=2)
        self.assertContains(response, '17.11.2026 23:15 · Наличные · 500,00 ₽')
        self.assertContains(response, '18.11.2026 10:35 · Карта · 1500,00 ₽')
        self.assertContains(response, 'Дата и время выдачи: 18.11.2026 11:45 · Лично владельцу')
        self.assertNotContains(response, 'Оплаты ещё не зарегистрированы.')
        self.assertNotContains(response, 'Изделие ещё не выдано.')

    def test_print_partial_payment_before_issue(self):
        Payment.objects.create(order=self.order, amount=Decimal('500'), method='cash',
                               request_key=uuid.uuid4(), author=self.users['Приём'])
        response = self.client.get(self.url)
        self.assertContains(response, 'Дата и время оплаты:', count=1)
        self.assertContains(response, 'Изделие ещё не выдано.')
