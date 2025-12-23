from flask import Flask, request, send_file, jsonify, send_from_directory
from flask_cors import CORS
from docxtpl import DocxTemplate
import os
import tempfile
from datetime import datetime

from config import Config

app = Flask(__name__, static_folder='static', template_folder='templates')
app.config.from_object(Config)

# Enable CORS for API endpoints
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Ensure upload and session directories exist
os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
os.makedirs(Config.SESSION_PERSIST_DIR, exist_ok=True)

# Template directory for Word documents
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), 'templates')

# Register blueprints
from api.session import session_bp
from api.rfp import rfp_bp
from api.documents import documents_bp
from api.objections import objections_bp
from api.analyze import analyze_bp
from api.generate import generate_bp
from api.motion_opposition import motion_opposition_bp
from api.users import users_bp

app.register_blueprint(session_bp)
app.register_blueprint(rfp_bp)
app.register_blueprint(documents_bp)
app.register_blueprint(objections_bp)
app.register_blueprint(analyze_bp)
app.register_blueprint(generate_bp)
app.register_blueprint(motion_opposition_bp)
app.register_blueprint(users_bp)


@app.route('/')
def index():
    """Serve the main SPA page."""
    return send_from_directory('templates', 'index.html')


@app.route('/api')
def api_info():
    """API information endpoint."""
    return jsonify({
        'message': 'Legal RFP Response Tool API',
        'version': '2.0.0',
        'endpoints': {
            '/api/session/create': 'POST - Create a new session',
            '/api/session/<id>': 'GET/DELETE - Get or delete session',
            '/api/rfp/upload': 'POST - Upload and parse RFP PDF',
            '/api/documents/upload': 'POST - Upload responsive documents',
            '/api/analyze/<session_id>': 'POST - Run AI analysis',
            '/api/generate/<session_id>': 'POST - Generate response document',
            '/health': 'GET - Health check'
        }
    })


@app.route('/health')
def health():
    """Health check endpoint for deployment monitoring."""
    return jsonify({'status': 'healthy'}), 200


@app.route('/generate')
def generate_document():
    """
    Legacy endpoint: Generate a Word document from template with provided parameters.

    Query Parameters:
    - template: name of the template file (default: 'default_template.docx')
    - All other parameters will be passed as context to the template
    """
    try:
        template_name = request.args.get('template', 'default_template.docx')
        template_path = os.path.join(TEMPLATE_DIR, template_name)

        if not os.path.exists(template_path):
            return jsonify({
                'error': 'Template not found',
                'template': template_name,
                'available_templates': os.listdir(TEMPLATE_DIR) if os.path.exists(TEMPLATE_DIR) else []
            }), 404

        doc = DocxTemplate(template_path)
        context = {key: value for key, value in request.args.items() if key != 'template'}

        if 'generated_date' not in context:
            context['generated_date'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        doc.render(context)

        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.docx')
        doc.save(temp_file.name)
        temp_file.close()

        output_filename = f"generated_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"

        response = send_file(
            temp_file.name,
            as_attachment=True,
            download_name=output_filename,
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )

        @response.call_on_close
        def cleanup():
            try:
                os.unlink(temp_file.name)
            except (OSError, FileNotFoundError) as e:
                app.logger.warning(f"Failed to cleanup temporary file {temp_file.name}: {e}")

        return response

    except Exception as e:
        return jsonify({
            'error': 'Failed to generate document',
            'message': str(e)
        }), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
