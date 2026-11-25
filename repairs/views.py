import uuid
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction, OperationalError
from django.db.models import Q, Count
from django.http import HttpResponse


def favicon(request):
    return HttpResponse(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="16" fill="#e7f0ea"/><path d="M16 39c7-1 11-6 14-16 2-7 6-10 10-10 5 0 8 4 8 9 0 7-6 13-13 13-5 0-8 3-9 8-5 0-8-1-10-4z" fill="#153f33"/><circle cx="43" cy="21" r="3" fill="#d9ad64"/></svg>',
        content_type='image/svg+xml',
    )
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from . import forms
from .models import AuditEvent, Client, Device, PriceItem, RepairOrder, WorkCatalogItem
from .permissions import ADMIN, MANAGER, MASTER, QUALITY, RECEPTION, has_role, staff_required, visible_orders
from .services.orders import Conflict, event, execute


def home(request):
    return render(request, 'public/home.html')


@staff_required
def dashboard(request):
    orders = visible_orders(request.user)
    counts = {row['status']: row['total'] for row in orders.values('status').annotate(total=Count('pk'))}
    tasks = orders.exclude(status=RepairOrder.Status.ISSUED)
    return render(request, 'repairs/dashboard.html', {'orders': tasks[:8], 'active_count': tasks.count(),
        'ready_count': counts.get('ready', 0), 'quality_count': counts.get('quality', 0),
        'overdue_count': tasks.filter(due_date__lt=timezone.localdate()).count()})


def filtered_orders(request):
    orders = visible_orders(request.user)
    q = request.GET.get('q', '').strip()
    if q:
        number = q.upper().replace('АС-', '').lstrip('0') or '0'
        condition = Q(client__name__icontains=q) | Q(client__phone__icontains=q) | Q(device__serial__icontains=q) | Q(device__model__icontains=q)
        if number.isascii() and number.isdigit() and len(number) <= 18:
            condition |= Q(pk=int(number))
        orders = orders.filter(condition)
    if request.GET.get('status') in dict(RepairOrder.Status.choices):
        orders = orders.filter(status=request.GET['status'])
    if request.GET.get('master', '').isdigit():
        orders = orders.filter(master_id=request.GET['master'])
    date_form = forms.ReportForm(request.GET)
    if date_form.is_valid():
        if date_form.cleaned_data['start']:
            orders = orders.filter(created_at__date__gte=date_form.cleaned_data['start'])
        if date_form.cleaned_data['end']:
            orders = orders.filter(created_at__date__lte=date_form.cleaned_data['end'])
    return orders, date_form


@staff_required
def order_list(request):
    orders, date_form = filtered_orders(request)
    params = request.GET.copy()
    params.pop('page', None)
    return render(request, 'repairs/orders.html', {'page_obj': Paginator(orders, 15).get_page(request.GET.get('page')),
        'statuses': RepairOrder.Status.choices, 'date_form': date_form, 'query': params.urlencode(),
        'masters': User.objects.filter(is_active=True, groups__name=MASTER)})


@staff_required
def order_new(request):
    if not has_role(request.user, RECEPTION):
        raise PermissionDenied
    if request.method == 'POST' and not request.POST.get('load_existing'):
        try:
            key = uuid.UUID(request.POST.get('request_key', ''))
        except (ValueError, TypeError, AttributeError):
            key = None
        if key:
            old = RepairOrder.objects.filter(request_key=key).first()
            if old:
                return redirect('order_detail', pk=old.pk)
    payload = request.POST.copy() if request.method == 'POST' else None
    if payload is not None and payload.get('load_existing'):
        from .intake_data import client_fields, client_devices, device_fields
        client = Client.objects.filter(pk=payload.get('existing_client')).first() if payload.get('existing_client', '').isdigit() else None
        if client:
            if payload.get('load_existing') == 'existing_client':
                payload.update({k: v for k, v in client_fields(client).items() if k != 'id'})
                payload['email_notifications'] = 'on' if client.email_notifications else ''
                payload['client_loaded'] = '1'
            device = client_devices(client).filter(pk=payload.get('existing_device')).first() if payload.get('existing_device', '').isdigit() else None
            if device and payload.get('load_existing') != 'catalog_model':
                payload.update({k: v for k, v in device_fields(device, client).items() if k not in ('id', 'label')})
        if payload.get('load_existing') == 'catalog_model':
            from .models import DeviceCatalogItem
            catalog = DeviceCatalogItem.objects.filter(pk=payload.get('catalog_model')).first() if payload.get('catalog_model', '').isdigit() else None
            if catalog:
                payload.update(device_type=str(catalog.kind_id), manufacturer=catalog.manufacturer, device_model=catalog.model, existing_device='', serial='')
        form = forms.IntakeForm(initial=payload.dict())
        form.fields['existing_device'].queryset = client_devices(client) if client else Device.objects.none()
    else:
        form = forms.IntakeForm(payload)
    if request.method == 'POST' and not request.POST.get('load_existing') and form.is_valid():
        data = form.cleaned_data
        with transaction.atomic():
            from .models import IntakeRequest
            IntakeRequest.objects.get_or_create(key=data['request_key'])
            old = RepairOrder.objects.filter(request_key=data['request_key']).first()
            if old:
                return redirect('order_detail', pk=old.pk)
            client = data['existing_client']
            if client:
                for field, attr in [('client_name', 'name'), ('kind', 'kind'), ('contact', 'contact'), ('phone', 'phone'), ('email', 'email')]:
                    if field in request.POST:
                        setattr(client, attr, data[field])
                if request.POST.get('client_loaded'):
                    client.email_notifications = data['email_notifications']
                client.save()
            else:
                client = Client.objects.create(kind=data['kind'], name=data['client_name'], contact=data['contact'], phone=data['phone'], email=data['email'], email_notifications=data['email_notifications'])
            device = data['existing_device']
            if device:
                if not device.orders.filter(client=client).exists():
                    raise PermissionDenied
                for field, attr in [('device_type', 'kind'), ('manufacturer', 'manufacturer'), ('device_model', 'model'), ('serial', 'serial')]:
                    if field in request.POST and (data.get(field) or field == 'serial'):
                        setattr(device, attr, data[field])
                device.save()
            else:
                device = Device.objects.create(kind=data['device_type'], manufacturer=data['manufacturer'], model=data['device_model'], serial=data['serial'])
            order = RepairOrder.objects.create(client=client, device=device, problem=data['problem'], accessories=data['accessories'], appearance=data['appearance'], request_key=data['request_key'])
            event(order, request.user)
            AuditEvent.objects.create(actor=request.user, order=order, action='Создан заказ')
        messages.success(request, f'Заказ {order.number} принят. Клиентская ссылка доступна в карточке.')
        return redirect('order_detail', pk=order.pk)
    return render(request, 'repairs/form_page.html', {'form': form, 'title': 'Приём устройства', 'subtitle': 'Новый заказ или повторное обращение с сохранением истории.', 'button': 'Принять устройство', 'is_intake': True, 'client_loaded': bool(payload and payload.get('client_loaded'))})


def order_context(request, order):
    user = request.user
    master = order.master_id == user.pk and has_role(user, MASTER)
    actions = []
    if master and order.status == 'received': actions.append(('start', 'Начать диагностику'))
    if master and order.status == 'diagnosis': actions.append(('diagnosis', 'Сохранить диагностику и начать ремонт'))
    if master and order.status == 'repair':
        actions.extend([('work', 'Добавить работу'), ('part', 'Добавить деталь'), ('to_quality', 'Передать на контроль')])
    if has_role(user, MANAGER) and order.status in ('received', 'diagnosis', 'repair'): actions.insert(0, ('assign', 'Назначить мастера'))
    if has_role(user, QUALITY) and order.status == 'quality': actions.append(('quality', 'Провести контроль качества'))
    if has_role(user, RECEPTION) and order.status == 'ready':
        actions.extend([('payment', 'Зарегистрировать оплату'), ('issue', 'Выдать устройство')])
    return {'order': order, 'actions': actions, 'history': order.history.select_related('author'),
        'checks': order.checks.select_related('author'), 'notifications': order.history.select_related('notification'),
        'audit': order.auditevent_set.select_related('actor')[:20]}


@staff_required
def order_detail(request, pk):
    order = get_object_or_404(visible_orders(request.user), pk=pk)
    return render(request, 'repairs/detail.html', order_context(request, order))


ACTION_FORMS = {'assign': forms.AssignForm, 'start': forms.EmptyForm, 'diagnosis': forms.DiagnosisForm,
    'work': forms.WorkForm, 'part': forms.PartForm, 'to_quality': forms.EmptyForm, 'quality': forms.QualityForm,
    'payment': forms.PaymentForm, 'issue': forms.IssueForm, 'approve_estimate': forms.EstimateApprovalForm}
ACTION_TITLES = {'assign': 'Назначить мастера', 'start': 'Начать диагностику', 'diagnosis': 'Диагностика',
    'work': 'Добавить работу', 'part': 'Добавить деталь', 'to_quality': 'Передать на контроль', 'quality': 'Контроль качества',
    'payment': 'Зарегистрировать оплату', 'issue': 'Выдача устройства', 'approve_estimate': 'Согласование стоимости'}


@staff_required
def order_action(request, pk, action):
    if action == 'diagnosis' and not has_role(request.user, MASTER):
        raise PermissionDenied
    order = get_object_or_404(visible_orders(request.user), pk=pk)
    if action == 'diagnosis' and request.method == 'POST' and has_role(request.user, MASTER) and order.master_id == request.user.pk and order.status != 'diagnosis':
        return HttpResponse('Диагностика уже сохранена или этап изменён. Обновите карточку заказа.', status=409)
    if action not in dict(order_context(request, order)['actions']):
        raise PermissionDenied('Действие недоступно для вашей роли или текущего этапа.')
    if action == 'diagnosis':
        from .diagnostics import diagnosis_page
        return diagnosis_page(request, order)
    initial = {'amount': order.preliminary_total if action == 'approve_estimate' else max(order.balance, 0), 'estimate': order.estimate, 'due_date': order.due_date, 'diagnosis_price': Decimal('500')}
    payload = request.POST.copy() if request.method == 'POST' else None
    loading = bool(payload is not None and payload.get('load_catalog') and action in ('work', 'part'))
    if loading:
        model = WorkCatalogItem if action == 'work' else PriceItem
        item_id = payload.get('price_item', '')
        query = model.objects.filter(is_active=True)
        if action == 'part':
            query = query.filter(kind='part')
        item = query.filter(pk=item_id).first() if item_id.isdigit() else None
        if item:
            payload['description' if action == 'work' else 'name'] = item.name
            payload['cost' if action == 'work' else 'price'] = str(item.price)
    form = ACTION_FORMS[action](payload, initial=initial)
    catalog_choices = []
    if action in ('work', 'part'):
        catalog_choices = [{'id': item.pk, 'name': item.name, 'price': str(item.price)} for item in form.fields['price_item'].queryset]
    part_results = []
    if action == 'part':
        from .catalog_api import price_query
        if len(request.GET.get('part_q', '').strip()) >= 2:
            part_results = price_query({'q': request.GET['part_q'], 'kind': 'part'})[:10]
    status = 200
    if request.method == 'POST' and not loading and form.is_valid():
        try:
            raw_version = request.POST.get('version', '')
            if not raw_version.isascii() or not raw_version.isdigit() or len(raw_version) > 10:
                raise ValidationError('Некорректная версия заказа. Вернитесь в карточку и обновите страницу.')
            version = int(raw_version)
            execute(order.pk, request.user, action, form.cleaned_data, version)
        except (Conflict, OperationalError) as exc:
            form.add_error(None, str(exc) if isinstance(exc, Conflict) else 'База занята. Обновите карточку и проверьте результат перед повтором.')
            status = 409
        except ValidationError as exc:
            form.add_error(None, exc)
            status = 400
        else:
            messages.success(request, 'Изменения сохранены.' if action != 'payment' else 'Запись об оплате сохранена.')
            if not visible_orders(request.user).filter(pk=pk).exists():
                return redirect('orders')
            return redirect('order_detail', pk=pk)
    return render(request, 'repairs/form_page.html', {'form': form, 'title': ACTION_TITLES[action], 'subtitle': f'{order.number} · {order.device}',
        'button': ACTION_TITLES[action], 'order': order, 'version': request.POST.get('version', order.version), 'is_payment': action == 'payment', 'is_part': action == 'part', 'is_work': action == 'work', 'catalog_choices': catalog_choices, 'part_results': part_results}, status=status)


@staff_required
def price_list(request):
    if not has_role(request.user, RECEPTION, MASTER, MANAGER, ADMIN): raise PermissionDenied
    from .catalog_api import price_query
    from .models import DeviceCatalogItem
    items = list(price_query(request.GET).exclude(kind='work').prefetch_related('compatible_works'))
    works = WorkCatalogItem.objects.filter(is_active=True)
    q = request.GET.get('q', '').strip().casefold()
    if request.GET.get('model_id'):
        works = works.filter(device_models__pk=request.GET['model_id']) if request.GET['model_id'].isdigit() else works.none()
    if request.GET.get('category'):
        works = works.filter(device_models__category=request.GET['category']).distinct()
    if request.GET.get('kind') not in ('', 'work', None) or request.GET.get('group'):
        works = works.none()
    items += [{'name': w.name, 'price': w.price, 'get_kind_display': 'Работа', 'unit': 'усл.', 'sku': '', 'group': w.category.name}
              for w in works.select_related('category') if not q or q in w.name.casefold()]
    params = request.GET.copy()
    params.pop('page', None)
    return render(request, 'repairs/price_list.html', {
        'page_obj': Paginator(items, 50).get_page(request.GET.get('page')),
        'query': request.GET.get('q', ''), 'kind': request.GET.get('kind', ''),
        'category': request.GET.get('category', ''), 'group': request.GET.get('group', ''),
        'device_models': DeviceCatalogItem.objects.all(), 'model_id': request.GET.get('model_id', ''),
        'model_works': WorkCatalogItem.objects.filter(is_active=True, device_models__pk=request.GET['model_id']) if request.GET.get('model_id', '').isdigit() else [],
        'groups': PriceItem.objects.exclude(group='').values_list('group', flat=True).distinct().order_by('group'),
        'kinds': PriceItem.KIND, 'params': params.urlencode(),
        'categories': [('phone', 'Телефоны'), ('laptop', 'Ноутбуки'), ('appliance', 'Бытовая техника')]})


@staff_required
def clients(request):
    if not has_role(request.user, RECEPTION, MANAGER, ADMIN): raise PermissionDenied
    clients = Client.objects.all().annotate(total=Count('orders')).order_by('name', 'pk')
    q = request.GET.get('q', '').strip()
    if q: clients = clients.filter(Q(name__icontains=q) | Q(phone__icontains=q))
    params = request.GET.copy()
    params.pop('page', None)
    return render(request, 'repairs/clients.html', {'page_obj': Paginator(clients, 20).get_page(request.GET.get('page')), 'query': params.urlencode()})


@staff_required
def client_detail(request, pk):
    if not has_role(request.user, RECEPTION, MANAGER, ADMIN): raise PermissionDenied
    client = get_object_or_404(Client, pk=pk)
    return render(request, 'repairs/client.html', {'client': client, 'orders': visible_orders(request.user).filter(client=client)})


@staff_required
def device_detail(request, pk):
    allowed = visible_orders(request.user).filter(device_id=pk)
    if not allowed.exists(): raise PermissionDenied
    device = get_object_or_404(Device, pk=pk)
    return render(request, 'repairs/device.html', {'device': device, 'orders': allowed})


@staff_required
def masters(request):
    if not has_role(request.user, MANAGER): raise PermissionDenied
    users = User.objects.filter(groups__name=MASTER, is_active=True).annotate(active=Count('assigned_orders', filter=~Q(assigned_orders__status='issued')), overdue=Count('assigned_orders', filter=Q(assigned_orders__due_date__lt=timezone.localdate()) & ~Q(assigned_orders__status='issued')))
    return render(request, 'repairs/masters.html', {'masters': users})


def error403(request, exception=None):
    return render(request, 'error.html', {'code': '403', 'title': 'Недостаточно прав', 'description': 'Эта страница или операция недоступна вашей роли.'}, status=403)

def error404(request, exception=None):
    return render(request, 'error.html', {'code': '404', 'title': 'Страница не найдена', 'description': 'Проверьте ссылку или вернитесь к списку заказов.'}, status=404)

def error500(request):
    return render(request, 'error.html', {'code': '500', 'title': 'Не удалось открыть страницу', 'description': 'Попробуйте позже. Не повторяйте оплату без проверки результата.'}, status=500)
