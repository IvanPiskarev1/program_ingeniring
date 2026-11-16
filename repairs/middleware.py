import hashlib
from django.core.cache import cache
from django.http import HttpResponse


def rate_limited(request, scope, limit=15):
    address = request.META.get('REMOTE_ADDR', 'unknown')
    key = scope + hashlib.sha256(address.encode()).hexdigest()
    attempts = cache.get(key, 0)
    if attempts >= limit:
        return True
    cache.set(key, attempts + 1, 300)
    return False


class LoginThrottleMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
    def __call__(self, request):
        if request.method == 'POST' and request.path in ('/accounts/login/', '/admin/login/'):
            if rate_limited(request, 'login:', 20):
                return HttpResponse('Слишком много попыток входа. Повторите через 5 минут.', status=429)
        return self.get_response(request)
