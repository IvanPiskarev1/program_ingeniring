from decimal import Decimal
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from ..models import AuditEvent, Diagnosis, EstimateRevision, Notification, NotificationTemplate, Payment, QualityCheck, RepairOrder, StatusHistory
from ..permissions import MANAGER, MASTER, QUALITY, RECEPTION, has_role


class Conflict(ValidationError):
    pass


def audit(order, actor, action):
    AuditEvent.objects.create(actor=actor, order=order, action=action)


def event(order, actor, old='', comment=''):
    item = StatusHistory.objects.create(order=order, old_status=old, new_status=order.status, author=actor, comment=comment)
    from .email_notifications import enqueue
    enqueue(item, order)


def require(user, *roles):
    if not has_role(user, *roles):
        raise PermissionDenied('У вашей роли нет права на это действие.')


@transaction.atomic
def execute(order_id, actor, action, data, version):
    """All mutations use a versioned conditional UPDATE, including SQLite.

    The CAS obtains SQLite's write lock before related inserts. Stale requests
    roll back without duplicate payments, works or status events.
    """
    updated = RepairOrder.objects.filter(pk=order_id, version=version).update(version=F('version') + 1)
    if not updated:
        raise Conflict('Заказ уже изменён. Обновите страницу и проверьте результат.')
    order = RepairOrder.objects.select_related('master').get(pk=order_id)
    S = RepairOrder.Status
    master_actions = {'start', 'diagnosis', 'work', 'part', 'to_quality'}
    if action in master_actions:
        require(actor, MASTER)
        if order.master_id != actor.pk:
            raise PermissionDenied('Действие доступно только назначенному мастеру.')
    old = order.status
    if action == 'assign':
        require(actor, MANAGER)
        if order.status not in (S.RECEIVED, S.DIAGNOSIS, S.REPAIR):
            raise ValidationError('Назначение доступно до передачи на контроль.')
        master = data['master']
        if not master.is_active or not has_role(master, MASTER):
            raise ValidationError('Выберите активного мастера.')
        order.master = master
        audit(order, actor, f'Назначен мастер: {master.get_full_name() or master.username}')
    elif action == 'start':
        expect(order, S.RECEIVED)
        order.status = S.DIAGNOSIS
    elif action == 'diagnosis':
        expect(order, S.DIAGNOSIS)
        diag_price = data.get('diagnosis_price')
        if diag_price is None:
            diag_price = Decimal('500')
        from ..diagnostic_items import validate_items
        from ..models import RepairWork, UsedPart
        rows = validate_items(data.get('items', []))
        if diag_price < 0 or data['estimate'] < 0:
            raise ValidationError('Стоимость не может быть отрицательной.')
        Diagnosis.objects.create(order=order, author=actor, result=data['result'], category=data['category'], required_parts=data.get('required_parts', ''), price=diag_price)
        for row in rows:
            if row['kind'] == 'part':
                UsedPart.objects.create(order=order, name=row['name'], quantity=row['quantity'], price=row['price'])
            else:
                RepairWork.objects.create(order=order, author=actor, description=row['name'], quantity=row['quantity'], cost=row['price'] * row['quantity'])
        order.due_date = data.get('due_date')
        order.estimate = (sum((row['price'] * row['quantity'] for row in rows), Decimal('0')) if rows else data['estimate']) + diag_price
        EstimateRevision.objects.create(order=order, amount=order.estimate, reason='Первоначальная оценка после диагностики', author=actor)
        order.status = S.REPAIR
    elif action == 'approve_estimate':
        require(actor, RECEPTION, MANAGER)
        if not hasattr(order, 'diagnosis') or order.status == S.ISSUED:
            raise ValidationError('Согласование доступно после диагностики и до выдачи.')
        amount = data['amount']
        if amount < order.preliminary_total:
            raise ValidationError('Согласованная сумма не может быть меньше текущей предварительной стоимости.')
        order.approved_estimate = amount
        order.estimate_approved_at = timezone.now()
        order.estimate_approved_by = actor
        order.estimate_approval_note = data.get('note', '').strip()
        audit(order, actor, f'Согласована стоимость: {amount} ₽')
    elif action in ('work', 'part'):
        expect(order, S.REPAIR)
        from ..models import RepairWork, UsedPart, PriceItem, WorkCatalogItem
        data = dict(data)
        if data.get('price_item'):
            catalog = PriceItem.objects.filter(kind='part') if action == 'part' else WorkCatalogItem.objects.all()
            item = catalog.filter(pk=data['price_item'].pk, is_active=True).first()
            if not item:
                raise ValidationError('Позиция прайс-листа недоступна.')
            data['name' if action == 'part' else 'description'] = item.name
            data['price' if action == 'part' else 'cost'] = item.price
        if action == 'work':
            RepairWork.objects.create(order=order, author=actor, description=data['description'], minutes=data['minutes'], cost=data['cost'])
            revision_reason = f"Добавлена работа: {data['description']}"
        else:
            UsedPart.objects.create(order=order, name=data['name'], quantity=data['quantity'], price=data['price'])
            revision_reason = f"Добавлена деталь: {data['name']}"
        EstimateRevision.objects.create(order=order, amount=order.final_total, reason=revision_reason, author=actor)
        audit(order, actor, 'Добавлена работа' if action == 'work' else 'Добавлена деталь')
    elif action == 'to_quality':
        expect(order, S.REPAIR)
        last_return = order.history.filter(old_status=S.QUALITY, new_status=S.REPAIR).last()
        works = order.works.all()
        if last_return:
            works = works.filter(created_at__gt=last_return.created_at)
        if not works.exists():
            raise ValidationError('Добавьте выполненную работу, в том числе после возврата на доработку.')
        order.status = S.QUALITY
    elif action == 'quality':
        require(actor, QUALITY)
        expect(order, S.QUALITY)
        if not data['comment'].strip():
            raise ValidationError('Укажите заключение контроля качества.')
        QualityCheck.objects.create(order=order, author=actor, passed=data['passed'], comment=data['comment'])
        order.status = S.READY if data['passed'] else S.REPAIR
    elif action == 'payment':
        require(actor, RECEPTION)
        expect(order, S.READY)
        if Payment.objects.filter(request_key=data['request_key']).exists():
            raise Conflict('Эта операция оплаты уже зарегистрирована. Проверьте историю расчётов.')
        amount = data['amount']
        if amount <= 0 or amount > order.balance:
            raise ValidationError('Оплата должна быть больше нуля и не превышать остаток.')
        Payment.objects.create(order=order, author=actor, amount=amount, method=data['method'], request_key=data['request_key'])
        audit(order, actor, f'Регистрация оплаты: {amount} ₽')
    elif action == 'issue':
        require(actor, RECEPTION)
        expect(order, S.READY)
        if order.balance != Decimal('0'):
            raise ValidationError('Перед выдачей полностью зарегистрируйте оплату.')
        if order.final_total == 0 and not data['free_reason'].strip():
            raise ValidationError('Укажите причину бесплатного ремонта.')
        order.free_reason = data['free_reason']
        order.issue_method = data['issue_method']
        order.issued_at = timezone.now()
        order.issued_by = actor
        order.status = S.ISSUED
    else:
        raise ValidationError('Неизвестное действие.')
    order.save()
    if old != order.status:
        event(order, actor, old, data.get('comment', ''))
        audit(order, actor, f'{dict(S.choices)[old]} → {order.get_status_display()}')
    return order


def expect(order, status):
    if order.status != status:
        raise Conflict('Действие недоступно на текущем этапе. Обновите страницу.')
