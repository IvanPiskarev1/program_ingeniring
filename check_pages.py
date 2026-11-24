from django.test import Client
from django.conf import settings
settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ['testserver']
from repairs.models import RepairOrder
c = Client()
ok = c.login(username='andrey.priem', password='12341234')
print('login:', ok)
r = c.get('/price/')
print('price:', r.status_code)
body = r.content.decode('utf-8')
print('has works:', 'Замена дисплея' in body or 'работы' in body.lower())
print('has diagnosis:', 'Диагностика' in body)
r2 = c.get('/orders/')
print('orders:', r2.status_code)
o = RepairOrder.objects.exclude(status='issued').first()
if o:
    r3 = c.get(f'/orders/{o.pk}/')
    print('order card:', r3.status_code)
