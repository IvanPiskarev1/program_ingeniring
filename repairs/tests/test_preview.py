import socket
import threading
import urllib.request
from django.test import SimpleTestCase
from preview import create_server


class PreviewTests(SimpleTestCase):
    def test_idle_connection_does_not_block_real_http_request(self):
        def application(environ, start_response):
            start_response('200 OK', [('Content-Type', 'text/plain'), ('Content-Length', '2')])
            return [b'ok']
        with create_server(application) as server:
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                with socket.create_connection(server.server_address, timeout=2) as idle:
                    # A browser can preconnect without sending request headers.
                    # An ordinary single-threaded WSGIServer blocks on this socket.
                    idle.sendall(b'GET / HTTP/1.1\r\n')
                    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                    with opener.open(f'http://127.0.0.1:{server.server_port}/', timeout=3) as response:
                        self.assertEqual(response.status, 200)
                        self.assertEqual(response.read(), b'ok')
            finally:
                server.shutdown()
                worker.join(timeout=5)
