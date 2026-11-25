from decimal import Decimal
from io import StringIO
from django.core.management import call_command
from django.urls import reverse
from repairs.models import PriceItem, WorkCatalogItem, RepairWork
from .test_workflow import WorkflowFixture


class DiagnosticsTests(WorkflowFixture):
    def setUp(self):
        super().setUp()
        self.act('assign', {'master': self.users['Мастер']}, 'Руководитель')
        self.act('start')
        self.client.force_login(self.users['Мастер'])
        self.url = reverse('diagnostics', args=[self.order.pk])
        self.part = PriceItem.objects.create(kind='part', name='Разъём Samsung', price=Decimal('350'))
        self.work = WorkCatalogItem.objects.create(name='Ремонт питания', category=self.category, price=Decimal('1200'))

    def payload(self, rows):
        data = {'result': 'Нарушен контакт разъёма питания', 'category': self.category.pk,
                'estimate': '5000', 'diagnosis_price': '0', 'due_date': '2026-12-25',
                'version': str(self.order.version), 'items-TOTAL_FORMS': str(len(rows)), 'items-INITIAL_FORMS': '0'}
        for i, row in enumerate(rows):
            for key, value in row.items():
                data[f'items-{i}-{key}'] = str(value)
        return data

    def test_catalog_snapshots_server_prices_and_total(self):
        data = self.payload([
            {'kind': 'part', 'catalog_id': self.part.pk, 'name': 'Подменённое имя', 'price': '1', 'quantity': 2},
            {'kind': 'work', 'catalog_id': self.work.pk, 'name': 'Подменённая работа', 'price': '2', 'quantity': 2},
        ])
        self.assertEqual(self.client.post(self.url, data).status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.final_total, Decimal('3100'))
        self.assertEqual(self.order.diagnosis.price, 0)
        self.assertEqual(self.order.estimate, 3100)
        self.assertEqual(self.order.parts.get().name, self.part.name)
        self.assertEqual(self.order.parts.get().price, 350)
        self.assertEqual(self.order.works.get().description, self.work.name)
        self.assertEqual(self.order.works.get().cost, 2400)
        self.part.price = 9999; self.part.save()
        self.work.price = 9999; self.work.save()
        self.order.refresh_from_db()
        self.assertEqual(self.order.final_total, 3100)
        self.assertEqual(self.order.estimate_revisions.count(), 1)
        self.assertEqual(self.client.post(self.url, data).status_code, 409)
        self.assertEqual(self.order.parts.count(), 1)
        self.assertEqual(self.order.works.count(), 1)

    def test_estimate_calculated_even_when_post_is_blank(self):
        data = self.payload([{'kind': 'part', 'catalog_id': self.part.pk, 'quantity': 3}])
        data.update(estimate='', diagnosis_price='500')
        self.assertEqual(self.client.post(self.url, data).status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.estimate, 1550)
        self.assertEqual(self.order.final_total, 1550)
        self.assertEqual(self.order.estimate_revisions.get().amount, 1550)

    def test_free_rows_do_not_use_manual_estimate(self):
        data = self.payload([{'kind': 'work', 'name': 'Проверка разъёма', 'price': 0, 'quantity': 1}])
        self.assertEqual(self.client.post(self.url, data).status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.estimate, 0)

    def test_manual_and_empty_rows(self):
        data = self.payload([{'kind': 'work', 'name': 'Восстановление дорожки', 'price': 800, 'quantity': 1},
                             {'kind': 'part', 'name': '', 'price': '', 'quantity': 1}])
        self.assertEqual(self.client.post(self.url, data).status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.final_total, 800)
        self.assertEqual(self.order.parts.count(), 0)
        self.assertEqual(WorkCatalogItem.objects.count(), 1)

    def test_validation_preserves_rows_and_atomicity(self):
        for quantity, price in [('0', '100'), ('1.5', '100'), ('1', '-1')]:
            with self.subTest(quantity=quantity, price=price):
                data = self.payload([{'kind': 'part', 'name': 'Кабель питания', 'price': price, 'quantity': quantity}])
                response = self.client.post(self.url, data)
                self.assertEqual(response.status_code, 400)
                self.assertContains(response, 'Кабель питания', status_code=400)
                self.assertFalse(self.order.parts.exists())
                self.order.refresh_from_db()
                self.assertEqual(self.order.status, 'diagnosis')

    def test_permissions_and_foreign_master(self):
        for role in ('Приём', 'Руководитель', 'Контроль качества'):
            self.client.force_login(self.users[role])
            self.assertEqual(self.client.post(self.url, self.payload([])).status_code, 403)
        self.order.master = None; self.order.save()
        self.client.force_login(self.users['Мастер'])
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_api_permissions_limit_and_no_cache(self):
        url = reverse('works_search')
        self.client.logout()
        self.assertEqual(self.client.get(url, {'q': 'рем'}).status_code, 403)
        self.client.force_login(self.users['Контроль качества'])
        self.assertEqual(self.client.get(url, {'q': 'рем'}).status_code, 403)
        self.client.force_login(self.users['Мастер'])
        self.assertEqual(self.client.get(url, {'q': 'р'}).json()['results'], [])
        response = self.client.get(url, {'q': 'РЕМОНТ'})
        self.assertEqual(response.json()['results'][0]['price'], '1200.00')
        self.assertIn('no-store', response['Cache-Control'])
        for n in range(12):
            WorkCatalogItem.objects.create(name=f'Ремонт контакта {n}', category=self.category, price=1)
        self.assertEqual(len(self.client.get(url, {'q': 'ремонт'}).json()['results']), 10)
        self.work.is_active = False; self.work.save()
        self.assertNotIn(self.work.pk, [r['id'] for r in self.client.get(url, {'q': 'питания'}).json()['results']])

    def test_without_js_add_preserves_input(self):
        data = self.payload([{'kind': 'work', 'name': 'Восстановление дорожки', 'price': 800, 'quantity': 1}])
        data['add_catalog'] = f'part:{self.part.pk}'
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Восстановление дорожки')
        self.assertContains(response, self.part.name)
        self.assertFalse(self.order.parts.exists())
        formset = response.context['formset']
        self.assertEqual(formset.total_form_count(), 2)
        data.update({'items-TOTAL_FORMS': '2', 'items-1-kind': 'part', 'items-1-catalog_id': self.part.pk,
                     'items-1-quantity': '1'})
        del data['add_catalog']
        self.assertEqual(self.client.post(self.url, data).status_code, 302)

    def test_without_js_remove_catalog_row_preserves_other_rows(self):
        data = self.payload([
            {'kind': 'part', 'catalog_id': self.part.pk, 'name': self.part.name, 'price': 350, 'quantity': 2},
            {'kind': 'work', 'name': 'Восстановление контакта', 'price': 800, 'quantity': 1},
        ])
        data['remove_row'] = '0'
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.order.parts.exists())
        self.assertFalse(self.order.works.exists())
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'diagnosis')
        formset = response.context['formset']
        self.assertEqual(formset.total_form_count(), 1)
        self.assertEqual(formset.forms[0]['name'].value(), 'Восстановление контакта')
        self.assertEqual(formset.forms[0]['catalog_id'].value(), '')
        remaining = dict(formset.data)
        # QueryDict values must remain scalars for the subsequent browser POST.
        remaining = {key: formset.data.get(key) for key in remaining}
        del remaining['remove_row']
        self.assertEqual(self.client.post(self.url, remaining).status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.final_total, 800)
        self.assertFalse(self.order.parts.exists())

    def test_without_js_search_keeps_results_expanded(self):
        data = self.payload([])
        data.update({'lookup': '1', 'q': self.part.name, 'kind': 'part'})
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<details open>')
        self.assertContains(response, f'Добавить: {self.part.name}')
        self.assertFalse(self.order.parts.exists())

    def test_without_js_remove_last_row(self):
        data = self.payload([{'kind': 'part', 'catalog_id': self.part.pk, 'quantity': 1}])
        data['remove_row'] = '0'
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['formset'].total_form_count(), 0)
        self.assertEqual(response.context['form']['estimate'].value(), '0')
        self.assertFalse(self.order.parts.exists())

    def test_stale_version_and_inactive_item(self):
        data = self.payload([{'kind': 'part', 'catalog_id': self.part.pk, 'quantity': 1}])
        data['version'] = '0'
        self.assertEqual(self.client.post(self.url, data).status_code, 409)
        self.part.is_active = False; self.part.save()
        data['version'] = str(self.order.version)
        self.assertEqual(self.client.post(self.url, data).status_code, 400)
        self.assertFalse(self.order.parts.exists())

    def test_seed_idempotent_preserves_existing(self):
        out = StringIO()
        call_command('seed_works_catalog', stdout=out)
        count = WorkCatalogItem.objects.count()
        self.assertGreaterEqual(count, 24)
        item = WorkCatalogItem.objects.order_by('pk').last()
        item.price = 321; item.save()
        call_command('seed_works_catalog', stdout=out)
        self.assertEqual(WorkCatalogItem.objects.count(), count)
        item.refresh_from_db()
        self.assertEqual(item.price, 321)
