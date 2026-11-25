"""Verify correction against pre-change backup and actual report aggregation."""
import os
import sqlite3
from datetime import date
from decimal import Decimal
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.db import connection
from repairs.models import RepairOrder, UsedPart, RepairWork, Payment
from repairs.services.reports import report_data
backup = sqlite3.connect('backups/asui-20261125-212701-201197.sqlite3')
with connection.cursor() as cursor:
    for table in ['repairs_repairorder', 'repairs_usedpart', 'repairs_repairwork', 'repairs_payment']:
        old = [r[0] for r in backup.execute(f'SELECT id FROM {table} ORDER BY id')]
        cursor.execute(f'SELECT id FROM {table} ORDER BY id')
        assert old == [r[0] for r in cursor.fetchall()], table
order = RepairOrder.objects.get(pk=15)
assert order.final_total == order.paid_total == order.estimate == Decimal('3300.00')
assert order.balance == 0 and order.diagnosis.price == 0
assert UsedPart.objects.get(pk=9).quantity == 1
assert RepairWork.objects.filter(pk=13, order=order).exists()
assert Payment.objects.filter(pk=6, order=order, amount=3300).exists()
report = report_data(date(2000,1,1), date(2100,1,1))
category = next(r for r in report['fault_payments'] if r['name'] == 'Не включается')
master = next(r for r in report['master_payments'] if r['order__master_id'] == order.master_id)
print('Category Не включается:', category['amount'])
print('Master:', master['name'], master['amount'], 'orders:', master['order_count'], 'payments:', master['payment_count'])
assert not any('Vapi642558' in r['name'] for r in report['used_parts'])
part = next(r for r in report['used_parts'] if r['name'] == 'Сетевой фильтр питания бытовой техники')
print('Part:', part['name'], part['quantity'], part['amount'])
assert part['quantity'] == 1 and part['amount'] == Decimal('1500.00')
assert category['amount'] < Decimal('1000000') and master['amount'] < Decimal('1000000')
print('PASS: row IDs preserved; corrected total/payment/balance; actual report aggregates consistent; no anomalous part label.')
backup.close()
