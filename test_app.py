"""
Simple tests for the docx_template API
"""
import unittest
import os
import tempfile
from app import app

class TestDocxTemplateAPI(unittest.TestCase):
    """Test cases for the API endpoints"""
    
    def setUp(self):
        """Set up test client"""
        self.app = app.test_client()
        self.app.testing = True
    
    def test_root_endpoint(self):
        """Test the root endpoint returns API info"""
        response = self.app.get('/')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn('message', data)
        self.assertIn('version', data)
        self.assertIn('endpoints', data)
    
    def test_health_endpoint(self):
        """Test the health check endpoint"""
        response = self.app.get('/health')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['status'], 'healthy')
    
    def test_generate_with_default_template(self):
        """Test document generation with default template"""
        response = self.app.get('/generate?name=Test&company=TestCorp')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.content_type,
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
        # Verify it's a valid DOCX file by checking the header
        self.assertTrue(response.data.startswith(b'PK'))  # ZIP file signature
    
    def test_generate_with_missing_template(self):
        """Test error handling for non-existent template"""
        response = self.app.get('/generate?template=nonexistent.docx')
        self.assertEqual(response.status_code, 404)
        data = response.get_json()
        self.assertIn('error', data)
        self.assertEqual(data['error'], 'Template not found')
    
    def test_generate_with_all_parameters(self):
        """Test document generation with multiple parameters"""
        params = {
            'name': 'John Doe',
            'company': 'Acme Corp',
            'date': '2024-12-16',
            'description': 'Test Description',
            'additional_info': 'Additional test info'
        }
        query_string = '&'.join([f'{k}={v}' for k, v in params.items()])
        response = self.app.get(f'/generate?{query_string}')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data.startswith(b'PK'))
    
    def test_template_directory_exists(self):
        """Test that templates directory exists"""
        template_dir = os.path.join(os.path.dirname(__file__), 'templates')
        self.assertTrue(os.path.exists(template_dir))
    
    def test_default_template_exists(self):
        """Test that default template exists"""
        template_path = os.path.join(
            os.path.dirname(__file__),
            'templates',
            'default_template.docx'
        )
        self.assertTrue(os.path.exists(template_path))

if __name__ == '__main__':
    unittest.main()
