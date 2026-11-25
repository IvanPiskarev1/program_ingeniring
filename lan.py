"""Windows trusted-LAN launcher. Not an Internet/production server."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import sys
from wsgiref.simple_server import make_server

from preview import PreviewServer, PrivateLog

ROOT = Path(__file__).resolve().parent


def powershell(script):
    result = subprocess.run(
        ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
         "$ErrorActionPreference='Stop'; " + script],
        capture_output=True, encoding='utf-8', errors='replace',
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or 'Windows command failed')
    return result.stdout.strip()


def interfaces():
    raw = powershell(
        "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; "
        "$physical=@(Get-NetAdapter -Physical | Select-Object -ExpandProperty InterfaceIndex); "
        "@(Get-NetIPConfiguration | Where-Object { $_.InterfaceIndex -in $physical } | ForEach-Object { "
        "$config=$_; foreach ($address in @($config.IPv4Address)) { "
        "[pscustomobject]@{Index=$config.InterfaceIndex; Name=$config.InterfaceAlias; IP=$address.IPAddress; "
        "Gateway=$config.IPv4DefaultGateway.NextHop; Category=[string]$config.NetProfile.NetworkCategory; "
        "Private=($config.NetProfile.NetworkCategory -eq 'Private')} } }) | ConvertTo-Json -Compress"
    )
    data = json.loads(raw or '[]')
    return data if isinstance(data, list) else [data]


def lan_candidates(items):
    candidates = []
    for item in items:
        try:
            address = ipaddress.IPv4Address(item['IP'])
        except (ValueError, KeyError, TypeError):
            continue
        # RFC1918 only; physical adapters are selected by interfaces().
        if item.get('Gateway') and any(address in ipaddress.ip_network(net) for net in
                                      ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')):
            candidates.append(item)
    return candidates


def describe_interfaces(items):
    lines = []
    for item in items:
        category = 'Частная' if item.get('Private') else (item.get('Category') or 'Не частная')
        lines.append(f"{item.get('Name', 'Подключение')} | IP {item.get('IP', 'нет')} | "
                     f"профиль: {category} | шлюз: {item.get('Gateway') or 'нет'}")
    return '\n'.join(lines) or 'Физические подключения с IPv4 не найдены.'


def choose_interface(items, requested=None):
    available = lan_candidates(items)
    selected = [item for item in available if requested is None or item['IP'] == requested]
    if requested and len(selected) == 1 and not selected[0].get('Private'):
        raise ValueError('Выбранная сеть не имеет профиля «Частная». Если это ваша защищённая '
                         'точка доступа, выполните от имени администратора: '
                         f'python lan.py --ip {requested} --trust-network --configure-firewall\n'
                         + describe_interfaces(items))
    candidates = [item for item in selected if item.get('Private')]
    if len(candidates) != 1:
        raise ValueError('Не удалось однозначно выбрать частную сеть.\n'
                         + describe_interfaces(items)
                         + '\nВыберите IP сети телефона и укажите --ip АДРЕС. '
                         'Если профиль Public, для своей защищённой сети добавьте '
                         '--trust-network --configure-firewall в терминале администратора. '
                         'Если подключения нет, сначала подключите компьютер к Wi-Fi телефона.')
    return candidates[0]


def trust_network(items, requested):
    # A profile change must target one explicitly selected physical LAN, never all networks.
    if not requested:
        raise ValueError('--trust-network требует явного --ip адреса вашей защищённой сети.')
    matches = [item for item in lan_candidates(items) if item['IP'] == requested]
    if len(matches) != 1:
        raise ValueError('Выбранный IP не найден на одном физическом подключении со шлюзом.\n'
                         + describe_interfaces(items))
    item = matches[0]
    if item.get('Private'):
        return
    if item.get('Category') != 'Public':
        raise ValueError('Менять можно только профиль Public вашей личной сети, не доменный профиль.')
    index = int(item['Index'])
    powershell(f'Set-NetConnectionProfile -InterfaceIndex {index} -NetworkCategory Private')


def configure_environment(ip, port):
    os.environ['ASUI_PUBLIC_URL'] = f'http://{ip}:{port}'
    os.environ['DJANGO_ALLOWED_HOSTS'] = f'{ip},127.0.0.1,localhost'
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    # Preserve production settings; do not silently downgrade an existing deployment.
    if os.environ.get('DJANGO_DEBUG', '1') != '1':
        raise ValueError('Этот HTTP-запуск предназначен только для доверенной сети с DJANGO_DEBUG=1.')


def firewall_rule(ip, index, port):
    # Only numeric values cross into PowerShell. Program path is single-quote escaped.
    ipaddress.IPv4Address(ip)
    index, port = int(index), int(port)
    program = sys.executable.replace("'", "''")
    name = f'ASUI-LAN-{ip}-{port}'
    powershell(
        f"$old=Get-NetFirewallRule -Name '{name}' -ErrorAction SilentlyContinue; "
        "if ($old) { throw 'Rule already exists; not modifying existing firewall rules.' }; "
        f"New-NetFirewallRule -Name '{name}' -DisplayName '{name}' "
        f"-Direction Inbound -Action Allow -Protocol TCP -LocalPort {port} "
        f"-LocalAddress '{ip}' -RemoteAddress LocalSubnet -Profile Private "
        f"-InterfaceAlias (Get-NetAdapter -InterfaceIndex {index}).Name "
        f"-Program '{program}' | Out-Null"
    )
    return name


def main():
    parser = argparse.ArgumentParser(description='Запуск АСУИ для телефона в частной сети Windows')
    parser.add_argument('--ip', help='IPv4 компьютера в доверенной сети')
    parser.add_argument('--port', type=int, default=8080, help='Порт, 0 — свободный порт')
    parser.add_argument('--configure-firewall', action='store_true', help='Создать узкое правило Windows Firewall (нужны права администратора)')
    parser.add_argument('--inspect', action='store_true', help='Только показать выбранную сеть')
    parser.add_argument('--list', action='store_true', help='Показать подключения и профили без изменений')
    parser.add_argument('--trust-network', action='store_true', help='Сделать выбранную через --ip личную сеть частной (нужны права администратора)')
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error('Порт должен быть от 0 до 65535')
    os.chdir(ROOT)
    try:
        items = interfaces()
        if args.list:
            print(describe_interfaces(items), flush=True)
            return
        if args.trust_network:
            if args.inspect:
                raise ValueError('--inspect не изменяет профиль; уберите --trust-network.')
            trust_network(items, args.ip)
            items = interfaces()
            print('Профиль выбранной сети проверен; изменение на Private сохраняется в Windows.', flush=True)
        item = choose_interface(items, args.ip)
        ip = str(item['IP'])
        if args.inspect:
            print(json.dumps(item, ensure_ascii=False), flush=True)
            return
        # Bind to the selected LAN address, never all interfaces/VPN adapters.
        with make_server(ip, args.port, lambda environ, start: [],
                         server_class=PreviewServer, handler_class=PrivateLog) as server:
            port = server.server_port
            configure_environment(ip, port)
            from mail_launcher import load_mail_environment, mail_worker
            load_mail_environment(ROOT / '.env')
            from django.core.wsgi import get_wsgi_application
            from django.contrib.staticfiles.handlers import StaticFilesHandler
            server.set_app(StaticFilesHandler(get_wsgi_application()))
            if args.configure_firewall:
                try:
                    name = firewall_rule(ip, item['Index'], port)
                    print('Правило брандмауэра создано: ' + name, flush=True)
                except RuntimeError as error:
                    print('Брандмауэр НЕ изменён: ' + str(error), flush=True)
                    print('Если телефон не подключается, выполните команду из README в терминале администратора.', flush=True)
            url = f'http://{ip}:{port}'
            print('АСУИ в доверенной сети: ' + url + '/', flush=True)
            print('QR-ссылки: ' + os.environ['ASUI_PUBLIC_URL'], flush=True)
            print('Телефон должен быть в той же сети. Остановка: Ctrl+C. Не открывайте порт на роутере.', flush=True)
            print('HTTP без шифрования; используйте только доверенную сеть. Это не сервер для Интернета.', flush=True)
            with mail_worker(ROOT):
                server.serve_forever()
    except (OSError, RuntimeError, ValueError) as error:
        parser.exit(1, str(error) + '\n')
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
