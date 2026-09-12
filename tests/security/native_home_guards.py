"""Test-only Windows asyncio wakeup pair; application networking stays blocked.

Windows CPython emulates socketpair with an ephemeral loopback listener. Blanket
bind/connect mocks otherwise fail before ASGI runs. Only the exact stdlib event
loop self-pipe code may use this pair. No application socket method is unpatched.
The temporary listener closes before the pair is returned. Never import in runtime.
"""
import socket
import sys
from unittest.mock import patch

_SOCKET = socket.socket
_BIND = socket.socket.bind
_CONNECT = socket.socket.connect


def _asyncio_socketpair(*args, **kwargs):
    from asyncio.proactor_events import BaseProactorEventLoop
    from asyncio.selector_events import BaseSelectorEventLoop
    callers = (BaseProactorEventLoop._make_self_pipe.__code__,
               BaseSelectorEventLoop._make_self_pipe.__code__)
    if args or kwargs or sys._getframe(1).f_code not in callers:
        raise AssertionError('Only stdlib asyncio wakeup socketpair is permitted')
    listener = _SOCKET(socket.AF_INET, socket.SOCK_STREAM)
    client = server = None
    try:
        listener.settimeout(5)
        _BIND(listener, ('127.0.0.1', 0))
        listener.listen(1)
        client = _SOCKET(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(5)
        _CONNECT(client, listener.getsockname())
        server, peer = listener.accept()
        if peer != client.getsockname() or server.getsockname() != client.getpeername():
            raise AssertionError('Unexpected wakeup peer')
        client.settimeout(None)
        server.settimeout(None)
        return server, client
    except BaseException:
        if client is not None: client.close()
        if server is not None: server.close()
        raise
    finally:
        listener.close()


def install_windows_asyncio_wakeup(testcase):
    if sys.platform == 'win32':
        guard = patch('socket.socketpair', _asyncio_socketpair)
        guard.start()
        testcase.addCleanup(guard.stop)
