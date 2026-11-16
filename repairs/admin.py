from django.contrib import admin
from django.contrib.auth.admin import UserAdmin, GroupAdmin
from django.contrib.auth.models import User, Group
from . import models


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False


for model in (models.RepairOrder, models.Diagnosis, models.RepairWork, models.UsedPart, models.QualityCheck,
              models.StatusHistory, models.Notification, models.Payment, models.AuditEvent):
    admin.site.register(model, ReadOnlyAdmin)


@admin.register(models.Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ['name', 'kind', 'phone', 'email']
    search_fields = ['name', 'phone']
    def has_delete_permission(self, request, obj=None): return False


@admin.register(models.Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ['manufacturer', 'model', 'serial', 'kind']
    search_fields = ['serial', 'model']
    def has_delete_permission(self, request, obj=None): return False


admin.site.register([models.DeviceType, models.FaultCategory, models.NotificationTemplate])


admin.site.unregister(User)
@admin.register(User)
class SafeUserAdmin(UserAdmin):
    def get_fieldsets(self, request, obj=None):
        if request.user.is_superuser:
            return super().get_fieldsets(request, obj)
        if not obj: return self.add_fieldsets
        return ((None, {'fields': ('username', 'password')}), ('Сведения', {'fields': ('first_name', 'last_name', 'email')}), ('Состояние', {'fields': ('is_active', 'groups')}))
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs if request.user.is_superuser else qs.filter(is_superuser=False, is_staff=False)
    def has_delete_permission(self, request, obj=None): return False
    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == 'groups' and not request.user.is_superuser:
            kwargs['queryset'] = Group.objects.exclude(name='Администратор')
        return super().formfield_for_manytomany(db_field, request, **kwargs)


admin.site.unregister(Group)
@admin.register(Group)
class SafeGroupAdmin(GroupAdmin):
    def has_module_permission(self, request): return request.user.is_superuser
    def has_view_permission(self, request, obj=None): return request.user.is_superuser
    def has_change_permission(self, request, obj=None): return request.user.is_superuser
    def has_add_permission(self, request): return request.user.is_superuser
    def has_delete_permission(self, request, obj=None): return False
