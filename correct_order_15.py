"""One-time, explicitly approved correction; preserves all source row IDs."""
import os
from decimal import Decimal
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.db import transaction
from repairs.models import RepairOrder, UsedPart, RepairWork, Payment, AuditEvent

with transaction.atomic():
    order = RepairOrder.objects.select_for_update().get(pk=15)
    part = UsedPart.objects.get(pk=9, order=order)
    work = RepairWork.objects.get(pk=13, order=order)
    payment = Payment.objects.get(pk=6, order=order)
    if part.name == 'Сетевой фильтр питания бытовой техники' and order.final_total == Decimal('3300.00') and order.paid_total == Decimal('3300.00'):
        print('Already corrected; no writes.')
    else:
        assert (part.name, part.quantity, part.price) == ('Vapi642558.99', 123, Decimal('22222.00')), 'Source part changed; abort'
        assert work.cost == Decimal('505050.00') and order.final_total == Decimal('3238356.00'), 'Source total changed; abort'
        assert payment.amount == Decimal('3238356.00') and order.payments.count() == 1, 'Payments changed; abort'
        assert order.estimate == Decimal('600000.00') and order.approved_estimate is None, 'Estimate changed; abort'
        part.name = 'Сетевой фильтр питания бытовой техники'
        part.quantity = 1
        part.price = Decimal('1500.00')
        part.save(update_fields=['name', 'quantity', 'price'])
        work.description = 'Замена сетевого фильтра и проверка цепи питания'
        work.cost = Decimal('1800.00')
        work.save(update_fields=['description', 'cost'])
        order.estimate = Decimal('3300.00')
        order.version += 1
        order.save(update_fields=['estimate', 'version'])
        payment.amount = Decimal('3300.00')
        payment.save(update_fields=['amount'])
        AuditEvent.objects.create(actor=payment.author, order=order, action='По запросу владельца исправлены ошибочные данные: деталь №9, работа №13, оценка 600000 -> 3300, оплата №6 3238356 -> 3300. Записи сохранены.')
        order.refresh_from_db()
        assert order.final_total == order.paid_total == Decimal('3300.00')
        print('Corrected order 15: total=3300.00 paid=3300.00 balance=0.00; part=9 work=13 payment=6 preserved.')
