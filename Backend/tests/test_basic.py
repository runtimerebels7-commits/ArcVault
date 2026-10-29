import os
import tempfile
import unittest
import sys
from pathlib import Path

# Ensure the Backend directory is importable when pytest is run from the project root.
BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]
if str(BACKEND_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIRECTORY))

# Use a temporary database before importing app/database modules.
tmp = tempfile.NamedTemporaryFile(delete=False)
os.environ["DATABASE_PATH"] = tmp.name
os.environ["FLASK_SECRET_KEY"] = "test-secret-key"
tmp.close()

from app import app


class BackendSmokeTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_health(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["status"], "ok")

    def test_register_and_create_publication(self):
        response = self.client.post("/api/auth/register", json={
            "name": "Test Publisher",
            "email": "test@example.com",
            "password": "example-pass-123"
        })
        self.assertEqual(response.status_code, 201)
        response = self.client.post("/api/publications", json={
            "title": "Sample Kannada Dataset",
            "language": "Kannada",
            "description": "Fictional test metadata",
            "licence_type": "research_only",
            "licence_terms": "Research use only",
            "licensing_cost": 1000,
            "value_score": 8,
            "allowed_uses": ["research"]
        })
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json["publication"]["rights_verified"], False)


if __name__ == "__main__":
    unittest.main()
