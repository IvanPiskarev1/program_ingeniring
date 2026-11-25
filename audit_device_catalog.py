"""Read-only catalogue coverage report; no personal data or tokens."""
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.db.models import Count
from repairs.models import Device, DeviceType, PriceItem, WorkCatalogItem, RepairOrder
print('COUNTS', {'devices': Device.objects.count(), 'models': Device.objects.values('manufacturer', 'model').distinct().count(), 'parts': PriceItem.objects.filter(kind='part').count(), 'works': WorkCatalogItem.objects.count(), 'orders': RepairOrder.objects.count()})
from repairs.models import DeviceCatalogItem
print('CATALOG', {'models': DeviceCatalogItem.objects.count(), 'without_parts': DeviceCatalogItem.objects.filter(parts=None).count(), 'without_works': DeviceCatalogItem.objects.filter(works=None).count(), 'uncovered_devices': sum(not DeviceCatalogItem.objects.filter(kind=d.kind, manufacturer=d.manufacturer, model=d.model).exists() for d in Device.objects.all())})
print('TYPES', list(DeviceType.objects.values_list('id','name')))
print('DEVICES', list(Device.objects.values('kind__name','manufacturer','model').annotate(count=Count('pk')).order_by('manufacturer','model')))
print('CLIENT DEVICE COUNTS', list(RepairOrder.objects.values('client_id').annotate(count=Count('device_id', distinct=True)).values_list('count',flat=True)))
print('WORKS', list(WorkCatalogItem.objects.values_list('name','category__name')))
print('LEGACY PARTS', list(PriceItem.objects.filter(kind='part', sku__isnull=True).values_list('name','category','group')))
