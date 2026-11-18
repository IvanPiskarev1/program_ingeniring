"""Transactional outbox. SMTP acceptance is not confirmation of delivery."""
import smtplib
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.core.validators import validate_email
from django.db.models import F, Q
from django.utils import timezone

from repairs.models import Client, Notification


def enqueue(event, order):
    client = order.client
    recipient = client.email.strip()
    enabled = client.email_notifications and bool(recipient)
    text = (f'Заказ {order.number}\n'
            f'Новый статус: {order.get_status_display()}.\n\n'
            'АСУИ Сервисный центр')
    return Notification.objects.create(
        event=event, channel='email', recipient=recipient if enabled else '',
        text=text, state='pending' if enabled else 'skipped',
        error='' if enabled else 'Нет адреса почты или согласия клиента.')


def process_queue(limit=50):
    now = timezone.now()
    ids = list(Notification.objects.filter(
        channel='email', state__in=['pending', 'error'], attempts__lt=3,
    ).filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now))
        .order_by('pk').values_list('pk', flat=True)[:limit])
    total = 0
    for pk in ids:
        # Atomic claim prevents two workers from sending the same event.
        claimed = Notification.objects.filter(pk=pk, state__in=['pending', 'error'], attempts__lt=3).update(
            state='sending', attempts=F('attempts') + 1)
        if not claimed:
            continue
        item = Notification.objects.select_related('event__order').get(pk=pk)
        client = Client.objects.get(pk=item.event.order.client_id)
        try:
            validate_email(item.recipient)
        except ValidationError:
            finish(item, 'skipped', 'Некорректный адрес почты.')
            continue
        # Consent revocation or address change invalidates queued messages.
        if not client.email_notifications or client.email.strip() != item.recipient:
            finish(item, 'skipped', 'Адрес или согласие клиента изменились.')
            continue
        try:
            message = EmailMessage(
                subject=f'АСУИ: статус заказа {item.event.order.number}',
                body=item.text, from_email=settings.DEFAULT_FROM_EMAIL,
                to=[item.recipient],
                headers={'Message-ID': f'<asui-status-{item.event_id}@service.center.asui.gmail.com>'})
            if message.send(fail_silently=False) != 1:
                finish(item, 'error', 'Сервер не принял письмо.')
            else:
                Notification.objects.filter(pk=pk).update(
                    state='sent', error='', sent_at=timezone.now(), next_attempt_at=None)
                total += 1
        except smtplib.SMTPAuthenticationError:
            finish(item, 'error', 'Gmail отклонил авторизацию. Проверьте пароль приложения.')
        except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused, smtplib.SMTPDataError):
            finish(item, 'error', 'Почтовый сервер отклонил письмо.')
        except Exception:
            # A disconnect after DATA may mean accepted mail. Never blindly resend.
            finish(item, 'unknown', 'Связь прервана. Результат неизвестен; автоматического повтора нет.')
    return total


def finish(item, state, error):
    Notification.objects.filter(pk=item.pk).update(
        state=state, error=error,
        next_attempt_at=timezone.now() + timedelta(minutes=5 * item.attempts))
