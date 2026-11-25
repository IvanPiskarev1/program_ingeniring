from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import OperationalError
from django.shortcuts import render, redirect
from .forms import DiagnosisForm
from .diagnostic_items import DiagnosticItemFormSet
from .catalog_api import price_query, works_query
from .models import PriceItem, WorkCatalogItem
from .services.orders import execute, Conflict


def diagnosis_page(request, order):
    payload = request.POST.copy() if request.method == 'POST' else None
    if payload is not None and not any(key.startswith('items-') for key in payload):
        payload.update({'items-TOTAL_FORMS': '0', 'items-INITIAL_FORMS': '0'})
    removing = payload is not None and 'remove_row' in payload
    editing = bool(payload is not None and (payload.get('add_manual') or payload.get('add_catalog') or payload.get('lookup') or removing))
    if removing:
        try:
            count = int(payload.get('items-TOTAL_FORMS', '0'))
            index = int(payload.get('remove_row', ''))
        except ValueError:
            count, index = -1, -1
        if 0 <= index < count <= 100:
            rows = [{key: payload.get(f'items-{i}-{key}', '')
                     for key in ('kind', 'catalog_id', 'name', 'quantity', 'price')}
                    for i in range(count) if i != index]
            for key in list(payload):
                if key.startswith('items-'):
                    del payload[key]
            payload.update({'items-TOTAL_FORMS': str(len(rows)), 'items-INITIAL_FORMS': '0'})
            if not any(row.get('name', '').strip() or row.get('catalog_id') or row.get('price') for row in rows):
                payload['estimate'] = '0'
            for i, row in enumerate(rows):
                for key, value in row.items():
                    payload[f'items-{i}-{key}'] = value
    if editing and not payload.get('lookup') and not removing:
        try:
            count = int(payload.get('items-TOTAL_FORMS', '0'))
        except ValueError:
            count = -1
        if 0 <= count < 100:
            row = {'kind': 'part', 'quantity': '1'}
            choice = payload.get('add_catalog', '').split(':')
            if len(choice) == 2 and choice[0] in ('part', 'work') and choice[1].isdigit():
                model = PriceItem if choice[0] == 'part' else WorkCatalogItem
                query = model.objects.filter(pk=choice[1], is_active=True)
                if choice[0] == 'part':
                    query = query.filter(kind='part')
                item = query.first()
                if item:
                    row.update(kind=choice[0], catalog_id=str(item.pk), name=item.name, price=str(item.price))
            for key, value in row.items():
                payload[f'items-{count}-{key}'] = value
            payload['items-TOTAL_FORMS'] = str(count + 1)
    formset = DiagnosticItemFormSet(payload, prefix='items')
    if payload is not None and formset.is_valid():
        rows = [row for row in formset.cleaned_data if row and not row.get('empty')]
        if rows:
            payload['estimate'] = str(sum(row['quantity'] * row['price'] for row in rows))
    form = DiagnosisForm(payload, initial={'due_date': order.due_date, 'diagnosis_price': 500})
    status = 200
    if payload is not None and not editing:
        valid = form.is_valid()
        rows_valid = formset.is_valid()
        if valid and rows_valid:
            try:
                raw = payload.get('version', '')
                if not raw.isascii() or not raw.isdigit() or len(raw) > 10:
                    raise ValidationError('Некорректная версия заказа. Обновите страницу.')
                data = dict(form.cleaned_data)
                data['items'] = [row for row in formset.cleaned_data if row and not row.get('empty')]
                execute(order.pk, request.user, 'diagnosis', data, int(raw))
            except (Conflict, OperationalError):
                form.add_error(None, 'Заказ изменён или база занята. Обновите карточку и проверьте результат.')
                status = 409
            except ValidationError as exc:
                form.add_error(None, exc)
                status = 400
            else:
                messages.success(request, 'Диагностика сохранена.')
                return redirect('order_detail', pk=order.pk)
        else:
            status = 400
    from .models import DeviceCatalogItem
    catalog = DeviceCatalogItem.objects.filter(kind=order.device.kind, manufacturer=order.device.manufacturer, model=order.device.model).first()
    model_id = str(catalog.pk) if catalog else ''
    parts = PriceItem.objects.filter(kind='part', is_active=True)
    works = WorkCatalogItem.objects.filter(is_active=True)
    if catalog:
        parts = parts.filter(device_models=catalog)
        works = works.filter(device_models=catalog)
    catalog_choices = {kind: [{'id': item.pk, 'name': item.name, 'price': str(item.price)} for item in query]
                       for kind, query in [('part', parts), ('work', works)]}
    search = payload if payload is not None else request.GET
    q = search.get('q', '').strip()
    kind = search.get('kind', 'part')
    results = []
    if len(q) >= 2:
        query = works_query(q, model_id) if kind == 'work' else price_query({'q': q, 'kind': 'part', 'model_id': model_id})
        results = query[:10]
    return render(request, 'repairs/diagnostics.html', {'form': form, 'formset': formset, 'order': order,
        'version': payload.get('version', order.version) if payload is not None else order.version,
        'catalog_choices': catalog_choices, 'search_results': results, 'search_kind': kind, 'search_q': q, 'catalog_model_id': model_id}, status=status)
