from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
import subprocess

from django.test import SimpleTestCase, override_settings
from mail_launcher import load_mail_environment, mail_worker
import lan


class MailEnvironmentTests(SimpleTestCase):
    def test_literal_password_and_environment_precedence(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / '.env'
            path.write_text('# local\nOTHER=ignored\nASUI_EMAIL_PASSWORD="abcd efgh ijkl mnop"\n', encoding='utf-8-sig')
            env = {}
            self.assertTrue(load_mail_environment(path, env))
            self.assertEqual(env, {'ASUI_EMAIL_PASSWORD': 'abcdefghijklmnop'})
            env['ASUI_EMAIL_PASSWORD'] = 'existing'
            load_mail_environment(path, env)
            self.assertEqual(env['ASUI_EMAIL_PASSWORD'], 'existing')

    def test_missing_empty_and_invalid_file(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / '.env'
            self.assertFalse(load_mail_environment(path, {}))
            path.write_text('ASUI_EMAIL_PASSWORD=\n', encoding='utf-8')
            self.assertFalse(load_mail_environment(path, {}))
            path.write_text('ASUI_EMAIL_PASSWORD="private-value\n', encoding='utf-8')
            with self.assertRaises(ValueError) as error:
                load_mail_environment(path, {})
            self.assertNotIn('private-value', str(error.exception))


class MailWorkerTests(SimpleTestCase):
    @override_settings(EMAIL_HOST_PASSWORD='')
    @patch('mail_launcher.subprocess.Popen')
    def test_no_password_no_worker(self, popen):
        with mail_worker(Path.cwd()) as worker:
            self.assertIsNone(worker)
        popen.assert_not_called()

    @override_settings(EMAIL_HOST_PASSWORD='local-secret')
    @patch('mail_launcher.subprocess.Popen')
    def test_start_once_stop_on_server_exception(self, popen):
        process = popen.return_value
        process.poll.return_value = None
        with self.assertRaises(RuntimeError):
            with mail_worker(Path.cwd()):
                raise RuntimeError('server failed')
        args, kwargs = popen.call_args
        self.assertEqual(args[0][-2:], ['send_notifications', '--watch'])
        self.assertNotIn('local-secret', str(args))
        self.assertNotIn('shell', kwargs)
        popen.assert_called_once()
        process.terminate.assert_called_once()
        process.wait.assert_called_once_with(timeout=5)

    @override_settings(EMAIL_HOST_PASSWORD='local-secret')
    @patch('mail_launcher.subprocess.Popen')
    def test_kill_if_stop_times_out(self, popen):
        process = popen.return_value
        process.poll.return_value = None
        process.wait.side_effect = [subprocess.TimeoutExpired('worker', 5), 0]
        with mail_worker(Path.cwd()):
            pass
        process.kill.assert_called_once()

    @patch('lan.interfaces', return_value=[])
    @patch('sys.argv', ['lan.py', '--list'])
    @patch('mail_launcher.subprocess.Popen')
    def test_list_does_not_start_worker(self, popen, interfaces):
        lan.main()
        popen.assert_not_called()

    @patch('lan.interfaces', return_value=[{'IP': '192.168.1.2', 'Gateway': '192.168.1.1', 'Private': True}])
    @patch('sys.argv', ['lan.py'])
    def test_lan_wraps_server_with_worker(self, interfaces):
        events = []
        server = Mock(server_port=8080)
        server.serve_forever.side_effect = lambda: events.append('serve')

        @contextmanager
        def worker(root):
            events.append('start')
            try:
                yield
            finally:
                events.append('stop')

        with patch('lan.make_server') as make, patch('lan.configure_environment'), \
             patch('mail_launcher.load_mail_environment') as load, \
             patch('mail_launcher.mail_worker', worker), \
             patch('django.core.wsgi.get_wsgi_application'):
            make.return_value.__enter__.return_value = server
            with patch.dict('os.environ', {'ASUI_PUBLIC_URL': 'http://192.168.1.2:8080'}):
                lan.main()
        load.assert_called_once_with(lan.ROOT / '.env')
        self.assertEqual(events, ['start', 'serve', 'stop'])
