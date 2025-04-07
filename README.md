# Receipt Scanner for Firefly III

A web application that allows you to scan receipts and automatically create transactions in Firefly III.

## Features

- Upload and scan receipts using Google's Gemini AI
- Extract key information: date, amount, store name, category, and budget
- Review and edit extracted data before creating transactions
- Create transactions in Firefly III with a single click
- Resize and compress images for faster processing

## Prerequisites

- Docker and Docker Compose
- A Firefly III instance
- A Google AI API key

## Configuration

1. Clone this repository:
   ```
   git clone https://github.com/yourusername/receipt-scanner.git
   cd receipt-scanner
   ```

2. Create a `.env` file based on the `.env.example`:
   ```
   cp .env.example .env
   ```

3. Edit the `.env` file with your configuration:
   ```
   # Firefly III API Configuration
   FIREFLY_III_URL=https://your-firefly-iii-instance.com
   FIREFLY_III_TOKEN=your-personal-access-token

   # Google AI API Configuration
   GOOGLE_AI_API_KEY=your-google-ai-api-key
   ```

## Deployment

### Using Docker Compose (Recommended)

1. Build and start the application:
   ```
   docker-compose up -d
   ```

2. Access the application at http://localhost:8000

### Manual Deployment

1. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Run the application:
   ```
   uvicorn app.app:app --host 0.0.0.0 --port 8000
   ```

## Usage

1. Open the application in your web browser
2. Select a source account from the dropdown menu
3. Upload a receipt image
4. Review and edit the extracted data
5. Click "Create Transaction" to create the transaction in Firefly III

## Development

### Project Structure

- `app/` - Application code
  - `app.py` - FastAPI application and routes
  - `firefly.py` - Firefly III API integration
  - `receipt_processing.py` - Receipt data extraction and processing
  - `image_utils.py` - Image processing utilities
  - `models.py` - Data models

### Running Tests

```
pytest
```

## License

MIT
