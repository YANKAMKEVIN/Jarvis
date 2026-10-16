import unittest
from collections import namedtuple

from jarvis.capabilities.system import SystemCapability

Usage = namedtuple("Usage", ["total", "used", "free"])


def capability_with(total, free):
    return SystemCapability(disk_usage=lambda path: Usage(total, total - free, free))


class StorageStatusTests(unittest.TestCase):
    def test_reports_free_space(self):
        cap = capability_with(total=500 * 10**9, free=200 * 10**9)
        result = cap.get_storage_status()

        self.assertTrue(result.ok)
        self.assertEqual(result.data["free_gb"], 200.0)
        self.assertEqual(result.data["total_gb"], 500.0)
        self.assertEqual(result.data["percent_free"], 40)
        self.assertFalse(result.data["low_space"])

    def test_flags_low_space(self):
        cap = capability_with(total=500 * 10**9, free=20 * 10**9)  # 4%
        result = cap.get_storage_status()

        self.assertTrue(result.data["low_space"])
        self.assertIn("Attention", result.message)

    def test_disk_usage_error_is_handled(self):
        def boom(path):
            raise OSError("no disk")

        result = SystemCapability(disk_usage=boom).get_storage_status()
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "system_error")


if __name__ == "__main__":
    unittest.main()
