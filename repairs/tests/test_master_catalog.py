from decimal import Decimal
from django.urls import reverse
from repairs.models import PriceItem, WorkCatalogItem
from .test_workflow import WorkflowFixture


class MasterCatalogTests(WorkflowFixture):
    def setUp(self):
        super().setUp()
        self.repair()
        self.client.force_login(self.users['Мастер'])
        self.work = WorkCatalogItem.objects.create(name='Замена разъёма питания', category=self.category, price=1250)
        self.part = PriceItem.objects.create(kind='part', name='Разъём питания Lenovo', price=450)
        PriceItem.objects.create(kind='work', name='Старая работа', price=99)

    def test_work_uses_same_catalog_as_price_and_server_snapshot(self):
        url = reverse('order_action', args=[self.order.pk, 'work'])
        response = self.client.get(url)
        self.assertContains(response, self.work.name)
        self.assertNotContains(response, 'Старая работа')
        self.assertContains(self.client.get(reverse('price_list'), {'kind': 'work'}), self.work.name)
        data = {'price_item': self.work.pk, 'description': 'Подмена', 'cost': 1,
                'minutes': 30, 'version': self.order.version}
        self.assertEqual(self.client.post(url, data).status_code, 302)
        work = self.order.works.latest('pk')
        self.assertEqual((work.description, work.cost), (self.work.name, Decimal('1250')))
        self.assertEqual(self.client.post(url, data).status_code, 409)

    def test_catalog_only_and_without_js_loading(self):
        for action, item, name, price in [('work', self.work, 'description', 'cost'), ('part', self.part, 'name', 'price')]:
            url = reverse('order_action', args=[self.order.pk, action])
            data = {'price_item': item.pk, 'quantity': 2, 'minutes': 15, 'version': self.order.version, 'load_catalog': '1'}
            response = self.client.post(url, data)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context['form'][name].value(), item.name)
            self.assertEqual(Decimal(response.context['form'][price].value()), item.price)
            self.order.refresh_from_db()
            del data['load_catalog']
            data['version'] = self.order.version
            self.assertEqual(self.client.post(url, data).status_code, 302)
            self.order.refresh_from_db()
        self.assertEqual(self.order.final_total, 4650)

    def test_inactive_and_permissions(self):
        url = reverse('order_action', args=[self.order.pk, 'work'])
        self.work.is_active = False
        self.work.save()
        data = {'price_item': self.work.pk, 'minutes': 1, 'version': self.order.version}
        self.assertEqual(self.client.post(url, data).status_code, 200)
        self.client.force_login(self.users['Приём'])
        self.assertEqual(self.client.post(url, data).status_code, 403)
        self.order.master = None
        self.order.save()
        self.client.force_login(self.users['Мастер'])
        self.assertEqual(self.client.get(url).status_code, 404)
