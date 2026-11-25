"""Local SMTP configuration and lifetime of the LAN mail worker."""
from contextlib import contextmanager
import os
from pathlib import Path
import subprocess
import sys
import threading


def load_mail_environment(path, environ=None):
    """Read only the SMTP password; shell environment takes precedence.

    Values are literal: no interpolation, shell execution or escape processing.
    Never include file contents or the password in errors/logs.
    """
    environ = os.environ if environ is None else environ
    if environ.get('ASUI_EMAIL_PASSWORD', '').strip():
        return True
    path = Path(path)
    if not path.exists():
        return False
    password = ''
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, separator, value = line.partition('=')
        if key.strip() != 'ASUI_EMAIL_PASSWORD':
            continue
        if not separator:
            raise ValueError('В .env ожидается ASUI_EMAIL_PASSWORD=пароль_приложения.')
        value = value.strip()
        if value.startswith(('"', "'")):
            if len(value) < 2 or value[-1] != value[0]:
                raise ValueError('Проверьте парные кавычки ASUI_EMAIL_PASSWORD в .env.')
            value = value[1:-1]
        password = value.replace(' ', '').strip()
    if password:
        environ['ASUI_EMAIL_PASSWORD'] = password
    return bool(password)


@contextmanager
def mail_worker(root):
    """Start once, never auto-restart; always stop when the web server exits."""
    from django.conf import settings
    if not settings.EMAIL_HOST_PASSWORD:
        print('Почта не запущена: заполните ASUI_EMAIL_PASSWORD в .env и перезапустите сайт.', flush=True)
        yield None
        return
    options = {}
    if os.name == 'nt':
        # Parent handles Ctrl+C and stops the child in finally.
        options['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
    process = subprocess.Popen(
        [sys.executable, str(Path(root) / 'manage.py'), 'send_notifications', '--watch'],
        cwd=root, env=os.environ.copy(), **options)
    stopped = threading.Event()

    def monitor():
        while not stopped.wait(1):
            if process.poll() is not None:
                print('Отправщик почты остановился. Проверьте сообщение выше; '
                      'автоматического перезапуска нет. Сайт продолжает работать.', flush=True)
                return

    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    print('Отправщик почты запущен; проверка очереди каждые 15 секунд.', flush=True)
    try:
        yield process
    finally:
        stopped.set()
        thread.join(timeout=2)
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        print('Отправщик почты остановлен.', flush=True)
