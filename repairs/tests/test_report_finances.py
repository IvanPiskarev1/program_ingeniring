import io
import uuid
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from repairs.models import Diagnosis, Payment, RepairOrder, UsedPart
from repairs.services.reports import report_data
from .test_workflow import WorkflowFixture


class ReportFinancesTests(WorkflowFixture):
    def pay(self, order, amount, date=None):
        return Payment.objects.create(order=order, amount=amount, method='cash',
            request_key=uuid.uuid4(), author=self.users['Приём'], created_at=date or timezone.now())

    def data(self):
        return report_data(timezone.localdate(), timezone.localdate())

    def test_partial_payments_group_once_including_diagnosis_work_and_parts(self):
        self.repair()  # 500 diagnosis + 1500 work + 2 * 250 parts
        RepairOrder.objects.filter(pk=self.order.pk).update(created_at=timezone.now()-timedelta(days=45))
        self.pay(self.order, Decimal('700'))
        self.pay(self.order, Decimal('1800'))
        self.pay(self.order, Decimal('100'), timezone.now()-timedelta(days=2))
        # Multiple positions must not multiply the payment aggregates.
        UsedPart.objects.create(order=self.order, name='Шлейф', quantity=3, price=20)
        data = self.data()
        self.assertEqual(data['received'], 0)
        self.assertEqual(data['fault_payments'][0]['amount'], Decimal('2500'))
        self.assertEqual(data['fault_payments'][0]['name'], 'Питание')
        row = data['master_payments'][0]
        self.assertEqual((row['amount'], row['payment_count'], row['order_count']), (Decimal('2500'), 2, 1))
        self.assertEqual(data['used_parts'], [])

    def test_missing_category_master_and_inactive_master_not_lost(self):
        self.pay(self.order, Decimal('300'))
        other = RepairOrder.objects.create(client=self.customer, device=self.device, problem='Перегрев', master=self.users['Мастер'])
        self.users['Мастер'].is_active = False
        self.users['Мастер'].save()
        Diagnosis.objects.create(order=other, result='Износ', category=self.category, author=self.users['Мастер'], price=500)
        self.pay(other, Decimal('500'))
        data = self.data()
        self.assertEqual(sum(row['amount'] for row in data['fault_payments']), Decimal('800'))
        self.assertEqual(sum(row['amount'] for row in data['master_payments']), Decimal('800'))
        self.assertIn('Без категории', [r['name'] for r in data['fault_payments']])
        self.assertIn('Без мастера', [r['name'] for r in data['master_payments']])

    def test_parts_snapshot_quantities_issue_date_and_top_five(self):
        RepairOrder.objects.filter(pk=self.order.pk).update(issued_at=timezone.now(), status='issued', created_at=timezone.now()-timedelta(days=45))
        for i in range(7):
            UsedPart.objects.create(order=self.order, name=f'Деталь {i}', quantity=i+1, price=Decimal('10.25'))
        UsedPart.objects.create(order=self.order, name='Деталь 6', quantity=2, price=20)
        old = RepairOrder.objects.create(client=self.customer, device=self.device, problem='Износ', status='issued', issued_at=timezone.now()-timedelta(days=2))
        UsedPart.objects.create(order=old, name='Не учитывать', quantity=100, price=999)
        data = self.data()
        self.assertEqual(len(data['top_parts']), 5)
        self.assertEqual(len(data['remaining_parts']), 2)
        self.assertEqual(data['top_parts'][0], {'name': 'Деталь 6', 'quantity': 9, 'amount': Decimal('111.75')})
        self.assertEqual(data['parts_total'], Decimal('327.00'))
        self.client.force_login(self.users['Руководитель'])
        response = self.client.get(reverse('reports'), {'start': timezone.localdate().isoformat(), 'end': timezone.localdate().isoformat()})
        self.assertContains(response, 'Показать остальные детали (2)')
        self.assertContains(response, 'Деталь 0')
        self.assertContains(response, f'value="{timezone.localdate().isoformat()}"')

    def test_exports_full_list_and_formula_protection_and_access(self):
        self.users['Мастер'].first_name = '=1+1'
        self.users['Мастер'].save()
        self.order.master = self.users['Мастер']
        self.order.status = 'issued'
        self.order.issued_at = timezone.now()
        self.order.save()
        self.pay(self.order, Decimal('100'))
        for i in range(7):
            UsedPart.objects.create(order=self.order, name=f'=Деталь {i}', quantity=1, price=10)
        for role in ('Приём', 'Мастер', 'Контроль качества', 'Администратор'):
            self.client.force_login(self.users[role])
            for fmt in ('', 'csv', 'xlsx'):
                self.assertEqual(self.client.get(reverse('reports'), {'format': fmt}).status_code, 403)
        self.client.force_login(self.users['Руководитель'])
        response = self.client.get(reverse('reports'), {'format': 'xlsx'})
        rows = list(load_workbook(io.BytesIO(response.content)).active.values)
        self.assertIn(("'=1+1", '100', 1, 1), rows)
        self.assertEqual(len([r for r in rows if str(r[0]).startswith("'=Деталь")]), 7)
        text = self.client.get(reverse('reports'), {'format': 'csv'}).content.decode('utf-8-sig')
        self.assertIn("'=Деталь 6", text)
        self.assertIn('Оплаты по категориям', text)

    def test_empty_period(self):
        data = self.data()
        self.assertEqual(data['fault_payments'], [])
        self.assertEqual(data['master_payments'], [])
        self.assertEqual(data['used_parts'], [])
        self.assertEqual(data['parts_total'], 0)
