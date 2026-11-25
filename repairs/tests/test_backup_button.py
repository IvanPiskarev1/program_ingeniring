import io
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.core.management import CommandError
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from repairs.management.commands.backup_database import Command
from repairs.permissions import ADMIN, MASTER, MANAGER, QUALITY, RECEPTION


class BackupButtonTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user('backup-admin', is_staff=True)
        self.admin.groups.add(Group.objects.get_or_create(name=ADMIN)[0])
        self.url = reverse('create_backup')

    def test_only_admin_can_create(self):
        with patch('django.core.management.call_command') as command:
            self.assertEqual(self.client.post(self.url).status_code, 302)
            for role in (MASTER, MANAGER, QUALITY, RECEPTION):
                user = User.objects.create_user('backup-' + str(Group.objects.get_or_create(name=role)[0].pk))
                user.groups.add(Group.objects.get(name=role))
                self.client.force_login(user)
                self.assertEqual(self.client.post(self.url).status_code, 403)
                self.assertNotContains(self.client.get(reverse('dashboard')), 'Создать резервную копию')
            command.assert_not_called()

    def test_get_and_missing_csrf_do_not_create(self):
        self.client.force_login(self.admin)
        with patch('django.core.management.call_command') as command:
            self.assertEqual(self.client.get(self.url).status_code, 405)
            browser = Client(enforce_csrf_checks=True)
            browser.force_login(self.admin)
            self.assertEqual(browser.post(self.url).status_code, 403)
            command.assert_not_called()

    def test_button_and_success(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse('dashboard')), 'Создать резервную копию')
        self.assertContains(self.client.get('/admin/'), 'Создать резервную копию')
        with patch('django.core.management.call_command', return_value='backups/asui-copy.sqlite3') as command:
            response = self.client.post(self.url, follow=True)
            self.assertContains(response, 'Резервная копия создана и проверена: backups/asui-copy.sqlite3')
            self.assertTrue(command.call_args.kwargs['keep_existing'])

    def test_failure_is_visible_and_does_not_leak_details(self):
        self.client.force_login(self.admin)
        with patch('django.core.management.call_command', side_effect=CommandError('private-path')):
            response = self.client.post(self.url, follow=True)
        self.assertContains(response, 'Не удалось создать резервную копию')
        self.assertNotContains(response, 'private-path')

    def test_actual_backup_and_retention(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'source.sqlite3'
            with closing(sqlite3.connect(source)) as db:
                db.execute('create table orders (number integer)')
                db.execute('insert into orders values (15)')
                db.commit()
            folder = Path(temp) / 'backups'
            folder.mkdir()
            old = folder / 'asui-old.sqlite3'
            old.write_bytes(b'preserve')
            import os
            os.utime(old, (1, 1))
            with override_settings(DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': str(source)}}):
                command = Command(stdout=io.StringIO())
                target = command.handle(output=str(folder), keep_existing=True)
            self.assertTrue(old.exists())
            with closing(sqlite3.connect(target)) as db:
                self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
                self.assertEqual(db.execute('select number from orders').fetchone()[0], 15)
