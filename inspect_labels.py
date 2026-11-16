"""Inspect names and placeholder labels only; never print credentials or tokens."""
import os
import re
import sys
sys.stdout.reconfigure(encoding='utf-8')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.apps import apps
from django.db import models
from django.contrib.auth import get_user_model
pattern = re.compile(r'демо|demo|учеб|тест|test|альфа|бета|гамма|дельта|эпсилон', re.I)
User = get_user_model()
for row in User.objects.values('id', 'username', 'first_name', 'last_name'):
    print('USER', row)
for name in ('Client', 'Device'):
    model = apps.get_model('repairs', name)
    fields = ['id', 'name', 'contact'] if name == 'Client' else ['id', 'manufacturer', 'model', 'serial', 'kind__name']
    for row in model.objects.values(*fields):
        print(name, row)
for model in apps.get_app_config('repairs').get_models():
    fields = [f.name for f in model._meta.fields if isinstance(f, (models.CharField, models.TextField)) and f.name not in ('token', 'phone', 'email')]
    for row in model.objects.values('pk', *fields):
        matches = {k: v for k, v in row.items() if isinstance(v, str) and pattern.search(v)}
        if matches:
            print('LABEL', model.__name__, row['pk'], matches)
