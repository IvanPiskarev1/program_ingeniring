import io
import uuid
from django.core.management import call_command
from repairs.models import Device, DeviceCatalogItem, PriceItem, WorkCatalogItem, RepairOrder
from .test_workflow import WorkflowFixture


class DeviceCatalogTests(WorkflowFixture):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        call_command('seed_parts_catalog', stdout=io.StringIO())
        call_command('seed_works_catalog', stdout=io.StringIO())
        call_command('seed_device_catalog', stdout=io.StringIO())

    def test_coverage_and_idempotence_preserves_data(self):
        self.assertGreaterEqual(DeviceCatalogItem.objects.count(), 54)
        self.assertFalse(DeviceCatalogItem.objects.filter(parts=None).exists())
        self.assertFalse(DeviceCatalogItem.objects.filter(works=None).exists())
        entry = DeviceCatalogItem.objects.get(manufacturer=self.device.manufacturer, model=self.device.model)
        self.assertTrue(entry.parts.exists())
        for part in entry.parts.all():
            self.assertTrue(part.compatible_works.exists())
        before = list(PriceItem.objects.values_list('pk', 'name', 'price'))
        counts = (DeviceCatalogItem.objects.count(), WorkCatalogItem.objects.count(), Device.objects.count(), RepairOrder.objects.count())
        call_command('seed_device_catalog', stdout=io.StringIO())
        self.assertEqual(before, list(PriceItem.objects.values_list('pk', 'name', 'price')))
        self.assertEqual(counts, (DeviceCatalogItem.objects.count(), WorkCatalogItem.objects.count(), Device.objects.count(), RepairOrder.objects.count()))

    def test_api_permissions_and_no_serial_or_client_data(self):
        for role in (None, 'Мастер', 'Контроль качества', 'Руководитель'):
            self.client.logout()
            if role:
                self.client.force_login(self.users[role])
            self.assertEqual(self.client.get('/api/device-models/').status_code, 403)
        self.client.force_login(self.users['Приём'])
        response = self.client.get('/api/device-models/')
        self.assertIn('no-store', response['Cache-Control'])
        self.assertGreaterEqual(len(response.json()['results']), 54)
        self.assertNotIn('serial', response.content.decode())
        self.assertNotIn('token', response.content.decode())

    def test_model_intake_no_js_and_server_values(self):
        self.client.force_login(self.users['Приём'])
        model = DeviceCatalogItem.objects.get(manufacturer='Apple', model='iPhone 12')
        data = {'request_key': str(uuid.uuid4()), 'existing_client': self.customer.pk, 'kind': 'person',
                'catalog_model': model.pk, 'problem': 'Не включается', 'serial': 'MANUFACTURER-SERIAL',
                'manufacturer': 'Подмена', 'device_model': 'Подмена', 'accessories': 'Кабель клиента'}
        loaded = self.client.post('/orders/new/', dict(data, load_existing='catalog_model'))
        self.assertEqual(loaded.context['form'].initial['manufacturer'], 'Apple')
        self.assertEqual(loaded.context['form'].initial['serial'], '')
        self.assertEqual(loaded.context['form'].initial['accessories'], 'Кабель клиента')
        response = self.client.post('/orders/new/', data)
        self.assertEqual(response.status_code, 302)
        order = RepairOrder.objects.get(request_key=data['request_key'])
        self.assertEqual(order.device.manufacturer, 'Apple')
        self.assertEqual(order.device.model, 'iPhone 12')
        self.assertEqual(order.device.serial, 'MANUFACTURER-SERIAL')
        self.client.post('/orders/new/', data)
        self.assertEqual(RepairOrder.objects.filter(request_key=data['request_key']).count(), 1)

    def test_conflicting_existing_device_and_catalog_rejected(self):
        self.client.force_login(self.users['Приём'])
        model = DeviceCatalogItem.objects.get(manufacturer='Apple', model='iPhone 12')
        response = self.client.post('/orders/new/', {'request_key': str(uuid.uuid4()), 'existing_client': self.customer.pk,
            'existing_device': self.device.pk, 'catalog_model': model.pk, 'kind': 'person', 'problem': 'Нет питания'})
        self.assertContains(response, 'не оба варианта одновременно')
        self.assertEqual(RepairOrder.objects.count(), 1)

    def test_model_price_and_search_filters(self):
        self.client.force_login(self.users['Мастер'])
        model = DeviceCatalogItem.objects.get(manufacturer='Apple', model='iPhone 12')
        response = self.client.get('/price/', {'model_id': model.pk, 'kind': 'part'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.context['page_obj'].object_list), set(model.parts.all()))
        parts = self.client.get('/api/parts/search/', {'q': 'Аккумулятор', 'model_id': model.pk}).json()['results']
        self.assertTrue(parts)
        self.assertTrue(all(model.parts.filter(pk=p['id']).exists() for p in parts))
        works = self.client.get('/api/works/search/', {'q': 'Замена', 'model_id': model.pk}).json()['results']
        self.assertTrue(works)
        self.assertTrue(all(model.works.filter(pk=w['id']).exists() for w in works))
