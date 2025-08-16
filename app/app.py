import os
import sys

from dotenv import load_dotenv
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from .firefly import get_firefly_asset_accounts, get_firefly_categories
from .receipt_processing import create_transaction_from_data, extract_receipt_data

# Load environment variables
load_dotenv()


def test_firefly_connection(url: str, token: str):
    """Test the connection to Firefly III by attempting to fetch categories."""
    try:
        categories = get_firefly_categories(url, token)
        if categories is None:
            print("Error: Could not connect to Firefly III. Categories returned None.")
            return False
        print("Successfully connected to Firefly III")
        return True
    except Exception as e:
        print(f"Error connecting to Firefly III: {str(e)}")
        return False


app = FastAPI(title="Receipt to Firefly III")

# Get secret key for session middleware
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable is not set")

# Add middleware
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

# Create a static directory if it doesn't exist
os.makedirs("app/static", exist_ok=True)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Set up templates
templates = Jinja2Templates(directory="app/templates")


# Dependency to get credentials or redirect to login
async def get_firefly_credentials(request: Request):
    firefly_url = request.session.get("firefly_url")
    firefly_token = request.session.get("firefly_token")

    if not firefly_url or not firefly_token:
        # Ganti 'return RedirectResponse' dengan 'raise HTTPException'
        raise HTTPException(
            status_code=307, 
            headers={"Location": "/login"}
        )

    return {"url": firefly_url, "token": firefly_token}


@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    """Serve the login page."""
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    firefly_url: str = Form(...),
    firefly_token: str = Form(...),
):
    """Handle login submission, test credentials, and set session."""
    # Clean up URL
    url = firefly_url.strip().rstrip("/")
    if test_firefly_connection(url, firefly_token):
        request.session["firefly_url"] = url
        request.session["firefly_token"] = firefly_token
        return RedirectResponse(url="/", status_code=303)
    else:
        error_message = "Failed to connect to Firefly III. Please check your URL and Token."
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error_message": error_message, "firefly_url": url},
        )


@app.get("/logout")
async def logout(request: Request):
    """Clear the session and redirect to the login page."""
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


@app.get("/", response_class=HTMLResponse)
async def root(request: Request, creds: dict = Depends(get_firefly_credentials)):
    """Serve a simple HTML form for uploading receipts."""
    asset_accounts = get_firefly_asset_accounts(creds["url"], creds["token"])
    if not asset_accounts:
        asset_accounts = ["Cash wallet"]
        print("Using default asset account due to Firefly III connection issues")
    return templates.TemplateResponse(
        "upload.html", {"request": request, "asset_accounts": asset_accounts}
    )


@app.post("/extract")
async def extract_receipt(
    request: Request,
    file: UploadFile = File(...),
    source_account: str = Form(...),
    creds: dict = Depends(get_firefly_credentials),
):
    try:
        extracted_data = await extract_receipt_data(file, creds["url"], creds["token"])
        extracted_data["source_account"] = source_account
        return templates.TemplateResponse(
            "review.html", {"request": request, "extracted_data": extracted_data}
        )
    except TimeoutError:
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "error_message": "The operation timed out. The image processing is taking too long. Please try again with a smaller or clearer image.",
            },
        )
    except Exception as e:
        return templates.TemplateResponse(
            "error.html", {"request": request, "error_message": str(e)}
        )


@app.post("/create-transaction")
async def create_transaction(
    request: Request,
    date: str = Form(...),
    amount: float = Form(...),
    store_name: str = Form(...),
    description: str = Form(...),
    category: str = Form(...),
    budget: str = Form(...),
    source_account: str = Form(...),
    creds: dict = Depends(get_firefly_credentials),
):
    try:
        form_data = {
            "date": date,
            "amount": amount,
            "store_name": store_name,
            "description": description,
            "category": category,
            "budget": budget,
            "source_account": source_account,
        }
        result = await create_transaction_from_data(
            form_data, source_account, creds["url"], creds["token"]
        )

        if result and "Failed to create transaction" in result:
            return templates.TemplateResponse(
                "error.html", {"request": request, "error_message": result}
            )

        asset_accounts = get_firefly_asset_accounts(creds["url"], creds["token"])
        return templates.TemplateResponse(
            "upload.html",
            {
                "request": request,
                "asset_accounts": asset_accounts,
                "success_message": "Transaction created successfully!",
            },
        )
    except Exception as e:
        return templates.TemplateResponse(
            "error.html", {"request": request, "error_message": str(e)}
        )