import os
from unittest.mock import patch
from django.test import SimpleTestCase, RequestFactory
from django.urls import reverse
from types import SimpleNamespace

from lan import choose_interface, configure_environment, trust_network, describe_interfaces, interfaces
from repairs.public import tracking_url


class LanTests(SimpleTestCase):
    def test_selects_physical_private_lan_not_public_vpn(self):
        entries = [
            {'IP': '26.135.226.22', 'Private': True, 'Gateway': '26.0.0.1'},
            {'IP': '192.168.56.1', 'Private': True, 'Gateway': None},
            {'IP': '192.168.0.101', 'Private': True, 'Gateway': '192.168.0.1'},
        ]
        self.assertEqual(choose_interface(entries)['IP'], '192.168.0.101')
        with self.assertRaises(ValueError):
            choose_interface(entries, '26.135.226.22')
        entries.append({'IP': '10.0.0.2', 'Private': True, 'Gateway': '10.0.0.1'})
        with self.assertRaises(ValueError):
            choose_interface(entries)
        self.assertEqual(choose_interface(entries, '10.0.0.2')['IP'], '10.0.0.2')

    def test_public_profile_is_not_accepted(self):
        with self.assertRaises(ValueError):
            choose_interface([{'IP': '192.168.1.2', 'Private': False, 'Gateway': '192.168.1.1'}])

    def test_hotspot_public_profile_reports_address_and_solution(self):
        item = {'Index': 10, 'Name': 'Wi-Fi', 'IP': '172.20.10.4',
                'Gateway': '172.20.10.1', 'Private': False, 'Category': 'Public'}
        for requested in (None, item['IP']):
            with self.assertRaises(ValueError) as error:
                choose_interface([item], requested)
            self.assertIn('172.20.10.4', str(error.exception))
            self.assertIn('--trust-network', str(error.exception))
        self.assertIn('Wi-Fi', describe_interfaces([item]))
        with patch('lan.powershell') as command:
            trust_network([item], item['IP'])
            command.assert_called_once_with('Set-NetConnectionProfile -InterfaceIndex 10 -NetworkCategory Private')

    def test_profile_change_requires_explicit_valid_physical_lan(self):
        item = {'Index': 10, 'IP': '172.20.10.4', 'Gateway': '172.20.10.1',
                'Private': False, 'Category': 'Public'}
        with patch('lan.powershell') as command:
            for requested in (None, '127.0.0.1', '10.0.0.123'):
                with self.assertRaises(ValueError):
                    trust_network([item], requested)
            with self.assertRaises(ValueError):
                trust_network([dict(item, Category='DomainAuthenticated')], item['IP'])
            trust_network([dict(item, Private=True)], item['IP'])
            command.assert_not_called()

    def test_discovery_preserves_profile_name_and_each_address(self):
        raw = '[{"Index":10,"Name":"Wi-Fi","IP":"172.20.10.4","Gateway":"172.20.10.1","Category":"Public","Private":false}]'
        with patch('lan.powershell', return_value=raw):
            item = interfaces()[0]
        self.assertEqual(item['Category'], 'Public')
        self.assertEqual(item['Name'], 'Wi-Fi')
        self.assertFalse(item['Private'])

    def test_environment_and_qr_target_ignore_local_browser_host(self):
        with patch.dict(os.environ, {'DJANGO_DEBUG': '1'}):
            configure_environment('192.168.0.101', 8080)
            self.assertEqual(os.environ['DJANGO_ALLOWED_HOSTS'], '192.168.0.101,127.0.0.1,localhost')
            with self.settings(PUBLIC_BASE_URL=os.environ['ASUI_PUBLIC_URL']):
                order = SimpleNamespace(token='test-token')
                url = tracking_url(RequestFactory().get('/', HTTP_HOST='localhost'), order)
                self.assertEqual(url, 'http://192.168.0.101:8080' + reverse('public_status', args=[order.token]))

    def test_does_not_downgrade_production(self):
        with patch.dict(os.environ, {'DJANGO_DEBUG': '0'}):
            with self.assertRaises(ValueError):
                configure_environment('192.168.0.101', 8080)
