from __future__ import annotations

import pathlib
import sys
import unittest


def main() -> int:
    tests_dir = pathlib.Path(__file__).resolve().parent
    suite = unittest.defaultTestLoader.discover(start_dir=str(tests_dir), pattern="test_company_scope_*.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
