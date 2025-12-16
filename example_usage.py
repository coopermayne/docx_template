"""
Example script demonstrating how to use the docx_template API
"""
import requests
import sys

# API base URL (change this to your deployed URL on Render)
API_URL = "http://localhost:5000"

def generate_document(params, output_file="output.docx"):
    """
    Generate a document with the given parameters
    
    Args:
        params: Dictionary of parameters to pass to the template
        output_file: Path where the generated document will be saved
    """
    try:
        # Make GET request to the generate endpoint
        response = requests.get(f"{API_URL}/generate", params=params)
        
        # Check if request was successful
        if response.status_code == 200:
            # Save the document
            with open(output_file, 'wb') as f:
                f.write(response.content)
            print(f"✓ Document generated successfully: {output_file}")
            return True
        else:
            # Print error message
            error_data = response.json()
            print(f"✗ Error: {error_data.get('error', 'Unknown error')}")
            print(f"  Message: {error_data.get('message', 'No details')}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"✗ Connection error: {e}")
        print(f"  Make sure the API is running at {API_URL}")
        return False
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return False

def check_api_health():
    """Check if the API is running and healthy"""
    try:
        response = requests.get(f"{API_URL}/health")
        if response.status_code == 200:
            print(f"✓ API is healthy")
            return True
        else:
            print(f"✗ API returned status code: {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ Cannot connect to API: {e}")
        return False

def main():
    """Main example function"""
    print("=== docx_template API Example ===\n")
    
    # Check API health
    print("1. Checking API health...")
    if not check_api_health():
        print("\nPlease start the API first:")
        print("  python app.py")
        sys.exit(1)
    
    print("\n2. Generating sample document...")
    
    # Example parameters
    params = {
        "name": "Jane Smith",
        "company": "Tech Solutions Inc.",
        "date": "2024-12-16",
        "description": "Quarterly Business Report",
        "additional_info": "This document contains confidential information about Q4 2024 performance metrics."
    }
    
    # Generate the document
    success = generate_document(params, "sample_output.docx")
    
    if success:
        print("\n✓ All done! Check sample_output.docx")
    else:
        print("\n✗ Failed to generate document")
        sys.exit(1)

if __name__ == "__main__":
    main()
