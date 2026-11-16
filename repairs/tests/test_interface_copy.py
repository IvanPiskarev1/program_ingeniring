import uuid
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from repairs.models import AuditEvent, Notification
from .test_workflow import WorkflowFixture


class InterfaceCopyTests(WorkflowFixture):
    def assert_neutral_copy(self, response):
        self.assertEqual(response.status_code, 200)
        import re
        from django.utils.html import strip_tags
        html = response.content.decode('utf-8')
        # Access tokens are random data, not interface wording.
        html = re.sub(r'<code\b[^>]*>.*?</code>', '', html, flags=re.S)
        text = strip_tags(html).lower()
        for phrase in ('учебн', 'sms', 'смс', 'push', 'пуш', 'не подключен', 'не отправлено'):
            self.assertNotIn(phrase, text)

    def test_public_and_staff_pages(self):
        for url in ('/', reverse('track'), reverse('login')):
            self.assert_neutral_copy(self.client.get(url))
        self.ready()
        # Historical records stay intact, but the obsolete notification UI is hidden.
        Notification.objects.update(text='Учебное уведомление', state='test')
        AuditEvent.objects.create(actor=self.users['Приём'], order=self.order, action='Учебная оплата: 100 ₽')
        self.client.force_login(self.users['Приём'])
        for url in (reverse('dashboard'), reverse('orders'),
                    reverse('order_detail', args=[self.order.pk]),
                    reverse('print_order', args=[self.order.pk]),
                    reverse('order_action', args=[self.order.pk, 'payment'])):
            self.assert_neutral_copy(self.client.get(url))
        self.assertTrue(Notification.objects.filter(state='test').exists())
        self.assertTrue(AuditEvent.objects.filter(action='Учебная оплата: 100 ₽').exists())

    def test_payment_copy_and_report_keep_cents(self):
        self.ready()
        self.client.force_login(self.users['Приём'])
        response = self.client.post(reverse('order_action', args=[self.order.pk, 'payment']), {
            'version': self.order.version, 'request_key': uuid.uuid4(),
            'amount': '123.45', 'method': 'cash'}, follow=True)
        self.assert_neutral_copy(response)
        self.assertContains(response, 'Запись об оплате сохранена.')
        self.assertEqual(self.order.payments.get().amount, Decimal('123.45'))
        self.client.force_login(self.users['Руководитель'])
        today = timezone.localdate().isoformat()
        response = self.client.get(reverse('reports'), {'start': today, 'end': today})
        self.assert_neutral_copy(response)
        self.assertEqual(response.context['report']['registered_payments'], Decimal('123.45'))
        self.assertContains(response, '123,45')
        response = self.client.get(reverse('reports'), {'start': today, 'end': today, 'format': 'csv'})
        self.assert_neutral_copy(response)
        self.assertIn('123.45', response.content.decode('utf-8-sig'))
