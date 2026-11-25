from functools import wraps
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from .models import Client, PriceItem
from .permissions import has_role, RECEPTION, MASTER, MANAGER, ADMIN
from .intake_data import client_fields, client_devices, device_fields, phone_key


def restricted(*roles):
    def decorate(view):
        @never_cache
        @require_GET
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not has_role(request.user, *roles):
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return wrapped
    return decorate


@restricted(RECEPTION)
def client_search(request):
    q = request.GET.get('q', '').strip()[:160]
    results = []
    if len(q) >= 2:
        needle = q.casefold()
        digits = phone_key(q)
        # SQLite's LIKE is not case-insensitive for Cyrillic. Keep this small
        # local directory search explicit and normalize formatted phones too.
        for client in Client.objects.order_by('name', 'pk').iterator():
            if (needle in client.name.casefold() or needle in client.email.casefold()
                    or (len(digits) >= 2 and digits in phone_key(client.phone))):
                results.append({'id': client.pk, 'label': f'{client.name} · {client.phone}'})
                if len(results) == 10:
                    break
    return JsonResponse({'results': results})


@restricted(RECEPTION)
def client_info(request, pk):
    return JsonResponse(client_fields(get_object_or_404(Client, pk=pk)))


@restricted(RECEPTION)
def devices(request, pk):
    client = get_object_or_404(Client, pk=pk)
    return JsonResponse({'results': [device_fields(d, client) for d in client_devices(client)]})


@restricted(RECEPTION)
def device_models(request):
    from .models import DeviceCatalogItem
    return JsonResponse({'results': [{'id': m.pk, 'label': str(m), 'device_type': m.kind_id,
        'manufacturer': m.manufacturer, 'device_model': m.model} for m in DeviceCatalogItem.objects.all()]})


def price_query(params):
    items = PriceItem.objects.filter(is_active=True)
    q = params.get('q', '').strip()[:180]
    if q:
        # Casefold also supports Russian names on SQLite.
        ids = [pk for pk, name, sku in items.values_list('pk', 'name', 'sku')
               if q.casefold() in name.casefold() or q.casefold() in (sku or '').casefold()]
        items = items.filter(pk__in=ids)
    if params.get('model_id'):
        items = items.filter(device_models__pk=params['model_id']) if str(params['model_id']).isdigit() else items.none()
    for field in ('kind', 'category', 'group'):
        if params.get(field):
            items = items.filter(**{field: params[field]})
    return items.order_by('kind', 'name', 'pk')


def works_query(q, model_id=None):
    from .models import WorkCatalogItem
    q = q.strip()[:180].casefold()
    if len(q) < 2:
        return WorkCatalogItem.objects.none()
    ids = [pk for pk, name in WorkCatalogItem.objects.filter(is_active=True).values_list('pk', 'name') if q in name.casefold()]
    items = WorkCatalogItem.objects.filter(pk__in=ids)
    if model_id:
        items = items.filter(device_models__pk=model_id) if str(model_id).isdigit() else items.none()
    return items.order_by('name', 'pk')


@restricted(RECEPTION, MASTER, MANAGER, ADMIN)
def works_search(request):
    return JsonResponse({'results': [{'id': p.pk, 'label': f'{p.name} · {p.price} ₽',
                                     'name': p.name, 'price': str(p.price)} for p in works_query(request.GET.get('q', ''), request.GET.get('model_id'))[:10]]})


@restricted(RECEPTION, MASTER, MANAGER, ADMIN)
def parts_search(request):
    q = request.GET.get('q', '').strip()
    items = price_query(request.GET).filter(kind='part')[:10] if len(q) >= 2 else []
    return JsonResponse({'results': [{'id': p.pk, 'label': f'{p.sku or ""} · {p.name} · {p.price} ₽',
                                     'name': p.name, 'price': str(p.price)} for p in items]})
