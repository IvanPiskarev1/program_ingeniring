import io
import uuid
from decimal import Decimal
from django.core.management import call_command
from django.urls import reverse
from repairs.models import Client, Device, PriceItem, RepairOrder
from .test_workflow import WorkflowFixture


class IntakeCatalogTests(WorkflowFixture):
    def test_client_api_permissions_and_minimal_data(self):
        endpoints = ['/api/clients/search/?q=Кл', f'/api/clients/{self.customer.pk}/', f'/api/clients/{self.customer.pk}/devices/']
        for role in (None, 'Мастер', 'Контроль качества', 'Руководитель', 'Администратор'):
            self.client.logout()
            if role:
                self.client.force_login(self.users[role])
            for url in endpoints:
                self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.users['Приём'])
        self.assertEqual(self.client.get('/api/clients/search/?q=К').json()['results'], [])
        response = self.client.get('/api/clients/search/?q=клиент')
        self.assertEqual(response.json()['results'][0]['id'], self.customer.pk)
        self.assertNotIn(self.order.token, response.content.decode())
        self.assertNotIn('token', response.content.decode())
        self.assertIn('no-store', response['Cache-Control'])
        self.customer.email = 'ivan@example.org'; self.customer.save()
        self.assertEqual(len(self.client.get('/api/clients/search/?q=ivan@').json()['results']), 1)
        for i in range(12):
            Client.objects.create(name=f'Иван Петров {i}', phone=f'+799900001{i:02d}')
        self.assertEqual(len(self.client.get('/api/clients/search/?q=иван').json()['results']), 10)

    def test_client_device_fields_and_foreign_device_rejected(self):
        self.client.force_login(self.users['Приём'])
        self.order.accessories = 'Блок питания'; self.order.save()
        info = self.client.get(f'/api/clients/{self.customer.pk}/').json()
        self.assertEqual(info['phone'], self.customer.phone)
        devices = self.client.get(f'/api/clients/{self.customer.pk}/devices/').json()['results']
        self.assertEqual(devices[0]['serial'], self.device.serial)
        self.assertEqual(devices[0]['accessories'], 'Блок питания')
        self.assertEqual(devices[0]['device_type'], self.kind.pk)
        foreign = Device.objects.create(kind=self.kind, manufacturer='HP', model='250 G8')
        data = {'request_key': uuid.uuid4(), 'existing_client': self.customer.pk, 'kind': 'person', 'existing_device': foreign.pk, 'problem': 'Нет питания'}
        response = self.client.post(reverse('intake'), data)
        self.assertContains(response, 'Изделие не принадлежит выбранному клиенту')
        self.assertEqual(RepairOrder.objects.count(), 1)

    def test_intake_edits_and_no_js_loading(self):
        self.client.force_login(self.users['Приём'])
        key = str(uuid.uuid4())
        data = {'request_key': key, 'existing_client': self.customer.pk, 'existing_device': self.device.pk, 'kind': 'person', 'load_existing': 'existing_client'}
        response = self.client.post(reverse('intake'), data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['form'].initial['client_name'], self.customer.name)
        self.assertEqual(response.context['form'].initial['serial'], self.device.serial)
        self.assertEqual(RepairOrder.objects.count(), 1)
        edited = dict(data, load_existing='existing_device', phone='+79995554433', email='changed@example.org', client_loaded='1')
        loaded = self.client.post(reverse('intake'), edited)
        self.assertEqual(loaded.context['form'].initial['phone'], '+79995554433')
        self.assertEqual(loaded.context['form'].initial['email'], 'changed@example.org')
        data.pop('load_existing')
        data.update(client_name='Иван Петров', phone=self.customer.phone, email='ivan@example.org', client_loaded='1', email_notifications='on', problem='Повторный ремонт')
        self.assertEqual(self.client.post(reverse('intake'), data).status_code, 302)
        self.client.post(reverse('intake'), data)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.name, 'Иван Петров')
        self.assertTrue(self.customer.email_notifications)
        self.assertEqual(RepairOrder.objects.filter(request_key=key).count(), 1)
        data.update(request_key=str(uuid.uuid4()), email_notifications='')
        self.assertEqual(self.client.post(reverse('intake'), data).status_code, 302)
        self.customer.refresh_from_db(); self.assertFalse(self.customer.email_notifications)

    def test_duplicate_phone_normalization(self):
        self.customer.phone = '+7 (999) 123-45-67'; self.customer.save()
        self.client.force_login(self.users['Приём'])
        data = {'request_key': uuid.uuid4(), 'kind': 'person', 'client_name': 'Иван', 'phone': '8 999 1234567', 'device_type': self.kind.pk, 'manufacturer': 'HP', 'device_model': '250', 'problem': 'Нет питания'}
        self.assertContains(self.client.post(reverse('intake'), data), 'Клиент с таким телефоном уже существует')
        self.assertEqual(Client.objects.count(), 1)
        self.assertEqual(len(self.client.get('/api/clients/search/?q=89991234567').json()['results']), 1)

    def test_catalog_seed_and_idempotence(self):
        original = PriceItem.objects.create(kind='part', name='Дисплейный модуль Apple iPhone 11', price=300)
        before = PriceItem.objects.filter(kind='part').count()
        call_command('seed_parts_catalog', stdout=io.StringIO())
        count = PriceItem.objects.filter(kind='part').count()
        self.assertGreaterEqual(count - before, 500)
        self.assertEqual(PriceItem.objects.exclude(sku=None).values('sku').distinct().count(), count - before)
        self.assertFalse(PriceItem.objects.filter(price__lte=0).exists())
        call_command('seed_parts_catalog', stdout=io.StringIO())
        self.assertEqual(PriceItem.objects.filter(kind='part').count(), count)
        original.refresh_from_db(); self.assertEqual(original.price, 300)
        self.assertIsNone(original.sku)

    def test_price_search_filters_and_pagination(self):
        self.client.force_login(self.users['Мастер'])
        call_command('seed_parts_catalog', stdout=io.StringIO())
        response = self.client.get('/price/')
        self.assertEqual(len(response.context['page_obj']), 50)
        self.assertTrue(response.context['page_obj'].has_next())
        response = self.client.get('/price/?page=2')
        self.assertEqual(response.context['page_obj'].number, 2)
        item = PriceItem.objects.filter(kind='part').first()
        response = self.client.get('/price/', {'q': item.sku})
        self.assertEqual(response.context['page_obj'].paginator.count, 1)
        response = self.client.get('/price/', {'category': item.category, 'group': item.group})
        self.assertTrue(all(p.category == item.category and p.group == item.group for p in response.context['page_obj']))
        response = self.client.get('/api/parts/search/', {'q': item.sku})
        self.assertEqual(response.json()['results'][0]['price'], str(item.price))
        self.client.force_login(self.users['Контроль качества'])
        self.assertEqual(self.client.get('/api/parts/search/?q=HP').status_code, 403)

    def test_part_price_snapshot_and_totals(self):
        self.repair()
        item = PriceItem.objects.create(kind='part', name='Аккумулятор HP HT03XL', price=2500, sku='HP-HT03XL')
        self.client.force_login(self.users['Мастер'])
        response = self.client.post(reverse('order_action', args=[self.order.pk, 'part']), {'price_item': item.pk, 'quantity': 2, 'version': self.order.version, 'price': '1', 'name': 'Подмена'})
        self.assertEqual(response.status_code, 302)
        part = self.order.parts.latest('pk')
        self.assertEqual(part.price, Decimal('2500'))
        self.assertEqual(part.name, item.name)
        item.price = 5000; item.save()
        self.order.refresh_from_db()
        self.assertEqual(self.order.final_total, Decimal('7500'))
        self.assertEqual(self.order.preliminary_total, Decimal('7500'))
        part.refresh_from_db(); self.assertEqual(part.price, Decimal('2500'))
        public = self.client.get(reverse('public_api', args=[self.order.token])).json()
        self.assertNotIn('token', public); self.assertNotIn('phone', public)

    def test_zero_diagnosis_price_not_replaced(self):
        self.act('assign', {'master': self.users['Мастер']}, 'Руководитель')
        self.act('start')
        self.act('diagnosis', {'result': 'Проверено питание', 'category': self.category, 'required_parts': '', 'estimate': Decimal('1000'), 'diagnosis_price': Decimal('0')})
        self.assertEqual(self.order.final_total, 0)
        self.assertEqual(self.order.estimate, 1000)
