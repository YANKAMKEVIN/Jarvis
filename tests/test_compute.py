import unittest

from jarvis.capabilities.compute import ComputeCapability


class CalculateTests(unittest.TestCase):
    def setUp(self):
        self.cap = ComputeCapability()

    def test_basic_arithmetic(self):
        r = self.cap.calculate("(12 + 8) * 3")
        self.assertTrue(r.ok)
        self.assertEqual(r.data["result"], 60)
        self.assertEqual(r.data["result_text"], "60")

    def test_percentage_and_float(self):
        r = self.cap.calculate("0.15 * 240")
        self.assertTrue(r.ok)
        self.assertEqual(r.data["result"], 36)

    def test_functions_and_constants(self):
        r = self.cap.calculate("sqrt(2)")
        self.assertTrue(r.ok)
        self.assertEqual(r.data["result_text"], "1.4142")

    def test_rejects_names_and_calls(self):
        self.assertFalse(self.cap.calculate("__import__('os')").ok)
        self.assertFalse(self.cap.calculate("open('x')").ok)
        self.assertFalse(self.cap.calculate("foo").ok)

    def test_guards_huge_power(self):
        r = self.cap.calculate("10 ** 100000")
        self.assertFalse(r.ok)
        self.assertEqual(r.error_code, "value_too_large")

    def test_empty(self):
        self.assertFalse(self.cap.calculate("   ").ok)


class ConvertTests(unittest.TestCase):
    def setUp(self):
        self.cap = ComputeCapability()

    def test_length(self):
        r = self.cap.convert_units(10, "km", "mi")
        self.assertTrue(r.ok)
        self.assertAlmostEqual(r.data["result"], 6.2137, places=3)

    def test_mass(self):
        r = self.cap.convert_units(180, "lb", "kg")
        self.assertTrue(r.ok)
        self.assertAlmostEqual(r.data["result"], 81.6466, places=2)

    def test_temperature(self):
        r = self.cap.convert_units(72, "F", "C")
        self.assertTrue(r.ok)
        self.assertAlmostEqual(r.data["result"], 22.2222, places=2)

    def test_incompatible(self):
        r = self.cap.convert_units(10, "km", "kg")
        self.assertFalse(r.ok)
        self.assertEqual(r.error_code, "incompatible_units")

    def test_unknown_unit(self):
        r = self.cap.convert_units(10, "km", "bananes")
        self.assertFalse(r.ok)
        self.assertEqual(r.error_code, "incompatible_units")

    def test_bad_value(self):
        r = self.cap.convert_units("beaucoup", "km", "mi")
        self.assertFalse(r.ok)
        self.assertEqual(r.error_code, "invalid_value")


if __name__ == "__main__":
    unittest.main()
