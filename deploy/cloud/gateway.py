"""Opt-in ingress for an isolated, publicly shared demonstration deployment.

Native local guards remain unchanged. Only a loopback TLS terminator for the
configured exact origin can enter the internal local application. Never attach
this gateway to a personal/local runtime.
"""
import json
import time
from collections import defaultdict, deque
from urllib.parse import urlsplit


class DemoGateway:
    def __init__(self, app, *, origin, enabled=False):
        parsed = urlsplit(origin)
        if not enabled or parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment or parsed.port:
            raise ValueError('Enable the isolated cloud demo and set an exact HTTPS origin without a path/port')
        self.app, self.origin, self.host = app, origin, parsed.netloc
        self.attempts = defaultdict(deque)

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = dict(scope.get('headers', []))
        client = (scope.get('client') or ('', 0))[0]
        # Caddy is in the same host network; forwarding headers from the public
        # internet must never be trusted directly by Uvicorn.
        host = headers.get(b'host', b'').decode('latin1')
        trusted = client in {'127.0.0.1', '::1'}
        if trusted and urlsplit('//'+host).hostname in {'127.0.0.1', 'localhost'} and scope['path'] == '/__health' and scope['method'] == 'GET':
            return await self.reply(send, 200, 'running')
        if not trusted or host != self.host or headers.get(b'x-forwarded-proto') != b'https':
            return await self.reply(send, 400, 'Invalid deployment origin or TLS proxy')
        origin = headers.get(b'origin')
        if origin and origin.decode('latin1') != self.origin:
            return await self.reply(send, 403, 'Cross-origin request rejected')
        if scope['path'] in {'/docs', '/redoc', '/openapi.json'}:
            return await self.reply(send, 404, 'Not found')
        if scope['method'] not in {'GET', 'HEAD', 'OPTIONS'}:
            if headers.get(b'x-p18-client') != b'workbench':
                return await self.reply(send, 403, 'Use the workbench client')
            if scope['path'] in {'/api/library/login', '/api/library/demo-fill', '/api/library/activate-account', '/api/library/demo-login'}:
                now = time.monotonic()
                for key in list(self.attempts):
                    while self.attempts[key] and self.attempts[key][0] < now - 60:
                        self.attempts[key].popleft()
                    if not self.attempts[key]:
                        del self.attempts[key]
                remote = headers.get(b'x-p18-remote-ip', b'unknown')[:100]
                bucket = self.attempts[remote]
                if len(bucket) >= 40 or len(self.attempts) > 4096:
                    return await self.reply(send, 429, 'Please wait before retrying sign-in')
                bucket.append(now)
        inner = dict(scope)
        inner.update(scheme='http', server=('localhost', 8896), client=('127.0.0.1', 0))
        inner['headers'] = [(k, v) for k, v in scope.get('headers', []) if k not in {b'host', b'origin', b'forwarded', b'x-forwarded-host', b'x-forwarded-proto', b'x-forwarded-for', b'x-p18-remote-ip'}]
        inner['headers'].append((b'host', b'localhost'))
        if origin:
            inner['headers'].append((b'origin', b'http://localhost'))

        async def secure_send(message):
            if message['type'] == 'http.response.start':
                message = dict(message)
                result = []
                for key, value in message.get('headers', []):
                    if key.lower() == b'set-cookie' and b'; secure' not in value.lower():
                        value += b'; Secure'
                    result.append((key, value))
                result.append((b'strict-transport-security', b'max-age=31536000'))
                message['headers'] = result
            await send(message)
        return await self.app(inner, receive, secure_send)

    @staticmethod
    async def reply(send, status, detail):
        body = json.dumps({'detail': detail}).encode()
        await send({'type': 'http.response.start', 'status': status, 'headers': [(b'content-type', b'application/json'), (b'cache-control', b'no-store')]})
        await send({'type': 'http.response.body', 'body': body})
