import io
from django import forms
from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
import qrcode
from .models import RepairOrder
from .middleware import rate_limited
from .permissions import staff_required, visible_orders


class TrackForm(forms.Form):
    number = forms.CharField(label='Номер заказа', max_length=30, help_text='Например, АС-000001')
    code = forms.CharField(label='Секретный код доступа', max_length=64, widget=forms.PasswordInput(render_value=True), help_text='Находится в вашем заказ-наряде. Не сообщайте его посторонним.')


def public_data(order):
    return {'number': order.number, 'device': f'{order.device.manufacturer} {order.device.model}', 'status': order.status,
        'status_label': order.get_status_display(), 'due_date': order.due_date.isoformat() if order.due_date else None,
        'estimate': str(order.estimate) if order.estimate is not None else None,
        'total': str(order.final_total) if order.status in ('ready', 'issued') else None,
        'history': [{'status': h.new_status, 'label': h.get_new_status_display(), 'at': h.created_at.isoformat()} for h in order.history.all()]}


@never_cache
def track(request):
    form = TrackForm(request.POST or None)
    status = 200
    if request.method == 'POST':
        if rate_limited(request, 'track:', 15):
            form.add_error(None, 'Слишком много попыток. Повторите через 5 минут.')
            status = 429
        elif form.is_valid():
            number = form.cleaned_data['number'].upper().replace('АС-', '').lstrip('0') or '0'
            valid_number = number.isascii() and number.isdigit() and len(number) <= 18
            order = RepairOrder.objects.filter(pk=int(number), token=form.cleaned_data['code']).first() if valid_number else None
            if order:
                return redirect('public_status', token=order.token)
            form.add_error(None, 'Номер или код доступа не совпали. Проверьте заказ-наряд.')
    return render(request, 'public/track.html', {'form': form}, status=status)


@never_cache
def status_page(request, token):
    order = get_object_or_404(RepairOrder.objects.select_related('device').prefetch_related('history', 'works', 'parts'), token=token)
    return render(request, 'public/status.html', {'data': public_data(order), 'token': token})


@never_cache
def status_api(request, token):
    if rate_limited(request, 'public-api:', 120):
        return JsonResponse({'error': 'Слишком много запросов'}, status=429)
    order = get_object_or_404(RepairOrder.objects.select_related('device').prefetch_related('history', 'works', 'parts'), token=token)
    return JsonResponse(public_data(order))


@staff_required
def order_api(request, pk=None):
    orders = visible_orders(request.user)
    if pk:
        order = get_object_or_404(orders, pk=pk)
        return JsonResponse({'id': order.pk, 'number': order.number, 'status': order.status, 'master_id': order.master_id,
            'device': str(order.device), 'due_date': order.due_date, 'estimate': order.estimate, 'version': order.version})
    from .views import filtered_orders
    orders, _ = filtered_orders(request)
    from django.core.paginator import Paginator
    page = Paginator(orders, 50).get_page(request.GET.get('page'))
    return JsonResponse({'count': page.paginator.count, 'page': page.number, 'pages': page.paginator.num_pages,
        'results': [{'id': o.pk, 'number': o.number, 'status': o.status, 'device': str(o.device)} for o in page]})


def tracking_url(request, order):
    path = reverse('public_status', args=[order.token])
    return settings.PUBLIC_BASE_URL + path if settings.PUBLIC_BASE_URL else request.build_absolute_uri(path)


@staff_required
@never_cache
def qr_image(request, pk):
    order = get_object_or_404(visible_orders(request.user), pk=pk)
    image = qrcode.make(tracking_url(request, order))
    out = io.BytesIO()
    image.save(out, format='PNG')
    return HttpResponse(out.getvalue(), content_type='image/png')


@staff_required
@never_cache
def print_order(request, pk):
    order = get_object_or_404(visible_orders(request.user), pk=pk)
    return render(request, 'repairs/print.html', {'order': order, 'tracking_url': tracking_url(request, order)})
