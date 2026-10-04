"""Test-account credentials: override via env (TEST_DEMO_PASSWORD, TEST_BUDI_PASSWORD, TEST_ADMIN_PASSWORD); defaults = preview demo accounts."""
import os

DEMO_EMAIL = os.environ.get("TEST_DEMO_EMAIL", "demo@aivora.ai")
DEMO_PASSWORD = os.environ.get("TEST_DEMO_PASSWORD", "demo123456")
BUDI_EMAIL = os.environ.get("TEST_BUDI_EMAIL", "budi@aivora.ai")
BUDI_PASSWORD = os.environ.get("TEST_BUDI_PASSWORD", "budi123456")
ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "admin@aivora.ai")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD") or os.environ.get("ADMIN_PASSWORD", "")
