from django.test import Client, SimpleTestCase


class ReferrerPolicyTests(SimpleTestCase):
    def test_forms_keep_same_origin_provenance_without_external_referrer(self):
        response = self.client.get('/track/')
        self.assertEqual(response.headers['Referrer-Policy'], 'same-origin')
        self.assertContains(response, '<meta name="referrer" content="same-origin">')
        self.assertContains(response, 'csrfmiddlewaretoken')

    def test_null_origin_is_still_rejected(self):
        browser = Client(enforce_csrf_checks=True)
        browser.get('/track/')
        token = browser.cookies['csrftoken'].value
        response = browser.post('/track/', {'number': '1', 'code': 'wrong', 'csrfmiddlewaretoken': token}, HTTP_ORIGIN='null')
        self.assertEqual(response.status_code, 403)
