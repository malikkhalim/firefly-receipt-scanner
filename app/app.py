import os
import sys

from fastapi import (
    FastAPI,
    File,
    Form,
    Query, 
    Request,
    UploadFile,
)
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import HTMLResponse, JSONResponse 
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from .firefly import get_firefly_asset_accounts
from .receipt_processing import create_transaction_from_data, extract_receipt_data

app = FastAPI(title="Receipt to Firefly III")


app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])


os.makedirs("app/static", exist_ok=True)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


templates = Jinja2Templates(directory="app/templates")


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Serve a simple HTML form for uploading receipts."""
    
    return templates.TemplateResponse(
        "upload.html", {"request": request, "asset_accounts": []}
    )


@app.get("/api/accounts", response_class=JSONResponse)
async def get_accounts(token: str = Query(...)):
    """API endpoint to fetch asset accounts using a provided token."""
    try:
        asset_accounts = get_firefly_asset_accounts(token)
        if asset_accounts is None:
            return JSONResponse(
                status_code=404,
                content={
                    "error": "Could not fetch accounts. Check your token or Firefly III connection."
                },
            )
        return {"accounts": asset_accounts}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/extract")
async def extract_receipt(
    request: Request,
    file: UploadFile = File(...),
    source_account: str = Form(...),
    firefly_token: str = Form(...),  
):
    try:
        
        extracted_data = await extract_receipt_data(file, firefly_token)

        
        extracted_data["source_account"] = source_account
        extracted_data["firefly_token"] = firefly_token

        return templates.TemplateResponse(
            "review.html", {"request": request, "extracted_data": extracted_data}
        )
    except TimeoutError:
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "error_message": "The operation timed out. Please try again with a smaller or clearer image.",
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
    firefly_token: str = Form(...),  
):
    try:
        
        result = await create_transaction_from_data(
            {
                "date": date,
                "amount": amount,
                "store_name": store_name,
                "description": description,
                "category": category,
                "budget": budget,
                "source_account": source_account,
            },
            source_account,
            firefly_token,  
        )

        if result and "Failed to create transaction" in result:
            return templates.TemplateResponse(
                "error.html", {"request": request, "error_message": result}
            )

        return templates.TemplateResponse(
            "upload.html",
            {
                "request": request,
                "asset_accounts": [],  
                "firefly_token": firefly_token,  
                "success_message": "Transaction created successfully!",
            },
        )
    except Exception as e:
        return templates.TemplateResponse(
            "error.html", {"request": request, "error_message": str(e)}
        )