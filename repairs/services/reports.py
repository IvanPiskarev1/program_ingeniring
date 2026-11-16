from datetime import timedelta
from decimal import Decimal
from django.contrib.auth.models import User
from django.utils import timezone
from ..models import Payment, RepairOrder


def report_data(start, end):
    # Each metric uses its own date: intake, issue or payment, never an accidental intersection.
    received = RepairOrder.objects.filter(created_at__date__gte=start, created_at__date__lte=end)
    issued = RepairOrder.objects.filter(issued_at__date__gte=start, issued_at__date__lte=end)
    payments = Payment.objects.filter(created_at__date__gte=start, created_at__date__lte=end)
    cycles = [(o.issued_at - o.created_at).total_seconds() / 86400 for o in issued]
    repair_hours = []
    for order in issued.prefetch_related('history'):
        began = None
        seconds = 0
        for item in order.history.all():
            if began:
                seconds += (item.created_at - began).total_seconds()
                began = None
            if item.new_status == 'repair': began = item.created_at
        repair_hours.append(seconds / 3600)
    masters = []
    for user in User.objects.filter(is_active=True, groups__name='Мастер').distinct():
        active = user.assigned_orders.exclude(status='issued')
        masters.append({'user': user, 'active': active.count(), 'overdue': active.filter(due_date__lt=timezone.localdate()).count()})
    from django.db.models import Count
    faults = received.filter(diagnosis__isnull=False).values('diagnosis__category__name').annotate(total=Count('id')).order_by('-total')
    return {'orders': received.select_related('device', 'client'), 'received': received.count(), 'issued': issued.count(),
        'average_days': round(sum(cycles) / len(cycles), 2) if cycles else None,
        'repair_hours': round(sum(repair_hours) / len(repair_hours), 2) if repair_hours else None,
        'demo_revenue': sum((p.amount for p in payments.filter(is_demo=True)), Decimal('0')),
        'real_revenue': sum((p.amount for p in payments.filter(is_demo=False)), Decimal('0')),
        'masters': masters, 'faults': faults}
