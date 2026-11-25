"""Read-only inspection of anomalous report source rows."""
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from repairs.models import RepairOrder, UsedPart, RepairWork, PriceItem
from django.db.models import Q
ids = set(UsedPart.objects.filter(Q(name__icontains='Vapi') | Q(price__gt=20000) | Q(quantity__gt=10)).values_list('order_id', flat=True))
ids.update(RepairWork.objects.filter(cost__gt=30000).values_list('order_id', flat=True))
for o in RepairOrder.objects.filter(pk__in=ids).select_related('device','master').order_by('pk'):
    print('ORDER', o.pk, str(o.device), o.status, 'master', o.master_id, 'total', o.final_total, 'paid', o.paid_total, 'estimate', o.estimate)
    print('PARTS', list(o.parts.values('id','name','quantity','price')))
    print('WORKS', list(o.works.values('id','description','quantity','cost')))
    print('DIAGNOSIS', list(o.__class__.objects.filter(pk=o.pk).values('diagnosis__price','diagnosis__category__name','diagnosis__required_parts')))
    print('PAYMENTS', list(o.payments.values('id','amount')))
    print('REVISIONS', list(o.estimate_revisions.values('id','amount')))
print('CATALOG', list(PriceItem.objects.filter(Q(name__icontains='Bosch') & (Q(name__icontains='плат') | Q(name__icontains='насос'))).values('id','name','price')[:15]))
print('DEVICE', list(RepairOrder.objects.filter(pk=15).values('device__kind__name','device__manufacturer','device__model','problem')))
from django.contrib.auth.models import User
print('MASTER', list(User.objects.filter(pk=7).values('id','username','first_name','last_name')))
