import unittest
import tempfile
import os

from tools import ReadFileTool, WriteFileTool

class TestFileTools(unittest.TestCase):
    def setUp(self):
        self.read_tool = ReadFileTool()
        self.write_tool = WriteFileTool()

    def test_read_file_success(self):
        """Test successful reading of a file's content."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_file:
            test_content = "Hello, World!\nThis is a test."
            temp_file.write(test_content)
            temp_file_path = temp_file.name

        try:
            result = self.read_tool.execute(file_path=temp_file_path)
            self.assertEqual(result, test_content)
        finally:
            os.unlink(temp_file_path)

    def test_read_file_nonexistent(self):
        """Test handling of a non-existent file."""
        nonexistent_path = "/tmp/nonexistent_file.txt"
        result = self.read_tool.execute(file_path=nonexistent_path)
        self.assertIn("File not found in working directory or app directory", result)

    def test_write_file_create_new(self):
        """Test successful creation and writing to a new file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, "new_file.txt")
            test_content = "This is new content."

            result = self.write_tool.execute(file_path=file_path, content=test_content)
            self.assertEqual(result, f"File written successfully: {file_path}")

            # Verify the file was created and has correct content
            with open(file_path, 'r') as f:
                self.assertEqual(f.read(), test_content)

    def test_write_file_create_directories(self):
        """Test creating necessary parent directories if they do not exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            nested_dir = os.path.join(temp_dir, "nested", "deep")
            file_path = os.path.join(nested_dir, "file.txt")
            test_content = "Content in nested directory."

            result = self.write_tool.execute(file_path=file_path, content=test_content)
            self.assertEqual(result, f"File written successfully: {file_path}")

            # Verify directories were created
            self.assertTrue(os.path.exists(nested_dir))

            # Verify file content
            with open(file_path, 'r') as f:
                self.assertEqual(f.read(), test_content)

    def test_write_file_overwrite_existing(self):
        """Test successful overwriting of an existing file."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_file:
            original_content = "Original content."
            temp_file.write(original_content)
            temp_file_path = temp_file.name

        try:
            new_content = "New content overwriting the old."
            result = self.write_tool.execute(file_path=temp_file_path, content=new_content)
            self.assertEqual(result, f"File written successfully: {temp_file_path}")

            # Verify the content was overwritten
            with open(temp_file_path, 'r') as f:
                self.assertEqual(f.read(), new_content)
        finally:
            os.unlink(temp_file_path)

if __name__ == '__main__':
    unittest.main()
