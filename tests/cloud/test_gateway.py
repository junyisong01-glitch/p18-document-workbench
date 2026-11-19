import asyncio
import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[2] / 'deploy/cloud/gateway.py'
spec = importlib.util.spec_from_file_location('cloud_gateway', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class GatewayTests(unittest.TestCase):
    def run_request(self, *, host='demo.example.com', origin='https://demo.example.com', proto='https', client='127.0.0.1', custom=True, path='/api/library/demo-fill', method='POST'):
        messages, seen = [], []
        async def native(scope, receive, send):
            seen.append(scope)
            await send({'type': 'http.response.start', 'status': 200, 'headers': [(b'set-cookie', b'p18_session=test; HttpOnly; SameSite=strict')]})
            await send({'type': 'http.response.body', 'body': b'{}'})
        app = module.DemoGateway(native, enabled=True, origin='https://demo.example.com')
        async def receive(): return {'type': 'http.request', 'body': b'', 'more_body': False}
        async def send(message): messages.append(message)
        headers = [(b'host', host.encode()), (b'x-forwarded-proto', proto.encode())]
        if custom: headers.append((b'x-p18-client', b'workbench'))
        if origin: headers.append((b'origin', origin.encode()))
        asyncio.run(app({'type': 'http', 'method': method, 'path': path, 'client': (client, 4), 'headers': headers}, receive, send))
        return messages, seen

    def test_only_explicit_exact_https_origin(self):
        for origin in ['http://demo.example.com', 'https://demo.example.com/path', 'https://u:p@demo.example.com', 'https://demo.example.com:443', '']:
            with self.assertRaises(ValueError): module.DemoGateway(None, enabled=True, origin=origin)
        with self.assertRaises(ValueError): module.DemoGateway(None, enabled=False, origin='https://demo.example.com')

    def test_cross_origin_missing_header_and_untrusted_proxy_never_reach_native(self):
        for args in [dict(host='evil.example.com'), dict(origin='https://evil.example.com'), dict(proto='http'), dict(client='198.51.100.1'), dict(custom=False)]:
            messages, seen = self.run_request(**args)
            self.assertGreaterEqual(messages[0]['status'], 400)
            self.assertEqual(seen, [])

    def test_local_health_with_port_does_not_enter_native_app(self):
        messages, seen = self.run_request(host='127.0.0.1:8896', path='/__health', method='GET', origin=None, proto='http', custom=False)
        self.assertEqual(messages[0]['status'], 200)
        self.assertEqual(seen, [])

    def test_trusted_origin_retains_native_guards_and_cookie_is_secure(self):
        messages, seen = self.run_request()
        self.assertEqual(messages[0]['status'], 200)
        headers = dict(seen[0]['headers'])
        self.assertEqual(headers[b'host'], b'localhost')
        self.assertEqual(headers[b'origin'], b'http://localhost')
        self.assertEqual(headers[b'x-p18-client'], b'workbench')
        self.assertEqual(seen[0]['client'][0], '127.0.0.1')
        self.assertIn(b'; Secure', dict(messages[0]['headers'])[b'set-cookie'])


if __name__ == '__main__': unittest.main()
