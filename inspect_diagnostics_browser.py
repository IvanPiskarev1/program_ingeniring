import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from repairs.models import RepairOrder
order = RepairOrder.objects.filter(status='diagnosis', master__is_active=True).select_related('master').first()
if order:
    print('Order:', order.pk, 'Master login:', order.master.username)
else:
    print('No existing diagnosis order; browser editing requires a separate database.')
