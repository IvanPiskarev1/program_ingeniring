"""Read-only live LAN checks (temporary staff session removed afterwards)."""
import os
import sys
from urllib.request import build_opener, ProxyHandler, Request

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.conf import settings
from django.contrib.auth import get_user_model, SESSION_KEY, BACKEND_SESSION_KEY, HASH_SESSION_KEY
from django.contrib.sessions.backends.db import SessionStore
from django.urls import reverse
from repairs.models import RepairOrder

base = sys.argv[1].rstrip('/')
opener = build_opener(ProxyHandler({}))

def get(path, cookie=None):
    headers = {'Cookie': cookie} if cookie else {}
    with opener.open(Request(base + path, headers=headers), timeout=15) as response:
        assert response.status == 200
        return response.read(), response.headers

get('/')
get('/track/')
user = get_user_model().objects.filter(is_active=True, groups__name='Приём').first()
assert user is not None, 'No active reception account'
order = RepairOrder.objects.first()
assert order is not None, 'No order for QR verification'
session = SessionStore()
session[SESSION_KEY] = str(user.pk)
session[BACKEND_SESSION_KEY] = 'django.contrib.auth.backends.ModelBackend'
session[HASH_SESSION_KEY] = user.get_session_auth_hash()
session.save()
try:
    cookie = settings.SESSION_COOKIE_NAME + '=' + session.session_key
    html, _ = get(reverse('print_order', args=[order.pk]), cookie)
    target = base + reverse('public_status', args=[order.token])
    assert target.encode() in html, 'Print QR target is not the LAN address'
    assert b'http://localhost' not in html and b'http://127.0.0.1' not in html
    png, headers = get(reverse('qr', args=[order.pk]), cookie)
    assert headers.get_content_type() == 'image/png' and png.startswith(b'\x89PNG\r\n\x1a\n')
    get(reverse('public_status', args=[order.token]))
    print('PASS: live LAN home/track, authenticated print with LAN URL, QR PNG and public status; temporary session removed. Tokens not logged.')
finally:
    session.delete()
