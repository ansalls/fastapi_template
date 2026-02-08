"""Domain extension package.

Add feature domains as packages under ``app/domains/<name>/`` with a
``router.py`` module that exports ``router = APIRouter(...)``.
Routers are auto-discovered and mounted under ``/api/v1``.
"""

