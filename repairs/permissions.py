from functools import wraps
from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required
from .models import RepairOrder

RECEPTION = 'Приём'
MASTER = 'Мастер'
QUALITY = 'Контроль качества'
MANAGER = 'Руководитель'
ADMIN = 'Администратор'
ROLES = (RECEPTION, MASTER, QUALITY, MANAGER, ADMIN)


def has_role(user, *roles):
    return bool(user.is_authenticated and user.is_active and (user.is_superuser or user.groups.filter(name__in=roles).exists()))


def staff_required(view):
    @login_required
    @wraps(view)
    def inner(request, *args, **kwargs):
        if not has_role(request.user, *ROLES):
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return inner


def visible_orders(user):
    qs = RepairOrder.objects.select_related('client', 'device', 'device__kind', 'master').prefetch_related('works', 'parts', 'payments')
    if has_role(user, RECEPTION, MANAGER, ADMIN):
        return qs
    if has_role(user, MASTER, QUALITY):
        from django.db.models import Q
        access = Q(pk__in=[])
        if has_role(user, MASTER):
            access |= Q(master=user)
        if has_role(user, QUALITY):
            access |= Q(status=RepairOrder.Status.QUALITY)
        return qs.filter(access)
    return qs.none()


def navigation(request):
    user = request.user
    return {'can_backup': has_role(user, ADMIN), 'can_receive': has_role(user, RECEPTION), 'can_manage': has_role(user, MANAGER),
            'can_quality': has_role(user, QUALITY), 'can_master': has_role(user, MASTER),
            'can_directory': has_role(user, RECEPTION, MANAGER, ADMIN),
            'is_employee': has_role(user, *ROLES), 'role_names': ', '.join(user.groups.values_list('name', flat=True)) if user.is_authenticated else ''}
