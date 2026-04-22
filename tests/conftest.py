"""Ajusta o sys.path para que os testes possam importar ``cert_reader``
independentemente de onde o pytest for invocado.
"""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
