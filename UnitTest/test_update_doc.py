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
        """Test that updateDoc runs successfully and updates the document as expected."""
        try:
            updated_data = self.merger.updateDoc(self.base_json, self.update_json)
            self.assertIsNotNone(updated_data, "The updated data should not be None")

            # Check if _his exists
            self.assertIn('_his', updated_data, "_his key is missing")
            # Check if _his is not empty
            self.assertTrue(updated_data['_his'], "_his exists but is empty")
            self.assertGreater(len(updated_data['_his'].keys()), 0, "_his has no keys")

            # Check if apples have changed compared to the original document
            self.assertNotEqual(self.original_json.get('apples'), updated_data.get('apples'), 
                               f"apples field was not updated. Old: {self.original_json.get('apples')}, New: {updated_data.get('apples')}")

            # Check if the new key from the second item in update_json is present
            new_key = list(self.update_json[1].keys())[0]  # Get the key from the second item
            self.assertIn(new_key, updated_data, f"New key '{new_key}' from update_json is missing")

            # Check if upDtEp exists
            self.assertIn('upDtEp', updated_data, "upDtEp key is missing")
            # Check if upDtEp is an integer (epoch time)
            self.assertIsInstance(updated_data['upDtEp'], int, "upDtEp is not an integer")

        except Exception as e:
            self.fail(f"updateDoc raised an unexpected exception: {e}")

if __name__ == "__main__":
    unittest.main()