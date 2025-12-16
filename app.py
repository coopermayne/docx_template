from flask import Flask, request, send_file, jsonify
from docxtpl import DocxTemplate
import os
import tempfile
from datetime import datetime

app = Flask(__name__)

# Template directory
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), 'templates')

@app.route('/')
def index():
    """Root endpoint with API information"""
    return jsonify({
        'message': 'docx_template API',
        'version': '1.0.0',
        'endpoints': {
            '/generate': 'GET - Generate a Word document from template with query parameters',
            '/health': 'GET - Health check endpoint'
        }
    })

@app.route('/health')
def health():
    """Health check endpoint for deployment monitoring"""
    return jsonify({'status': 'healthy'}), 200

@app.route('/generate')
def generate_document():
    """
    Generate a Word document from template with provided parameters.
    
    Query Parameters:
    - template: name of the template file (default: 'default_template.docx')
    - All other parameters will be passed as context to the template
    
    Example:
    /generate?name=John&company=Acme&date=2024-01-01
    """
    try:
        # Get template name from query params or use default
        template_name = request.args.get('template', 'default_template.docx')
        template_path = os.path.join(TEMPLATE_DIR, template_name)
        
        # Check if template exists
        if not os.path.exists(template_path):
            return jsonify({
                'error': 'Template not found',
                'template': template_name,
                'available_templates': os.listdir(TEMPLATE_DIR) if os.path.exists(TEMPLATE_DIR) else []
            }), 404
        
        # Load the document template
        doc = DocxTemplate(template_path)
        
        # Get all query parameters except 'template' to use as context
        context = {key: value for key, value in request.args.items() if key != 'template'}
        
        # Add timestamp if not provided
        if 'generated_date' not in context:
            context['generated_date'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Render the template with context
        doc.render(context)
        
        # Create a temporary file to save the generated document
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.docx')
        doc.save(temp_file.name)
        temp_file.close()
        
        # Generate filename for download
        output_filename = f"generated_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
        
        # Send the file and clean up
        response = send_file(
            temp_file.name,
            as_attachment=True,
            download_name=output_filename,
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
        
        # Clean up temp file after sending
        @response.call_on_close
        def cleanup():
            try:
                os.unlink(temp_file.name)
            except Exception:
                pass
        
        return response
        
    except Exception as e:
        return jsonify({
            'error': 'Failed to generate document',
            'message': str(e)
        }), 500

if __name__ == '__main__':
    # Run the app
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
