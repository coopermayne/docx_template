# docx_template

A Python backend API for generating Word (DOCX) documents from templates using docxtpl.

## Features

- 🚀 Simple REST API built with Flask
- 📄 Generate Word documents from templates with custom data
- 🔧 Template-based document generation using Jinja2 syntax
- ☁️ Ready for deployment on Render
- 💾 Server-stored templates (custom template upload can be added later)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/coopermayne/docx_template.git
cd docx_template
```

2. Create a virtual environment (recommended):
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create a sample template (if not already created):
```bash
python create_sample_template.py
```

## Running Locally

Start the Flask application:
```bash
python app.py
```

The API will be available at `http://localhost:5000`

## API Endpoints

### GET `/`
Returns API information and available endpoints.

**Example:**
```bash
curl http://localhost:5000/
```

### GET `/health`
Health check endpoint for monitoring.

**Response:**
```json
{
  "status": "healthy"
}
```

### GET `/generate`
Generate a Word document from a template with provided query parameters.

**Query Parameters:**
- `template` (optional): Name of the template file (default: `default_template.docx`)
- All other parameters will be passed to the template as context variables

**Example:**
```bash
curl "http://localhost:5000/generate?name=John%20Doe&company=Acme%20Corp&date=2024-01-15&description=Sample%20document" --output generated.docx
```

**Response:**
- Success: Returns a downloadable `.docx` file
- Error: Returns JSON with error details

## Template Format

Templates are Word documents (`.docx`) that use Jinja2 syntax for placeholders:

- Simple variables: `{{ variable_name }}`
- The sample template includes fields like: `{{ name }}`, `{{ company }}`, `{{ date }}`, etc.

### Creating Custom Templates

1. Create a Word document with your desired layout
2. Add Jinja2 placeholders where you want dynamic content (e.g., `{{ name }}`)
3. Save the document as `.docx` in the `templates/` directory
4. Use the template name in the API call: `/generate?template=your_template.docx&name=Value`

## Testing

Run the included tests to verify everything is working:

```bash
python -m unittest test_app.py -v
```

Or use the example script to see the API in action:

```bash
python example_usage.py
```

This will generate a sample document with predefined parameters.

## Project Structure

```
docx_template/
├── app.py                      # Main Flask application
├── requirements.txt            # Python dependencies
├── render.yaml                 # Render deployment configuration
├── create_sample_template.py   # Script to create sample template
├── example_usage.py            # Example script showing API usage
├── test_app.py                 # Unit tests for the API
├── templates/                  # Directory for document templates
│   └── default_template.docx   # Default sample template
└── README.md                   # This file
```

## Deployment on Render

This application is configured for deployment on Render using the included `render.yaml` configuration.

### Deploy Steps:

1. Push your code to GitHub
2. Connect your GitHub repository to Render
3. Render will automatically detect the `render.yaml` file
4. The application will be built and deployed automatically

### Environment Variables (Optional):

- `PORT`: The port the application runs on (default: 5000, Render uses 10000)

## Example Usage

### Generate a document with custom data:

```bash
curl "http://localhost:5000/generate?name=Jane%20Smith&company=Tech%20Solutions&date=2024-12-16&description=Quarterly%20Report&additional_info=This%20is%20additional%20information" --output report.docx
```

This will generate a Word document with all the provided data filled into the template.

### Using a custom template:

1. Create your template: `my_custom_template.docx`
2. Place it in the `templates/` directory
3. Call the API:
```bash
curl "http://localhost:5000/generate?template=my_custom_template.docx&field1=value1&field2=value2" --output output.docx
```

## Future Enhancements

- [ ] Support for uploading custom templates via API
- [ ] POST endpoint for more complex data structures
- [ ] Template management (list, upload, delete templates)
- [ ] Authentication and authorization
- [ ] Rate limiting
- [ ] Template validation

## Technologies Used

- **Flask**: Web framework
- **docxtpl**: Python library for templating Word documents
- **python-docx**: Working with Word documents
- **Gunicorn**: Production WSGI server

## License

MIT

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
