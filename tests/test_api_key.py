from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.db import Database
from app.main import _mask_api_key


class ApiKeyStorageTest(unittest.TestCase):
    def test_database_keeps_one_updatable_key(self):
        with TemporaryDirectory() as directory:
            database = Database(Path(directory) / "test.db")
            database.initialize("first-key")
            database.initialize("second-key")

            self.assertEqual(database.get_api_key(), "first-key")
            database.update_api_key("updated-key")
            self.assertEqual(database.get_api_key(), "updated-key")

            with database.connection() as connection:
                count = connection.execute("SELECT COUNT(*) FROM api_keys").fetchone()[0]
            self.assertEqual(count, 1)

    def test_key_is_masked(self):
        self.assertEqual(_mask_api_key("test-key-123456"), "test...3456")


if __name__ == "__main__":
    unittest.main()
