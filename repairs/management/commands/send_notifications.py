import getpass
import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from repairs.services.email_notifications import process_queue


class Command(BaseCommand):
    help = 'Отправка новых email-уведомлений через SMTP. Старые записи журнала не рассылаются.'

    def add_arguments(self, parser):
        parser.add_argument('--watch', action='store_true', help='Проверять очередь каждые 15 секунд')
        parser.add_argument('--ask-password', action='store_true', help='Скрыто ввести пароль приложения для этого процесса')

    def handle(self, *args, **options):
        if options['ask_password']:
            settings.EMAIL_HOST_PASSWORD = getpass.getpass('Пароль приложения Gmail (ввод скрыт): ').replace(' ', '')
        if not settings.EMAIL_HOST_PASSWORD and settings.EMAIL_BACKEND.endswith('smtp.EmailBackend'):
            raise CommandError('Задайте ASUI_EMAIL_PASSWORD или используйте --ask-password. Обычный пароль Gmail не нужен.')
        try:
            while True:
                sent = process_queue()
                self.stdout.write(f'Передано почтовому серверу: {sent}. Это не подтверждение доставки.')
                if not options['watch']:
                    break
                time.sleep(15)
        except KeyboardInterrupt:
            self.stdout.write('Обработка остановлена.')
