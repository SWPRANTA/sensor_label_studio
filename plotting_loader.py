"""Load this app's plotting helpers without stale, unqualified module imports.

Only the trusted plotting source is refreshed. csv_document and Streamlit
session state are never reloaded, so existing uploaded files/edits stay intact.
"""
from pathlib import Path
from types import ModuleType
import hashlib
import sys
import threading

_REQUIRED = ("GROUPS", "MOTION", "derived_signals", "overview", "label_figure",
             "sensor_figure", "synthetic_demo", "LABEL_COLORS", "label_color",
             "label_intervals", "add_label_shading")
_lock = threading.RLock()
_versions = {}


def load_plotting(app_root):
    path = (Path(app_root).resolve() / "plotting.py")
    source = path.read_bytes()
    version = hashlib.sha256(str(path).encode("utf-8") + b"\\0" + source).hexdigest()
    with _lock:
        if version in _versions:
            return _versions[version]
        name = "_road_sensor_studio_plotting_" + version
        module = ModuleType(name)
        module.__file__ = str(path)
        module.__package__ = ""
        # Compile the source bytes directly: do not reuse plotting in sys.modules
        # or an old timestamp-based .pyc. This is trusted app code, never CSV text.
        exec(compile(source, str(path), "exec"), module.__dict__)
        missing = [name for name in _REQUIRED if not hasattr(module, name)]
        if missing:
            raise ImportError("Incomplete plotting file " + str(path) +
                              "; missing: " + ", ".join(missing))
        sys.modules[name] = module
        _versions[version] = module
        return module
