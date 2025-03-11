import json
import sys
import os
import unittest

# Set up paths to import JsonMerge from the parent directory
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)
import JsonMerge

class TestUpdateDoc(unittest.TestCase):
    def setUp(self):
        """Set up the test by initializing the merger and loading JSON files."""
        self.merger = JsonMerge.JSONMERGE()
        # Load the base JSON file (original document to update)
        with open(os.path.join(current_dir, 'test-sample-json-data', 'OUTPUT-New-doc-made.json'), 'r') as file1:
            self.base_json = json.load(file1)
        # Load the update JSON file (changes to apply)
        with open(os.path.join(current_dir, 'test-sample-json-data', 'INPUT-Simple-doc-to-change.json'), 'r') as file2:
            self.update_json = json.load(file2)
        # Load the original simple doc for comparison
        with open(os.path.join(current_dir, 'test-sample-json-data', 'INPUT-Simple-doc.json'), 'r') as file3:
            self.original_json = json.load(file3)

    def test_update_doc_success(self):
        try:
            # Call updateDoc with a base document and a dictionary of updates
            updated_doc = self.merger.updateDoc(self.base_json, self.update_json)
            
            # Verify the update was applied (adjust based on your data)
            for key, value in self.update_json.items():
                self.assertEqual(updated_doc[key], value, f"Field '{key}' was not updated correctly")
            
        except Exception as e:
            self.fail(f"updateDoc raised an unexpected exception: {e}")

if __name__ == "__main__":
    unittest.main()