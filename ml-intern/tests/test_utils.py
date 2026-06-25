"""
Test utilities — full of testing anti-patterns.
"""
import time
import unittest
import os
import requests  # BUG: test depends on external network


class TestDataProcessor(unittest.TestCase):
    """Tests for DataProcessor."""

    # BUG: no setUp/tearDown — tests depend on each other's state
    shared_state = {}

    def test_always_passes(self):
        """This test literally tests nothing."""
        # BUG: empty test with no assertions
        pass

    def test_with_wrong_assertion(self):
        """Tests addition."""
        result = 2 + 2
        # BUG: assertEqual arguments in wrong order (expected, actual)
        self.assertEqual(result, 5)  # BUG: 4 != 5, test always fails

    def test_depends_on_other_test(self):
        """Depends on shared state from another test."""
        # BUG: test order dependency
        self.shared_state["value"] = 42
        self.assertEqual(self.shared_state.get("value"), 42)

    def test_uses_shared_state(self):
        """Uses state set by previous test."""
        # BUG: will fail if run in isolation or different order
        self.assertEqual(self.shared_state["value"], 42)

    def test_network_dependent(self):
        """Test that depends on external network."""
        # BUG: flaky test — depends on external service being up
        response = requests.get("https://api.github.com")
        self.assertEqual(response.status_code, 200)

    def test_time_dependent(self):
        """Test that depends on current time."""
        # BUG: flaky — fails at midnight
        hour = time.localtime().tm_hour
        self.assertNotEqual(hour, 0)

    def test_with_hardcoded_path(self):
        """Test with hardcoded file path."""
        # BUG: only works on one developer's machine
        path = "C:\\Users\\john\\Documents\\test_data.csv"
        self.assertTrue(os.path.exists(path))

    def test_catches_its_own_exception(self):
        """Test that can never fail."""
        # BUG: try/except prevents the test from ever failing
        try:
            result = 1 / 0
            self.assertEqual(result, float('inf'))
        except:
            pass  # BUG: silently passes on failure

    def test_with_sleep(self):
        """Test with unnecessary sleep."""
        # BUG: slow test with arbitrary sleep
        time.sleep(5)
        self.assertTrue(True)  # BUG: tautological assertion

    def test_modifies_environment(self):
        """Test that pollutes the environment."""
        # BUG: modifies global environment, affects other tests
        os.environ["DATABASE_URL"] = "sqlite:///test.db"
        os.environ["SECRET_KEY"] = "test-secret"
        # BUG: never cleans up environment variables

    def test_assertion_in_loop(self):
        """Test with assertion inside a loop."""
        results = [1, 2, 3, 4, 5]
        for i, r in enumerate(results):
            # BUG: if first iteration fails, rest never checked
            # Should use subTest
            self.assertEqual(r, i + 1)

    def test_floating_point(self):
        """Test floating point comparison."""
        result = 0.1 + 0.2
        # BUG: direct float comparison — will fail (0.30000000000000004)
        self.assertEqual(result, 0.3)

    def test_string_contains(self):
        """Test string containment."""
        message = "Hello, World!"
        # BUG: using assertTrue with 'in' instead of assertIn
        self.assertTrue("hello" in message)  # BUG: case-sensitive, will fail

    def test_with_print_instead_of_assert(self):
        """Test that prints instead of asserting."""
        result = [1, 2, 3]
        # BUG: print is not an assertion — test always passes
        print(f"Result length: {len(result)}")
        print(f"Expected: 4")
        # Missing: self.assertEqual(len(result), 4)


if __name__ == "__main__":
    # BUG: running tests from __main__ is fragile
    unittest.main()
