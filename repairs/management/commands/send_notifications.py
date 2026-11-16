from django.core.management.base import BaseCommand
from django.db import transaction
from repairs.models import Notification

class Command(BaseCommand):
    help = 'Учебная обработка очереди. Не отправляет SMS/e-mail.'
    def handle(self, *args, **options):
        total = 0
        for pk in Notification.objects.filter(state__in=['pending', 'error'], attempts__lt=3).values_list('pk', flat=True):
            with transaction.atomic():
                item = Notification.objects.get(pk=pk)
                if item.state == 'test' or item.attempts >= 3: continue
                item.attempts += 1
                item.state = 'test'
                item.error = ''
                item.save(update_fields=['attempts','state','error'])
                total += 1
        self.stdout.write(f'Учебно обработано: {total}. Реальные сообщения не отправлялись.')
