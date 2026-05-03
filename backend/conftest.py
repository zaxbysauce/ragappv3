"""Pytest configuration for backend tests."""

import sys
import types
from pathlib import Path

# Add backend directory to path so tests can import app modules
sys.path.insert(0, str(Path(__file__).parent))

# Stub problematic optional dependencies BEFORE any test imports
# This must happen before pytest collection to prevent import errors

# Stub lancedb (imports lancedb.index.IvfPq, FTS)
_lancedb = types.ModuleType("lancedb")
_lancedb.index = types.ModuleType("lancedb.index")
# Add fake IvfPq, FTS classes to prevent import errors
_lancedb.index.IvfPq = type("IvfPq", (), {})
_lancedb.index.FTS = type("FTS", (), {})
sys.modules["lancedb"] = _lancedb
sys.modules["lancedb.index"] = _lancedb.index

# Stub pyarrow only when the real package is unavailable. Replacing a real
# pyarrow install with an attribute-less stub breaks `import pandas`, because
# pandas.compat.pyarrow reads `pyarrow.__version__` during its own import.
try:
    import pyarrow  # noqa: F401
except ImportError:
    _pa_stub = types.ModuleType("pyarrow")
    _pa_stub.__version__ = "0.0.0"
    sys.modules["pyarrow"] = _pa_stub

# Stub jwt (PyJWT) — system-level jwt has a broken C extension in this env.
# Only stub when the real import fails so a working install is not replaced.
try:
    # Attempt to import the actual jwt; if the C extension is broken it raises.
    _jwt_check = __import__("jwt")
    _jwt_check.ExpiredSignatureError  # attribute probe to catch partially-broken installs
except Exception:
    _jwt_stub = types.ModuleType("jwt")
    _jwt_stub.encode = lambda *a, **kw: "stub-token"
    _jwt_stub.decode = lambda *a, **kw: {}
    _jwt_stub.ExpiredSignatureError = type("ExpiredSignatureError", (Exception,), {})
    _jwt_stub.InvalidTokenError = type("InvalidTokenError", (Exception,), {})
    sys.modules["jwt"] = _jwt_stub

# Stub unstructured
_unstructured = types.ModuleType("unstructured")
_unstructured.partition = types.ModuleType("unstructured.partition")
_unstructured.partition.auto = types.ModuleType("unstructured.partition.auto")
_unstructured.partition.auto.partition = lambda *args, **kwargs: []
_unstructured.chunking = types.ModuleType("unstructured.chunking")
_unstructured.chunking.title = types.ModuleType("unstructured.chunking.title")
_unstructured.chunking.title.chunk_by_title = lambda *args, **kwargs: []
_unstructured.documents = types.ModuleType("unstructured.documents")
_unstructured.documents.elements = types.ModuleType("unstructured.documents.elements")
_unstructured.documents.elements.Element = type("Element", (), {})
_unstructured.file_utils = types.ModuleType("unstructured.file_utils")
_unstructured.file_utils.filetype = types.ModuleType("unstructured.file_utils.filetype")
sys.modules["unstructured"] = _unstructured
sys.modules["unstructured.partition"] = _unstructured.partition
sys.modules["unstructured.partition.auto"] = _unstructured.partition.auto
sys.modules["unstructured.chunking"] = _unstructured.chunking
sys.modules["unstructured.chunking.title"] = _unstructured.chunking.title
sys.modules["unstructured.documents"] = _unstructured.documents
sys.modules["unstructured.documents.elements"] = _unstructured.documents.elements
sys.modules["unstructured.file_utils"] = _unstructured.file_utils
sys.modules["unstructured.file_utils.filetype"] = _unstructured.file_utils.filetype
