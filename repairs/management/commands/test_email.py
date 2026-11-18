import getpass
from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Одно проверочное письмо только на разрешённый адрес владельца проекта.'

    def add_arguments(self, parser):
        parser.add_argument('--ask-password', action='store_true')

    def handle(self, *args, **options):
        if options['ask_password']:
            settings.EMAIL_HOST_PASSWORD = getpass.getpass('Пароль приложения Gmail (ввод скрыт): ').replace(' ', '')
        if not settings.EMAIL_HOST_PASSWORD:
            raise CommandError('Используйте --ask-password или ASUI_EMAIL_PASSWORD.')
        try:
            result = send_mail('АСУИ: проверка почтовых уведомлений',
                               'Проверка отправки писем из АСУИ Сервисный центр. Это не изменение заказа.',
                               settings.DEFAULT_FROM_EMAIL, [settings.ASUI_EMAIL_TEST_RECIPIENT],
                               fail_silently=False)
        except Exception as exc:
            reason = str(exc).strip() or exc.__class__.__name__
            raise CommandError(
                'Отправка не подтверждена. Причина от почтового сервера:\n'
                f'{reason}\n'
                'Не повторяйте автоматически.') from None
        if result != 1:
            raise CommandError('Сервер не подтвердил приём письма.')
        self.stdout.write('Письмо принято почтовым сервером. Проверьте входящие и спам на разрешённом адресе.')
