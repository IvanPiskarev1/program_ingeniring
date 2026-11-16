"""Connectivity check; no client tokens or credentials are printed."""
import sys
import urllib.request
import urllib.error
for path in ('/', '/accounts/login/', '/static/css/style.css'):
    try:
        with urllib.request.urlopen(sys.argv[1].rstrip('/') + path, timeout=10) as response:
            print(path, response.status, response.headers.get('Content-Type'), len(response.read()))
    except Exception as exc:
        print(path, type(exc).__name__, str(exc))
