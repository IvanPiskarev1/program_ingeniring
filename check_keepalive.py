import http.client
c = http.client.HTTPConnection('127.0.0.1', 8123, timeout=10)
c.request('GET', '/accounts/login/')
r = c.getresponse()
print('first:', r.status, len(r.read()))
c.request('GET', '/accounts/login/')
r2 = c.getresponse()
print('second:', r2.status, len(r2.read()))
