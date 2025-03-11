import json
import sys
import os
import unittest

# Set up the path to import JsonMerge from the parent directory
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)
import JsonMerge

class TestMakeNewDoc(unittest.TestCase):
    def setUp(self):
        """Prepare the environment before each test."""
        self.merger = JsonMerge.JSONMERGE()
        input_file = os.path.join(current_dir, 'test-sample-json-data', 'INPUT-Simple-doc.json')
        with open(input_file, 'r') as file:
            self.input_json = json.load(file)

    def test_his_exists(self):
        """Test that the '_his' key exists in the output."""
        data = self.merger.makeNewDoc(self.input_json)
        self.assertIn('_his', data, "_his key is missing")

    def test_his_not_empty(self):
        """Test that '_his' is not empty."""
        data = self.merger.makeNewDoc(self.input_json)
        self.assertTrue(data['_his'], "_his is empty")

    def test_upDtEp_exists(self):
        """Test that the 'upDtEp' key exists in the output."""
        data = self.merger.makeNewDoc(self.input_json)
        self.assertIn('upDtEp', data, "upDtEp key is missing")

    def test_upDtEp_is_int(self):
        """Test that 'upDtEp' is an integer."""
        data = self.merger.makeNewDoc(self.input_json)
        self.assertIsInstance(data['upDtEp'], int, "upDtEp is not an integer")

if __name__ == "__main__":
    unittest.main()