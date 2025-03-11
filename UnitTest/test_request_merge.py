import json
import sys
import os
import unittest

# Set up paths to import JsonMerge from the parent directory
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)
import JsonMerge

class TestMergeDocReq(unittest.TestCase):
    def setUp(self):
        """Set up the test by initializing the merger and loading JSON files."""
        self.merger = JsonMerge.JSONMERGE()
        # Load the base JSON file (assuming this file is used elsewhere in the test)
        with open(os.path.join(current_dir, 'test-sample-json-data', 'OUTPUT-New-doc-made.json'), 'r') as file1:
            self.base_json = json.load(file1)
        # Load the request JSON file (corrected to an existing file)
        with open(os.path.join(current_dir, 'test-sample-json-data', 'INPUT-Request-change-doc-different.json'), 'r') as file2:
            self.request_json = json.load(file2)

    def test_merge_doc_req_success(self):
        """Test that mergeDocReq runs successfully and returns a non-None result."""
        try:
            result = self.merger.mergeDocReq(self.base_json, self.request_json)
            self.assertIsNotNone(result, "The merge result should not be None")
            # Add more specific assertions here if you know the expected output
        except Exception as e:
            self.fail(f"mergeDocReq raised an unexpected exception: {e}")

if __name__ == "__main__":
    unittest.main()