from django.test import SimpleTestCase


class FaviconTests(SimpleTestCase):
    def test_favicon_is_available(self):
        response = self.client.get('/favicon.ico')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/svg+xml')
