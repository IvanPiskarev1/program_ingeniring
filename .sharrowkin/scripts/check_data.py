import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) if '__file__' in dir() else '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.contrib.auth.models import User, Group
from repairs.models import Client, RepairOrder, PriceItem, Device, Payment
for u in User.objects.filter(is_staff=True):
    print(u.username, '|', u.get_full_name(), '|', [g.name for g in u.groups.all()])
print('clients:', Client.objects.count(), 'orders:', RepairOrder.objects.count(), 'price:', PriceItem.objects.count(), 'devices:', Device.objects.count(), 'payments:', Payment.objects.count())
from django.db.models import Count
print(RepairOrder.objects.values('status').annotate(n=Count('id')).order_by('-n'))
print('name sample:', [c.full_name for c in Client.objects.all()[:3]])
print('order numbers sample:', list(RepairOrder.objects.values_list('number', flat=True)[:3]))
