"""No skips: guarded real asyncio wakeup, but no arbitrary application sockets."""
import asyncio
import socket
import unittest
from unittest.mock import patch

from native_home_guards import install_windows_asyncio_wakeup, _asyncio_socketpair


class NativeHomeGuardTests(unittest.TestCase):
    def setUp(self):
        install_windows_asyncio_wakeup(self)
        for method in ('bind', 'connect'):
            guard = patch.object(socket.socket, method,
                                 side_effect=AssertionError('Application network forbidden'))
            guard.start()
            self.addCleanup(guard.stop)

    def test_application_loopback_and_non_loopback_bind_connect_stay_blocked(self):
        for address in ('127.0.0.1', '192.0.2.1', '0.0.0.0'):
            for method in ('bind', 'connect'):
                with self.subTest(address=address, method=method), socket.socket() as sock:
                    with self.assertRaisesRegex(AssertionError, 'Application network'):
                        getattr(sock, method)((address, 0))

    def test_application_cannot_call_internal_pair_exception(self):
        with self.assertRaisesRegex(AssertionError, 'Only stdlib asyncio'):
            _asyncio_socketpair()

    def test_asyncio_cross_thread_wakeup_still_runs_with_guards(self):
        async def run():
            event = asyncio.Event()
            loop = asyncio.get_running_loop()
            await asyncio.to_thread(loop.call_soon_threadsafe, event.set)
            await asyncio.wait_for(event.wait(), timeout=5)
            return True
        self.assertTrue(asyncio.run(run()))


if __name__ == '__main__': unittest.main()
