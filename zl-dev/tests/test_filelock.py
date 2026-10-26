"""Cross-platform lock: fcntl, simulated msvcrt, and refusal when neither exists."""
import builtins
from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import filelock


def without(*names):
    original = builtins.__import__
    def importing(name, *args, **kwargs):
        if name in names:
            raise ImportError(name)
        return original(name, *args, **kwargs)
    return patch.object(builtins, '__import__', side_effect=importing)


class FakeMsvcrt(types.ModuleType):
    LK_NBLCK, LK_UNLCK = 2, 0

    def __init__(self):
        super().__init__('msvcrt')
        self.held, self.calls, self.guard = False, [], threading.Lock()

    def locking(self, fd, mode, size):
        with self.guard:
            self.calls.append(mode)
            if mode == self.LK_NBLCK:
                if self.held:
                    raise OSError('locked')
                self.held = True
            else:
                self.held = False


class FileLockTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.lock = Path(temp.name) / 'x.lock'

    def test_posix_lock_serializes_threads(self):
        order = []
        def worker(tag):
            with filelock.exclusive(self.lock, 'unsupported'):
                order.append(tag + '-in'); order.append(tag + '-out')
        threads = [threading.Thread(target=worker, args=(str(i),)) for i in range(4)]
        [t.start() for t in threads]; [t.join() for t in threads]
        for i in range(0, len(order), 2):
            self.assertEqual(order[i].split('-')[0], order[i + 1].split('-')[0])

    def test_windows_backend_locks_and_unlocks(self):
        fake = FakeMsvcrt()
        with without('fcntl'), patch.dict(sys.modules, {'msvcrt': fake}):
            with filelock.exclusive(self.lock, 'unsupported'):
                self.assertTrue(fake.held)
            self.assertFalse(fake.held)
        self.assertEqual(fake.calls, [fake.LK_NBLCK, fake.LK_UNLCK])

    def test_windows_backend_waits_while_held(self):
        fake = FakeMsvcrt(); fake.held = True
        def release():
            with fake.guard: fake.held = False
        timer = threading.Timer(0.2, release); timer.start()
        with without('fcntl'), patch.dict(sys.modules, {'msvcrt': fake}):
            with filelock.exclusive(self.lock, 'unsupported'):
                self.assertTrue(fake.held)
        timer.join()
        self.assertGreater(fake.calls.count(fake.LK_NBLCK), 1)

    def test_no_backend_refuses_with_caller_message(self):
        with without('fcntl', 'msvcrt'), patch.dict(sys.modules, {'msvcrt': None}):
            with self.assertRaisesRegex(ValueError, '不支持任务写锁'):
                with filelock.exclusive(self.lock, '当前平台不支持任务写锁'):
                    self.fail('must not enter')


if __name__ == '__main__':
    unittest.main()
