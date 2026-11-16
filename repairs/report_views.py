import csv
import io
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from openpyxl import Workbook
from .forms import ReportForm
from .permissions import MANAGER, has_role, staff_required
from .services.reports import report_data


def text_cell(value):
    value = str(value)
    return "'" + value if value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r', '\n')) else value


@staff_required
def reports(request):
    if not has_role(request.user, MANAGER): raise PermissionDenied
    today = timezone.localdate()
    form = ReportForm(request.GET if request.GET else {'start': today.replace(day=1), 'end': today})
    data = None
    if form.is_valid():
        start = form.cleaned_data['start'] or today.replace(day=1)
        end = form.cleaned_data['end'] or today
        data = report_data(start, end)
        data['registered_payments'] = data['demo_revenue'] + data['real_revenue']
        if request.GET.get('format') in ('csv', 'xlsx'):
            rows = [['Отчёт АСУИ', f'{start} — {end}'], ['Принято заказов', data['received']], ['Выдано заказов', data['issued']],
                ['Средний полный цикл, дней', data['average_days'] if data['average_days'] is not None else 'Нет данных'],
                ['Время в ремонте, часов', data['repair_hours'] if data['repair_hours'] is not None else 'Нет данных'],
                ['Зарегистрировано оплат, ₽', str(data['demo_revenue'] + data['real_revenue'])],
                [], ['Мастер', 'Активные заказы (сейчас)', 'Просрочено (сейчас)']]
            rows += [[text_cell(m['user'].get_full_name() or m['user'].username), m['active'], m['overdue']] for m in data['masters']]
            rows += [[], ['Категория неисправности', 'Принято за период']]
            rows += [[text_cell(f['diagnosis__category__name']), f['total']] for f in data['faults']]
            rows += [[], ['Номер', 'Изделие', 'Статус', 'Принято']]
            rows += [[o.number, text_cell(str(o.device)), o.get_status_display(), o.created_at.isoformat()] for o in data['orders']]
            if request.GET['format'] == 'csv':
                response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
                response.write('\ufeff')
                writer = csv.writer(response, delimiter=';')
                writer.writerows(rows)
            else:
                book = Workbook()
                sheet = book.active
                sheet.title = 'Отчёт АСУИ'
                for row in rows: sheet.append(row)
                sheet.column_dimensions['A'].width = 42
                sheet.column_dimensions['B'].width = 44
                sheet.column_dimensions['C'].width = 24
                stream = io.BytesIO()
                book.save(stream)
                response = HttpResponse(stream.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            response['Content-Disposition'] = f'attachment; filename="asui-report.{request.GET["format"]}"'
            return response
    return render(request, 'repairs/reports.html', {'form': form, 'report': data, 'query': request.GET.urlencode()})
