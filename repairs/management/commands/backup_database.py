import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

class Command(BaseCommand):
    help = 'Безопасная онлайн-копия SQLite; удаляет только свои копии старше 30 дней.'
    def add_arguments(self, parser):
        parser.add_argument('--output', default=str(settings.BASE_DIR / 'backups'))
        parser.add_argument('--keep-existing', action='store_true', help='Не удалять прежние копии.')
    def handle(self, *args, **options):
        source = Path(settings.DATABASES['default']['NAME'])
        if not source.exists(): raise CommandError('База не найдена. Сначала migrate.')
        folder = Path(options['output']).resolve()
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f'asui-{datetime.now():%Y%m%d-%H%M%S-%f}.sqlite3'
        with closing(sqlite3.connect(str(source))) as src, closing(sqlite3.connect(str(target))) as dst:
            src.backup(dst)
            if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise CommandError('Проверка целостности копии не прошла.')
        cutoff = datetime.now().timestamp() - timedelta(days=30).total_seconds()
        if not options['keep_existing']:
            for old in folder.glob('asui-*.sqlite3'):
                if old.stat().st_mtime < cutoff: old.unlink()
        self.stdout.write(self.style.SUCCESS(f'Копия создана и проверена: {target}'))
        return str(target)
