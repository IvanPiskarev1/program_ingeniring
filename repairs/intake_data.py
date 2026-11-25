import re
from .models import Device


def phone_key(value):
    digits = re.sub(r'\D', '', value)
    return '7' + digits[1:] if len(digits) == 11 and digits.startswith('8') else digits


def client_fields(client):
    return {'id': client.pk, 'kind': client.kind, 'client_name': client.name,
            'contact': client.contact, 'phone': client.phone, 'email': client.email,
            'email_notifications': client.email_notifications}


def client_devices(client):
    return Device.objects.filter(orders__client=client).select_related('kind').distinct().order_by('pk')


def device_fields(device, client):
    last = device.orders.filter(client=client).order_by('-created_at', '-pk').first()
    return {'id': device.pk, 'device_type': device.kind_id, 'manufacturer': device.manufacturer,
            'device_model': device.model, 'serial': device.serial,
            'accessories': last.accessories if last else '', 'label': str(device)}
