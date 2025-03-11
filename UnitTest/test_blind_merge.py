import json
import sys
import os
import unittest

# Set up the path to import JsonMerge from the parent directory
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)
import JsonMerge

class TestBlindMerge(unittest.TestCase):
    def setUp(self):
        """Set up the test environment before each test."""
        self.merger = JsonMerge.JSONMERGE()
        # Use os.path.join for cross-platform compatibility
        with open(os.path.join(current_dir, 'test-sample-json-data', 'OUTPUT-New-doc-made.json'), 'r') as file1:
            self.base_json = json.load(file1)
        with open(os.path.join(current_dir, 'test-sample-json-data', 'INPUT-Request-change-doc-different.json'), 'r') as file2:
            self.update_json = json.load(file2)

    def test_blind_merge_success(self):
        """Test that blindMerge executes without raising an exception."""
        try:
            result = self.merger.blindMerge(self.base_json, self.update_json)
            self.assertIsNotNone(result, "The merge result should not be None")
            # Add more assertions based on expected output, e.g.:
            # self.assertIn('some_key', result, "Expected key missing in merged data")
        except Exception as e:
            self.fail(f"blindMerge raised an unexpected exception: {e}")

if __name__ == "__main__":
    unittest.main()


