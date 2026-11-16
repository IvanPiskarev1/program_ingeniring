from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from repairs.permissions import ROLES

class Command(BaseCommand):
    help = 'Создать пять ролей. Администратор управляет обычными сотрудниками и справочниками, но не суперпользователями.'
    def handle(self, *args, **options):
        for role in ROLES:
            group, _ = Group.objects.get_or_create(name=role)
            if role == 'Администратор':
                group.permissions.set(Permission.objects.filter(content_type__app_label='repairs').exclude(codename__startswith='delete_').filter(codename__in=[
                    'view_client','change_client','view_device','change_device',
                    'view_devicetype','add_devicetype','change_devicetype',
                    'view_faultcategory','add_faultcategory','change_faultcategory',
                    'view_notificationtemplate','add_notificationtemplate','change_notificationtemplate',
                    'view_repairorder','view_auditevent','view_statushistory','view_notification','view_payment',
                    'view_diagnosis','view_repairwork','view_usedpart','view_qualitycheck',
                ]) | Permission.objects.filter(content_type__app_label='auth', codename__in=['add_user','view_user','change_user']))
        self.stdout.write(self.style.SUCCESS('Роли настроены. Для администратора также установите is_staff.'))
