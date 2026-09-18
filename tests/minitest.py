"""Minimal pytest stand-in for environments where pytest cannot be
installed: runs ``test_*`` functions from the given test modules, supports
``monkeypatch`` (setenv/delenv/setattr/undo) and ``tmp_path``, and honours
``pytest.raises``/``pytest.skip`` through a tiny shim when pytest itself is
absent. Use real pytest whenever it is available:

    python tests/minitest.py test_legacy_contract test_policy
"""

import importlib
import inspect
import os
import sys
import tempfile
import traceback
import types
from pathlib import Path


class MonkeyPatch:
    def __init__(self):
        self._env = []
        self._attrs = []

    def setenv(self, k, v):
        self._env.append((k, os.environ.get(k)))
        os.environ[k] = v

    def delenv(self, k, raising=True):
        self._env.append((k, os.environ.get(k)))
        if k in os.environ:
            del os.environ[k]
        elif raising:
            raise KeyError(k)

    def setattr(self, obj, name, value):
        self._attrs.append((obj, name, getattr(obj, name)))
        setattr(obj, name, value)

    def undo(self):
        for k, old in reversed(self._env):
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old
        for obj, name, old in reversed(self._attrs):
            setattr(obj, name, old)
        self._env, self._attrs = [], []


class _Raises:
    def __init__(self, exc, match=None):
        self.exc, self.match, self.value = exc, match, None

    def __enter__(self):
        return self

    def __exit__(self, et, ev, tb):
        if et is None:
            raise AssertionError(f"did not raise {self.exc.__name__}")
        if not issubclass(et, self.exc):
            return False
        if self.match and self.match not in str(ev):
            raise AssertionError(f"{ev!r} does not contain {self.match!r}")
        self.value = ev
        return True


class _Skip(Exception):
    pass


def _install_pytest_shim():
    if "pytest" in sys.modules:
        return
    try:
        import pytest  # noqa: F401
        return
    except ImportError:
        pass
    shim = types.ModuleType("pytest")
    shim.raises = _Raises

    def skip(reason=""):
        raise _Skip(reason)
    shim.skip = skip

    class _Mark:
        def __getattr__(self, name):
            def deco(*a, **k):
                return a[0] if a and callable(a[0]) else deco
            return deco
    shim.mark = _Mark()

    def fixture(*a, **k):
        return a[0] if a and callable(a[0]) else (lambda f: f)
    shim.fixture = fixture
    sys.modules["pytest"] = shim


def main(modnames):
    root = os.getcwd()
    sys.path.insert(0, root)
    sys.path.insert(0, os.path.join(root, "tests"))
    _install_pytest_shim()
    passed = failed = skipped = 0
    for modname in modnames:
        mod = importlib.import_module(modname)
        for name, fn in inspect.getmembers(mod, inspect.isfunction):
            if not name.startswith("test_") or fn.__module__ != mod.__name__:
                continue
            kwargs, patch = {}, None
            params = inspect.signature(fn).parameters
            if "monkeypatch" in params:
                patch = MonkeyPatch()
                kwargs["monkeypatch"] = patch
            if "tmp_path" in params:
                kwargs["tmp_path"] = Path(tempfile.mkdtemp(prefix="mt-"))
            try:
                fn(**kwargs)
                passed += 1
                print(f"PASS {modname}.{name}")
            except _Skip as exc:
                skipped += 1
                print(f"SKIP {modname}.{name} ({exc})")
            except Exception:  # noqa: BLE001
                failed += 1
                print(f"FAIL {modname}.{name}")
                traceback.print_exc()
            finally:
                if patch:
                    patch.undo()
    print(f"\n{passed} passed, {failed} failed, {skipped} skipped")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
