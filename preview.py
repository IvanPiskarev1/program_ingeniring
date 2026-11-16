"""Loopback-only threaded development preview; never deploy this server."""
import os
from socketserver import ThreadingMixIn
from wsgiref.simple_server import make_server, WSGIServer, WSGIRequestHandler

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')


class PreviewServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


class PrivateLog(WSGIRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, format, *args):
        # Do not log URLs containing client access tokens.
        return


def create_server(application):
    return make_server('127.0.0.1', 0, application, server_class=PreviewServer, handler_class=PrivateLog)


if __name__ == '__main__':
    from django.core.wsgi import get_wsgi_application
    from django.contrib.staticfiles.handlers import StaticFilesHandler
    with create_server(StaticFilesHandler(get_wsgi_application())) as server:
        print(f'Local development preview: http://127.0.0.1:{server.server_port}/', flush=True)
        server.serve_forever()
