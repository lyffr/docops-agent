import unittest

from docops_agent.security import ApiKeyAuthenticator, Principal


class ApiKeyAuthenticatorTests(unittest.TestCase):
    def test_development_mode_without_keys_uses_an_admin_principal(self) -> None:
        authenticator = ApiKeyAuthenticator()

        principal = authenticator.authenticate(None)

        self.assertEqual(principal, Principal(name="development", role="admin"))
        self.assertTrue(authenticator.authorize(principal, "admin"))

    def test_configured_keys_authenticate_and_enforce_roles(self) -> None:
        authenticator = ApiKeyAuthenticator(
            "viewer:reader:viewer-secret-with-24-chars,ops:operator:operator-secret-with-24-chars"
        )

        viewer = authenticator.authenticate("viewer-secret-with-24-chars")
        operator = authenticator.authenticate("operator-secret-with-24-chars")

        self.assertEqual(viewer.name, "viewer")
        self.assertTrue(authenticator.authorize(viewer, "read"))
        self.assertFalse(authenticator.authorize(viewer, "operate"))
        self.assertTrue(authenticator.authorize(operator, "operate"))
        self.assertIsNone(authenticator.authenticate("wrong"))

    def test_invalid_or_missing_production_keys_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "required in production"):
            ApiKeyAuthenticator(required=True)
        with self.assertRaisesRegex(ValueError, "at least 24"):
            ApiKeyAuthenticator("admin:admin:short")
        with self.assertRaisesRegex(ValueError, "role"):
            ApiKeyAuthenticator("user:owner:a-very-long-secret-value")
        with self.assertRaisesRegex(ValueError, "unique"):
            ApiKeyAuthenticator(
                "first:reader:the-same-long-secret-value,second:admin:the-same-long-secret-value"
            )


if __name__ == "__main__":
    unittest.main()
