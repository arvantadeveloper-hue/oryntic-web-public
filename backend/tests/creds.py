"""Test credentials — read from the environment (backend/.env), never hardcoded in test files."""
import os

from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

DEMO_EMAIL = os.environ.get("TEST_DEMO_EMAIL", "demo@aivora.ai")
DEMO_PASSWORD = os.environ["TEST_DEMO_PASSWORD"]
ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "admin@aivora.ai")
ADMIN_PASSWORD = os.environ["ADMIN_PASSWORD"]
BUDI_EMAIL = os.environ.get("TEST_BUDI_EMAIL", "budi@aivora.ai")
BUDI_PASSWORD = os.environ.get("TEST_BUDI_PASSWORD", DEMO_PASSWORD)
