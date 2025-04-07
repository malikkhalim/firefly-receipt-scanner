import os
from fastapi import (
    FastAPI,
    File,
    UploadFile,
    HTTPException,
    Form,
)
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.trustedhost import TrustedHostMiddleware
import tempfile

from .receipt_processing import extract_receipt_data, create_transaction_from_data
from .firefly import get_firefly_asset_accounts
from .image_utils import process_image

app = FastAPI(title="Receipt to Firefly III")

# Add trusted host middleware to handle forwarded headers
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])

# Create a static directory if it doesn't exist
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve a simple HTML form for uploading receipts."""
    # Fetch asset accounts from Firefly III
    asset_accounts = get_firefly_asset_accounts()

    # If no accounts were fetched, use a default
    if not asset_accounts:
        asset_accounts = ["Cash wallet"]
        print("Using default asset account due to Firefly III connection issues")

    # Create the options HTML for the dropdown
    account_options = "\n".join(
        [f'<option value="{account}">{account}</option>' for account in asset_accounts]
    )

    return f"""
    <!DOCTYPE html>
    <html>
        <head>
            <title>Receipt Scanner</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                * {{
                    box-sizing: border-box;
                    margin: 0;
                    padding: 0;
                }}

                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 100%;
                    margin: 0;
                    padding: 20px;
                    background-color: #f5f5f5;
                }}

                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    background: white;
                    padding: 20px;
                    border-radius: 12px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }}

                h1 {{
                    color: #2c3e50;
                    font-size: 24px;
                    margin-bottom: 20px;
                    text-align: center;
                }}

                .form-group {{
                    margin-bottom: 20px;
                }}

                label {{
                    display: block;
                    margin-bottom: 8px;
                    font-weight: 500;
                    color: #2c3e50;
                }}

                select, input[type="file"] {{
                    width: 100%;
                    padding: 12px;
                    border: 2px solid #ddd;
                    border-radius: 8px;
                    font-size: 16px;
                    background-color: white;
                }}

                select:focus, input[type="file"]:focus {{
                    outline: none;
                    border-color: #3498db;
                }}

                .btn {{
                    display: inline-block;
                    width: 100%;
                    padding: 12px;
                    background: #3498db;
                    color: white;
                    border: none;
                    border-radius: 8px;
                    font-size: 16px;
                    font-weight: 500;
                    cursor: pointer;
                    transition: background-color 0.3s;
                }}

                .btn:hover {{
                    background: #2980b9;
                }}

                .camera-container {{
                    margin-bottom: 20px;
                }}

                #camera-preview {{
                    width: 100%;
                    max-width: 100%;
                    border-radius: 8px;
                    margin-bottom: 10px;
                    display: none;
                }}

                .camera-buttons {{
                    display: flex;
                    gap: 10px;
                    margin-bottom: 10px;
                }}

                .camera-btn {{
                    flex: 1;
                    padding: 12px;
                    border: none;
                    border-radius: 8px;
                    font-size: 16px;
                    font-weight: 500;
                    cursor: pointer;
                    transition: background-color 0.3s;
                }}

                .start-camera {{
                    background: #2ecc71;
                    color: white;
                }}

                .start-camera:hover {{
                    background: #27ae60;
                }}

                .capture {{
                    background: #3498db;
                    color: white;
                    display: none;
                }}

                .capture:hover {{
                    background: #2980b9;
                }}

                .retake {{
                    background: #e74c3c;
                    color: white;
                    display: none;
                }}

                .retake:hover {{
                    background: #c0392b;
                }}

                .or-divider {{
                    text-align: center;
                    margin: 20px 0;
                    position: relative;
                }}

                .or-divider::before,
                .or-divider::after {{
                    content: '';
                    position: absolute;
                    top: 50%;
                    width: 45%;
                    height: 1px;
                    background-color: #ddd;
                }}

                .or-divider::before {{
                    left: 0;
                }}

                .or-divider::after {{
                    right: 0;
                }}

                @media (max-width: 480px) {{
                    body {{
                        padding: 10px;
                    }}

                    .container {{
                        padding: 15px;
                    }}

                    h1 {{
                        font-size: 20px;
                    }}

                    .btn, .camera-btn {{
                        padding: 10px;
                        font-size: 14px;
                    }}
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Receipt Scanner</h1>
                <form id="receipt-form" action="/extract" method="post" enctype="multipart/form-data">
                    <div class="form-group">
                        <label>Source Account:</label>
                        <select name="source_account" required>
                            {account_options}
                        </select>
                    </div>

                    <div class="camera-container">
                        <video id="camera-preview" autoplay playsinline></video>
                        <canvas id="canvas" style="display: none;"></canvas>
                        <div class="camera-buttons">
                            <button type="button" class="camera-btn start-camera" id="startCamera">Take Photo</button>
                            <button type="button" class="camera-btn capture" id="capture">Capture</button>
                            <button type="button" class="camera-btn retake" id="retake">Retake</button>
                        </div>
                    </div>

                    <div class="or-divider">OR</div>

                    <div class="form-group">
                        <label>Upload Receipt:</label>
                        <input type="file" name="file" id="file" accept="image/*" capture="environment">
                    </div>

                    <button type="submit" class="btn">Extract Receipt Data</button>
                </form>
            </div>

            <script>
                let stream;
                const video = document.getElementById('camera-preview');
                const canvas = document.getElementById('canvas');
                const startButton = document.getElementById('startCamera');
                const captureButton = document.getElementById('capture');
                const retakeButton = document.getElementById('retake');
                const fileInput = document.getElementById('file');
                const form = document.getElementById('receipt-form');

                startButton.addEventListener('click', async () => {{
                    try {{
                        stream = await navigator.mediaDevices.getUserMedia({{
                            video: {{ facingMode: 'environment' }}
                        }});
                        video.srcObject = stream;
                        video.style.display = 'block';
                        startButton.style.display = 'none';
                        captureButton.style.display = 'block';
                        fileInput.disabled = true;
                    }} catch (err) {{
                        console.error('Error accessing camera:', err);
                        alert('Could not access the camera. Please check permissions or use file upload instead.');
                    }}
                }});

                captureButton.addEventListener('click', () => {{
                    canvas.width = video.videoWidth;
                    canvas.height = video.videoHeight;
                    canvas.getContext('2d').drawImage(video, 0, 0);
                    
                    // Convert the canvas to a blob
                    canvas.toBlob((blob) => {{
                        const file = new File([blob], 'receipt.jpg', {{ type: 'image/jpeg' }});
                        const dataTransfer = new DataTransfer();
                        dataTransfer.items.add(file);
                        fileInput.files = dataTransfer.files;
                        
                        // Stop the camera stream
                        stream.getTracks().forEach(track => track.stop());
                        video.style.display = 'none';
                        captureButton.style.display = 'none';
                        retakeButton.style.display = 'block';
                        fileInput.disabled = false;
                    }}, 'image/jpeg', 0.8);
                }});

                retakeButton.addEventListener('click', () => {{
                    video.style.display = 'none';
                    startButton.style.display = 'block';
                    retakeButton.style.display = 'none';
                    fileInput.value = '';
                }});

                // Clean up on page unload
                window.addEventListener('unload', () => {{
                    if (stream) {{
                        stream.getTracks().forEach(track => track.stop());
                    }}
                }});
            </script>
        </body>
    </html>
    """


@app.post("/extract")
async def extract_receipt(
    file: UploadFile = File(...), source_account: str = Form(...)
):
    """Extract data from the receipt and show a review page."""
    try:
        # Process the image (resize and compress)
        processed_image_bytes, original_filename = await process_image(
            file, max_size=(512, 512), quality=85
        )

        # Create a temporary file with the processed image
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=os.path.splitext(original_filename)[1]
        ) as temp_file:
            temp_file.write(processed_image_bytes)
            temp_file_path = temp_file.name

        # Create a new UploadFile object with the processed image
        processed_file = UploadFile(
            file=open(temp_file_path, "rb"), filename=original_filename
        )

        # Extract data from the processed image
        extracted_data = await extract_receipt_data(processed_file)

        # Clean up the temporary file
        os.unlink(temp_file_path)

        # Create category options for the dropdown
        category_options = "\n".join(
            [
                f'<option value="{category}" {"selected" if category == extracted_data["category"] else ""}>{category}</option>'
                for category in extracted_data["available_categories"]
            ]
        )

        # Create budget options for the dropdown
        budget_options = "\n".join(
            [
                f'<option value="{budget}" {"selected" if budget == extracted_data["budget"] else ""}>{budget}</option>'
                for budget in extracted_data["available_budgets"]
            ]
        )

        return HTMLResponse(f"""
            <!DOCTYPE html>
            <html>
                <head>
                    <title>Review Receipt Data</title>
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <style>
                        * {{
                            box-sizing: border-box;
                            margin: 0;
                            padding: 0;
                        }}

                        body {{
                            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                            line-height: 1.6;
                            color: #333;
                            background-color: #f5f5f5;
                            padding: 20px;
                        }}

                        .container {{
                            max-width: 600px;
                            margin: 0 auto;
                            background: white;
                            padding: 20px;
                            border-radius: 12px;
                            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                        }}

                        h1 {{
                            color: #2c3e50;
                            font-size: 24px;
                            margin-bottom: 20px;
                            text-align: center;
                        }}

                        .form-group {{
                            margin-bottom: 20px;
                        }}

                        label {{
                            display: block;
                            margin-bottom: 8px;
                            font-weight: 500;
                            color: #2c3e50;
                        }}

                        input, select {{
                            width: 100%;
                            padding: 12px;
                            border: 2px solid #ddd;
                            border-radius: 8px;
                            font-size: 16px;
                            background-color: white;
                        }}

                        input:focus, select:focus {{
                            outline: none;
                            border-color: #3498db;
                        }}

                        .btn {{
                            display: inline-block;
                            width: 100%;
                            padding: 12px;
                            background: #3498db;
                            color: white;
                            border: none;
                            border-radius: 8px;
                            font-size: 16px;
                            font-weight: 500;
                            cursor: pointer;
                            transition: background-color 0.3s;
                            margin-bottom: 10px;
                        }}

                        .btn:hover {{
                            background: #2980b9;
                        }}

                        .btn-secondary {{
                            background: #95a5a6;
                        }}

                        .btn-secondary:hover {{
                            background: #7f8c8d;
                        }}

                        .loading {{
                            display: none;
                            text-align: center;
                            margin-top: 20px;
                            padding: 20px;
                            background: #f8f9fa;
                            border-radius: 8px;
                        }}

                        .loading.active {{
                            display: block;
                        }}

                        @media (max-width: 480px) {{
                            body {{
                                padding: 10px;
                            }}

                            .container {{
                                padding: 15px;
                            }}

                            h1 {{
                                font-size: 20px;
                            }}

                            input, select, .btn {{
                                padding: 10px;
                                font-size: 14px;
                            }}
                        }}
                    </style>
                    <script>
                        function showLoading() {{
                            document.getElementById('loading').classList.add('active');
                            document.getElementById('submit-btn').disabled = true;
                        }}
                    </script>
                </head>
                <body>
                    <div class="container">
                        <h1>Review Receipt Data</h1>
                        <p>Please review and edit the extracted data before creating the transaction.</p>
                        
                        <form action="/create-transaction" method="post" onsubmit="showLoading()">
                            <div class="form-group">
                                <label>Date:</label>
                                <input type="date" name="date" value="{extracted_data["date"]}" required>
                            </div>
                            
                            <div class="form-group">
                                <label>Amount:</label>
                                <input type="number" step="0.01" name="amount" value="{extracted_data["amount"]}" required>
                            </div>
                            
                            <div class="form-group">
                                <label>Store Name:</label>
                                <input type="text" name="store_name" value="{extracted_data["store_name"]}" required>
                            </div>
                            
                            <div class="form-group">
                                <label>Category:</label>
                                <select name="category" required>
                                    {category_options}
                                </select>
                            </div>
                            
                            <div class="form-group">
                                <label>Budget:</label>
                                <select name="budget" required>
                                    {budget_options}
                                </select>
                            </div>
                            
                            <input type="hidden" name="source_account" value="{source_account}">
                            
                            <div class="form-group">
                                <button type="submit" id="submit-btn" class="btn">Create Transaction</button>
                                <button type="button" class="btn btn-secondary" onclick="window.location.href='/'">Cancel</button>
                            </div>
                        </form>
                        
                        <div id="loading" class="loading">
                            <p>Creating transaction... This may take a minute. Please don't close this page.</p>
                            <p>If this takes too long, you can try again later.</p>
                        </div>
                    </div>
                </body>
            </html>
        """)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/create-transaction")
async def create_transaction(
    date: str = Form(...),
    amount: float = Form(...),
    store_name: str = Form(...),
    category: str = Form(...),
    budget: str = Form(...),
    source_account: str = Form(...),
):
    """Create a transaction in Firefly III using the reviewed data."""
    try:
        # Create a dictionary with the form data
        receipt_data = {
            "date": date,
            "amount": amount,
            "store_name": store_name,
            "category": category,
            "budget": budget,
        }

        # Create the transaction
        result = await create_transaction_from_data(receipt_data, source_account)

        # Check if the result contains an error message
        if result and "Failed to create transaction" in result:
            return HTMLResponse(f"""
                <!DOCTYPE html>
                <html>
                    <head>
                        <title>Transaction Creation Failed</title>
                        <meta name="viewport" content="width=device-width, initial-scale=1.0">
                        <style>
                            * {{
                                box-sizing: border-box;
                                margin: 0;
                                padding: 0;
                            }}

                            body {{
                                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                                line-height: 1.6;
                                color: #333;
                                background-color: #f5f5f5;
                                padding: 20px;
                            }}

                            .container {{
                                max-width: 600px;
                                margin: 0 auto;
                                background: white;
                                padding: 20px;
                                border-radius: 12px;
                                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                            }}

                            h1 {{
                                color: #2c3e50;
                                font-size: 24px;
                                margin-bottom: 20px;
                                text-align: center;
                            }}

                            .error {{
                                background: #ffebee;
                                color: #c62828;
                                padding: 15px;
                                border-radius: 8px;
                                margin-bottom: 20px;
                                font-size: 16px;
                            }}

                            .error-details {{
                                background: #f5f5f5;
                                padding: 15px;
                                border-radius: 8px;
                                margin-bottom: 20px;
                                font-family: monospace;
                                font-size: 14px;
                                white-space: pre-wrap;
                                word-break: break-word;
                            }}

                            .btn {{
                                display: inline-block;
                                width: 100%;
                                padding: 12px;
                                background: #3498db;
                                color: white;
                                border: none;
                                border-radius: 8px;
                                font-size: 16px;
                                font-weight: 500;
                                cursor: pointer;
                                transition: background-color 0.3s;
                                text-align: center;
                                text-decoration: none;
                            }}

                            .btn:hover {{
                                background: #2980b9;
                            }}

                            .retry-btn {{
                                background: #2ecc71;
                                margin-bottom: 10px;
                            }}

                            .retry-btn:hover {{
                                background: #27ae60;
                            }}

                            @media (max-width: 480px) {{
                                body {{
                                    padding: 10px;
                                }}

                                .container {{
                                    padding: 15px;
                                }}

                                h1 {{
                                    font-size: 20px;
                                }}

                                .btn {{
                                    padding: 10px;
                                    font-size: 14px;
                                }}

                                .error {{
                                    font-size: 14px;
                                    padding: 12px;
                                }}

                                .error-details {{
                                    font-size: 12px;
                                    padding: 12px;
                                }}
                            }}
                        </style>
                    </head>
                    <body>
                        <div class="container">
                            <h1>Transaction Creation Failed</h1>
                            <div class="error">
                                <p>The transaction could not be created in Firefly III. This might be due to a temporary issue with the Firefly III server.</p>
                                <p>You can try again later or check the Firefly III server status.</p>
                            </div>
                            <h2>Error Details:</h2>
                            <div class="error-details">{result}</div>
                            <a href="javascript:history.back()" class="btn retry-btn">Try Again</a>
                            <a href="/" class="btn">Back to Upload</a>
                        </div>
                    </body>
                </html>
            """)

        # If we get here, the transaction was created successfully
        return HTMLResponse(f"""
            <!DOCTYPE html>
            <html>
                <head>
                    <title>Transaction Created</title>
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <style>
                        * {{
                            box-sizing: border-box;
                            margin: 0;
                            padding: 0;
                        }}

                        body {{
                            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                            line-height: 1.6;
                            color: #333;
                            background-color: #f5f5f5;
                            padding: 20px;
                        }}

                        .container {{
                            max-width: 600px;
                            margin: 0 auto;
                            background: white;
                            padding: 20px;
                            border-radius: 12px;
                            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                        }}

                        h1 {{
                            color: #2c3e50;
                            font-size: 24px;
                            margin-bottom: 20px;
                            text-align: center;
                        }}

                        .success {{
                            background: #e8f5e9;
                            color: #2e7d32;
                            padding: 15px;
                            border-radius: 8px;
                            margin-bottom: 20px;
                            font-size: 16px;
                        }}

                        .transaction-details {{
                            background: #f5f5f5;
                            padding: 15px;
                            border-radius: 8px;
                            margin-bottom: 20px;
                            font-family: monospace;
                            font-size: 14px;
                            white-space: pre-wrap;
                            word-break: break-word;
                        }}

                        .btn {{
                            display: inline-block;
                            width: 100%;
                            padding: 12px;
                            background: #3498db;
                            color: white;
                            border: none;
                            border-radius: 8px;
                            font-size: 16px;
                            font-weight: 500;
                            cursor: pointer;
                            transition: background-color 0.3s;
                            text-align: center;
                            text-decoration: none;
                        }}

                        .btn:hover {{
                            background: #2980b9;
                        }}

                        @media (max-width: 480px) {{
                            body {{
                                padding: 10px;
                            }}

                            .container {{
                                padding: 15px;
                            }}

                            h1 {{
                                font-size: 20px;
                            }}

                            .btn {{
                                padding: 10px;
                                font-size: 14px;
                            }}

                            .success {{
                                font-size: 14px;
                                padding: 12px;
                            }}

                            .transaction-details {{
                                font-size: 12px;
                                padding: 12px;
                            }}
                        }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <h1>Transaction Created Successfully</h1>
                        <div class="success">
                            <p>Your transaction has been created in Firefly III.</p>
                        </div>
                        <h2>Transaction Details:</h2>
                        <div class="transaction-details">{result}</div>
                        <a href="/" class="btn">Back to Upload</a>
                    </div>
                </body>
            </html>
        """)
    except Exception as e:
        return HTMLResponse(f"""
            <!DOCTYPE html>
            <html>
                <head>
                    <title>Error</title>
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <style>
                        * {{
                            box-sizing: border-box;
                            margin: 0;
                            padding: 0;
                        }}

                        body {{
                            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                            line-height: 1.6;
                            color: #333;
                            background-color: #f5f5f5;
                            padding: 20px;
                        }}

                        .container {{
                            max-width: 600px;
                            margin: 0 auto;
                            background: white;
                            padding: 20px;
                            border-radius: 12px;
                            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                        }}

                        h1 {{
                            color: #2c3e50;
                            font-size: 24px;
                            margin-bottom: 20px;
                            text-align: center;
                        }}

                        .error {{
                            background: #ffebee;
                            color: #c62828;
                            padding: 15px;
                            border-radius: 8px;
                            margin-bottom: 20px;
                            font-size: 16px;
                        }}

                        .error-details {{
                            background: #f5f5f5;
                            padding: 15px;
                            border-radius: 8px;
                            margin-bottom: 20px;
                            font-family: monospace;
                            font-size: 14px;
                            white-space: pre-wrap;
                            word-break: break-word;
                        }}

                        .btn {{
                            display: inline-block;
                            width: 100%;
                            padding: 12px;
                            background: #3498db;
                            color: white;
                            border: none;
                            border-radius: 8px;
                            font-size: 16px;
                            font-weight: 500;
                            cursor: pointer;
                            transition: background-color 0.3s;
                            text-align: center;
                            text-decoration: none;
                        }}

                        .btn:hover {{
                            background: #2980b9;
                        }}

                        @media (max-width: 480px) {{
                            body {{
                                padding: 10px;
                            }}

                            .container {{
                                padding: 15px;
                            }}

                            h1 {{
                                font-size: 20px;
                            }}

                            .btn {{
                                padding: 10px;
                                font-size: 14px;
                            }}

                            .error {{
                                font-size: 14px;
                                padding: 12px;
                            }}

                            .error-details {{
                                font-size: 12px;
                                padding: 12px;
                            }}
                        }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <h1>Error</h1>
                        <div class="error">
                            <p>An error occurred while processing your request:</p>
                        </div>
                        <div class="error-details">{str(e)}</div>
                        <a href="/" class="btn">Back to Upload</a>
                    </div>
                </body>
            </html>
        """)
