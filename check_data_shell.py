from django.contrib.auth.models import User
from repairs.models import Client, RepairOrder, PriceItem, Device
for u in User.objects.filter(is_staff=True):
    print(u.username, '|', u.first_name, u.last_name, '|', [g.name for g in u.groups.all()])
print('clients:', Client.objects.count(), 'price:', PriceItem.objects.count(), 'devices:', Device.objects.count())
for c in Client.objects.all()[:3]:
    print('client:', c.name, c.phone)
print('price kinds:', PriceItem.objects.values('kind').distinct().count())
