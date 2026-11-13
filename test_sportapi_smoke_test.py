import unittest

from sportapi_smoke_test import validate_success_payload


class SportAPIPayloadTests(unittest.TestCase):
    def test_accepts_successful_object(self):
        payload = {"success": True, "data": []}
        self.assertIs(validate_success_payload(payload, "/leagues"), payload)

    def test_rejects_provider_error(self):
        with self.assertRaisesRegex(ValueError, "not a successful JSON object"):
            validate_success_payload({"success": False, "error": "bad key"}, "/leagues")

    def test_rejects_non_object(self):
        with self.assertRaises(ValueError):
            validate_success_payload([], "/leagues")


if __name__ == "__main__":
    unittest.main()
