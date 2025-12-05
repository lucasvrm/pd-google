import unittest
from services.google_drive_mock import GoogleDriveService
import os
import json

class TestMockDrive(unittest.TestCase):
    def setUp(self):
        # Ensure we start fresh
        self.db_file = "mock_drive_db.json"
        if os.path.exists(self.db_file):
            os.remove(self.db_file)
        self.service = GoogleDriveService()

    def tearDown(self):
        if os.path.exists(self.db_file):
            os.remove(self.db_file)

    def test_create_folder(self):
        folder = self.service.create_folder("Test Folder")
        self.assertEqual(folder["name"], "Test Folder")
        self.assertIn("id", folder)

    def test_upload_file(self):
        file = self.service.upload_file(b"content", "test.txt", "text/plain")
        self.assertEqual(file["name"], "test.txt")
        self.assertEqual(file["size"], 7)

if __name__ == "__main__":
    unittest.main()
