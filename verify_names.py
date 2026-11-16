"""Read-only verification against the pre-rename SQLite backup."""
import os
import sqlite3
from pathlib import Path
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.conf import settings
from django.db import connection
from repairs.management.commands.normalize_names import USERS, MARKER
from repairs.models import Client, Device
backup = sorted((settings.BASE_DIR / '.local/backups').glob('before_names_*.sqlite3'))[0]
old = sqlite3.connect(str(backup))
new = sqlite3.connect(str(settings.DATABASES['default']['NAME']))
allowed = {
 # Successful browser authentication legitimately updates last_login.
 'auth_user': {'username', 'first_name', 'last_name', 'last_login'},
 'repairs_client': {'name', 'contact', 'email'},
 'repairs_device': {'manufacturer', 'model', 'serial'},
 'repairs_repairorder': {'problem','accessories','appearance','issue_method','free_reason'},
 'repairs_diagnosis': {'result','required_parts'}, 'repairs_repairwork': {'description'},
 'repairs_usedpart': {'name'}, 'repairs_qualitycheck': {'comment'}, 'repairs_statushistory': {'comment'},
}
for (table,) in old.execute("SELECT name FROM sqlite_master WHERE type='table'"):
    # Browser login creates session records; they are not business data.
    if table == 'django_session':
        continue
    fields = [r[1] for r in old.execute(f'PRAGMA table_info("{table}")')]
    fixed = [f for f in fields if f not in allowed.get(table, set())]
    columns = ','.join('"'+f+'"' for f in fixed)
    before = old.execute(f'SELECT {columns} FROM "{table}" ORDER BY 1').fetchall()
    after = new.execute(f'SELECT {columns} FROM "{table}" ORDER BY 1').fetchall()
    assert before == after, table
assert not any(MARKER.search(c.name) for c in Client.objects.all())
assert not any(MARKER.search(d.manufacturer+' '+d.model+' '+d.serial) for d in Device.objects.all())
assert not new.execute("SELECT id FROM auth_user WHERE username LIKE 'demo_%'").fetchall()
assert new.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
assert not new.execute('PRAGMA foreign_key_check').fetchall()
old.close(); new.close()
print('PASS: names normalized; every row preserved; credentials, roles, links, amounts, statuses, tokens and audit unchanged; SQLite integrity OK.')
