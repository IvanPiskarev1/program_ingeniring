import io
import uuid
from datetime import timedelta
from decimal import Decimal
from django.core.cache import cache
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from repairs.models import Payment, RepairOrder
from .test_workflow import WorkflowFixture


class HttpFlowTests(WorkflowFixture):
    def setUp(self):
        super().setUp()
        cache.clear()
    def post_action(self, role, action, data=None):
        self.client.force_login(self.users[role])
        self.order.refresh_from_db()
        payload = dict(data or {}, version=self.order.version)
        url = reverse('order_action', args=[self.order.pk, action])
        self.assertEqual(self.client.get(url).status_code, 200)
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 302, response.content[:2000])
        self.assertEqual(self.client.get(response.url).status_code, 200)
        self.order.refresh_from_db()
    def test_form_pipeline_from_assignment_to_issue(self):
        self.post_action('Руководитель', 'assign', {'master':self.users['Мастер'].pk})
        self.post_action('Мастер', 'start')
        self.post_action('Мастер', 'diagnosis', {'result':'Неисправен разъём','category':self.category.pk,'required_parts':'Разъём','estimate':'2400.00','due_date':timezone.localdate().isoformat()})
        self.post_action('Мастер', 'work', {'description':'Пайка разъёма','minutes':30,'cost':'1500.00'})
        self.post_action('Мастер', 'part', {'name':'Разъём','quantity':2,'price':'250.00'})
        self.post_action('Мастер', 'to_quality')
        self.post_action('Контроль качества','quality', {'passed':'no','comment':'Повторная проверка контакта'})
        self.assertEqual(self.order.status,'repair')
        self.assertEqual(self.client.get(reverse('order_detail',args=[self.order.pk])).status_code,404)
        self.post_action('Мастер','work',{'description':'Доработка контакта','minutes':10,'cost':'0'})
        self.post_action('Мастер','to_quality')
        self.post_action('Контроль качества','quality', {'passed':'yes','comment':'Функциональный тест пройден'})
        self.post_action('Приём','payment',{'request_key':str(uuid.uuid4()),'amount':'2000.00','method':'card'})
        self.post_action('Приём','issue',{'issue_method':'Лично владельцу','free_reason':''})
        self.assertEqual(self.order.status,'issued')
        self.assertEqual(self.order.final_total,Decimal('2000'))
        self.assertEqual(self.order.history.count(),8)
    def test_forged_version_and_long_order_number(self):
        self.ready()
        self.client.force_login(self.users['Приём'])
        response = self.client.post(reverse('order_action',args=[self.order.pk,'payment']),{'version':'bad','request_key':uuid.uuid4(),'amount':'100','method':'cash'})
        self.assertEqual(response.status_code,400)
        self.assertEqual(Payment.objects.count(),0)
        self.assertEqual(self.client.get(reverse('orders'), {'q':'9'*200}).status_code,200)
        self.assertEqual(self.client.post(reverse('track'), {'number':'9'*30,'code':'wrong'}).status_code,200)
    def test_same_payment_key_with_new_version_is_rejected(self):
        self.ready()
        data = {'amount':Decimal('1000'),'method':'cash','request_key':uuid.uuid4()}
        self.act('payment',data,'Приём')
        from repairs.services.orders import Conflict
        with self.assertRaises(Conflict): self.act('payment',data,'Приём')
        self.assertEqual(Payment.objects.count(),1)
        self.assertEqual(self.order.paid_total,Decimal('1000'))
    def test_free_issue_requires_reason(self):
        self.ready()
        self.order.works.update(cost=0); self.order.parts.update(price=0)
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError): self.act('issue',{'issue_method':'Лично','free_reason':''},'Приём')
        self.act('issue',{'issue_method':'Лично','free_reason':'Учебная бесплатная диагностика'},'Приём')
        self.assertEqual(self.order.status,'issued')
    def test_public_pages_errors_and_rate_limit(self):
        self.assertEqual(self.client.get('/').status_code,200)
        self.assertEqual(self.client.get(reverse('track')).status_code,200)
        for _ in range(15): self.client.post(reverse('track'),{'number':'1','code':'wrong'})
        self.assertEqual(self.client.post(reverse('track'),{'number':'1','code':'wrong'}).status_code,429)
        cache.clear()
        for _ in range(20): self.client.post(reverse('login'),{'username':'unknown','password':'wrong'})
        self.assertEqual(self.client.post(reverse('login'),{'username':'unknown','password':'wrong'}).status_code,429)
        with self.settings(DEBUG=False):
            self.assertEqual(self.client.get('/missing-page/').status_code,404)
    def test_report_duration_known_timeline(self):
        self.ready()
        self.act('payment',{'amount':Decimal('2000'),'method':'cash','request_key':uuid.uuid4()},'Приём')
        self.act('issue',{'issue_method':'Лично','free_reason':''},'Приём')
        now=timezone.now()
        RepairOrder.objects.filter(pk=self.order.pk).update(created_at=now-timedelta(days=4),issued_at=now)
        times={'received':now-timedelta(days=4),'diagnosis':now-timedelta(days=3),'repair':now-timedelta(hours=26),'quality':now-timedelta(hours=2),'ready':now-timedelta(hours=1),'issued':now}
        for item in self.order.history.all():
            item.created_at=times[item.new_status];item.save(update_fields=['created_at'])
        from repairs.services.reports import report_data
        data=report_data(timezone.localdate(),timezone.localdate())
        self.assertEqual(data['issued'],1)
        self.assertEqual(data['received'],0)
        self.assertEqual(data['average_days'],4)
        self.assertEqual(data['repair_hours'],24)
