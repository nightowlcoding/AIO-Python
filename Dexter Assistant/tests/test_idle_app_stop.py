from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests._dexter_test_harness import load_dexter_module

_mod = load_dexter_module()


class _FakeProc:
    """Stands in for a running subprocess.Popen child."""

    def __init__(self) -> None:
        self.terminated = False
        self.returncode: int | None = None
        self.pid = 12345

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = 0

    def kill(self) -> None:
        self.terminated = True
        self.returncode = -9

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode if self.returncode is not None else 0


class TestStopIdleApps(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = _mod.AppManager(_mod.CONFIG)
        names = list(_mod.CONFIG["apps"].keys())
        self.idle_name = names[0]
        self.active_name = names[1]

    def _fake_start(self, name: str, last_activity: float) -> _FakeProc:
        proc = _FakeProc()
        self.manager._procs[name] = proc
        self.manager._last_activity[name] = last_activity
        return proc

    def test_idle_app_stopped_and_active_app_kept(self):
        now = time.time()
        idle_proc = self._fake_start(self.idle_name, now - 3600)
        active_proc = self._fake_start(self.active_name, now)

        stopped = self.manager.stop_idle_apps(600)

        self.assertEqual(stopped, [self.idle_name])
        self.assertTrue(idle_proc.terminated)
        self.assertFalse(active_proc.terminated)
        self.assertFalse(self.manager.is_running(self.idle_name))
        self.assertTrue(self.manager.is_running(self.active_name))

    def test_disabled_timeout_is_noop(self):
        proc = self._fake_start(self.idle_name, time.time() - 3600)

        self.assertEqual(self.manager.stop_idle_apps(0), [])
        self.assertEqual(self.manager.stop_idle_apps(-5), [])
        self.assertFalse(proc.terminated)

    def test_touch_keeps_app_alive(self):
        proc = self._fake_start(self.idle_name, time.time() - 3600)

        self.manager.touch(self.idle_name)
        stopped = self.manager.stop_idle_apps(600)

        self.assertEqual(stopped, [])
        self.assertFalse(proc.terminated)

    def test_touch_resolves_manager_alias(self):
        # The proxy may address managerapp via its "manager" alias.
        if "managerapp" not in _mod.CONFIG["apps"]:
            self.skipTest("managerapp not configured")
        proc = self._fake_start("managerapp", time.time() - 3600)

        self.manager.touch("manager")
        stopped = self.manager.stop_idle_apps(600)

        self.assertEqual(stopped, [])
        self.assertFalse(proc.terminated)


if __name__ == "__main__":
    unittest.main(verbosity=2)
