import os
import time
from datetime import datetime

from dotenv import load_dotenv
from fastapi import UploadFile
from google import genai

from .firefly import (
    create_firefly_transaction,
    get_firefly_budgets,
    get_firefly_categories,
)
from .image_utils import process_image
from .models import ReceiptModel

load_dotenv()

GOOGLE_AI_API_KEY = os.getenv("GOOGLE_AI_API_KEY")
if not GOOGLE_AI_API_KEY:
    raise ValueError("GOOGLE_AI_API_KEY environment variable is not set")

client = genai.Client(api_key=GOOGLE_AI_API_KEY)


async def extract_receipt_data(file: UploadFile, token: str):
    """Extract data from the receipt image without creating a transaction."""
    try:
        image = await process_image(file, max_size=(768, 768))

        # Fetch dynamic data from Firefly III
        categories = get_firefly_categories(token)
        budgets = get_firefly_budgets(token)

        # Use default values if connection fails
        if not categories:
            categories = ["Groceries", "Dining", "Shopping", "Other"]
        if not budgets:
            budgets = ["Monthly", "Weekly", "Other"]

        receipt_prompt = (
            "Please analyze the attached receipt image and extract the following details: "
            "1) receipt amount, 2) receipt category (choose from: "
            + ", ".join(categories)
            + "), "
            "3) receipt budget (choose from: " + ", ".join(budgets) + "), "
            "4) destination account (store name) "
            "5) description of the transaction"
            "5) date (in YYYY-MM-DD format). Today's date is "
            + datetime.now().strftime("%Y-%m-%d")
            + ". "
            "Most receipts are from the past few days, so use today's date as a reference point when interpreting dates. "
            "If the date is not on the receipt, use today's date as the default."
        )

        gemini_response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=[
                    receipt_prompt,
                    image,
                ],
                config={
                    "response_mime_type": "application/json",
                    "response_schema": ReceiptModel,
                },
            )

        try:
            date_obj = datetime.strptime(gemini_response.parsed.date, "%Y-%m-%d")
            gemini_response.parsed.date = date_obj.strftime("%Y-%m-%d")
        except ValueError:
            gemini_response.parsed.date = datetime.now().strftime("%Y-%m-%d")

        extracted_data = {
            "date": gemini_response.parsed.date,
            "amount": gemini_response.parsed.amount,
            "store_name": gemini_response.parsed.store_name,
            "description": gemini_response.parsed.description,
            "category": gemini_response.parsed.category,
            "budget": gemini_response.parsed.budget,
            "available_categories": categories,
            "available_budgets": budgets,
        }
        return extracted_data
    except Exception as e:
        print(f"Unexpected error in extract_receipt_data: {str(e)}")
        raise


async def create_transaction_from_data(receipt_data, source_account, token: str):
    """Create a transaction in Firefly III using the provided data."""
    receipt = ReceiptModel(**receipt_data)
    
    max_retries = 3
    retry_delay = 3
    last_error = None

    for attempt in range(max_retries):
        try:
            transaction_result = create_firefly_transaction(receipt, source_account, token)
            if transaction_result:
                return f"Transaction created successfully with ID: {transaction_result['data']['id']}"
            else:
                last_error = "Failed to create transaction. No response from Firefly III."
        except Exception as e:
            last_error = str(e)
            if attempt < max_retries - 1:
                wait_time = retry_delay * (2**attempt)
                time.sleep(wait_time)
    
    return f"Failed to create transaction after {max_retries} attempts. Last error: {last_error}"
