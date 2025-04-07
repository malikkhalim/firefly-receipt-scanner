from fastapi import UploadFile
from google import genai
from .models import ReceiptModel
from .firefly import (
    get_firefly_categories,
    get_firefly_budgets,
    create_firefly_transaction,
)
from datetime import datetime
import time
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get API key from environment variable
GOOGLE_AI_API_KEY = os.getenv("GOOGLE_AI_API_KEY")
if not GOOGLE_AI_API_KEY:
    raise ValueError("GOOGLE_AI_API_KEY environment variable is not set")

client = genai.Client(api_key=GOOGLE_AI_API_KEY)


async def extract_receipt_data(file: UploadFile):
    """Extract data from the receipt image without creating a transaction."""
    # Create a temporary file with a unique name
    temp_file = None
    try:
        # Create a temporary file with the same extension as the original
        file_ext = os.path.splitext(file.filename)[1]
        temp_file = f"/tmp/receipt_{int(time.time())}{file_ext}"

        # Write the file content to the temporary file
        with open(temp_file, "wb") as f:
            f.write(await file.read())

        # Upload file via genai client
        receipt_img = client.files.upload(file=temp_file)

        # Fetch dynamic data from Firefly III
        categories = get_firefly_categories()
        budgets = get_firefly_budgets()

        # If we couldn't fetch categories or budgets, use default values
        if not categories:
            categories = [
                "Groceries",
                "Dining",
                "Shopping",
                "Transportation",
                "Entertainment",
                "Other",
            ]
            print("Using default categories due to Firefly III connection issues")

        if not budgets:
            budgets = ["Monthly", "Weekly", "Other"]
            print("Using default budgets due to Firefly III connection issues")

        # Construct the prompt.
        receipt_prompt = (
            "Please analyze the attached receipt image and extract the following details: "
            "1) receipt amount, 2) receipt category (choose from: "
            + ", ".join(categories)
            + "), "
            "3) receipt budget (choose from: " + ", ".join(budgets) + "), "
            "4) destination account (store name) "
            "5) date (in YYYY-MM-DD format)."
        )

        # Generate receipt details using genai.
        gemini_response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[receipt_prompt, receipt_img],
            config={
                "response_mime_type": "application/json",
                "response_schema": ReceiptModel,
            },
        )

        # Validate and format the date
        try:
            # Try to parse the date to ensure it's valid
            date_obj = datetime.strptime(gemini_response.parsed.date, "%Y-%m-%d")
            # Format it back to the expected format
            gemini_response.parsed.date = date_obj.strftime("%Y-%m-%d")
        except ValueError:
            # If the date is invalid, use the current date
            print(
                f"Invalid date format: {gemini_response.parsed.date}. Using current date instead."
            )
            gemini_response.parsed.date = datetime.now().strftime("%Y-%m-%d")

        # Return the extracted data as a dictionary
        extracted_data = {
            "date": gemini_response.parsed.date,
            "amount": gemini_response.parsed.amount,
            "store_name": gemini_response.parsed.store_name,
            "category": gemini_response.parsed.category,
            "budget": gemini_response.parsed.budget,
            "available_categories": categories,
            "available_budgets": budgets,
        }

        return extracted_data
    finally:
        # Clean up the temporary file
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except Exception as e:
                print(f"Error removing temporary file {temp_file}: {e}")


async def create_transaction_from_data(receipt_data, source_account):
    """Create a transaction in Firefly III using the provided data."""
    # Create a ReceiptModel object from the data
    receipt = ReceiptModel(
        date=receipt_data["date"],
        amount=receipt_data["amount"],
        store_name=receipt_data["store_name"],
        category=receipt_data["category"],
        budget=receipt_data["budget"],
    )

    # Implement retry logic with exponential backoff
    max_retries = 3  # Reduced from 5 to 3 to prevent too many duplicates
    retry_delay = 3  # Keep at 3 seconds
    last_error = None

    for attempt in range(max_retries):
        try:
            # Create a transaction based on the receipt data
            transaction_result = create_firefly_transaction(receipt, source_account)

            if transaction_result:
                print("Transaction created successfully:")
                print(f"- Date: {receipt.date}")
                print(f"- Amount: {receipt.amount}")
                print(f"- Store: {receipt.store_name}")
                print(f"- Category: {receipt.category}")
                print(f"- Budget: {receipt.budget}")
                print(f"- Source Account: {source_account}")
                print(f"- Transaction ID: {transaction_result['data']['id']}")
                return f"Transaction created successfully with ID: {transaction_result['data']['id']}"
            else:
                last_error = (
                    "Failed to create transaction. No response from Firefly III."
                )
                print(last_error)

        except Exception as e:
            last_error = str(e)
            print(
                f"Error creating transaction (attempt {attempt + 1}/{max_retries}): {e}"
            )

            # If this is not the last attempt, wait and retry
            if attempt < max_retries - 1:
                wait_time = retry_delay * (2**attempt)  # Exponential backoff
                print(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)

    # If we've exhausted all retries, return an error message
    error_msg = f"Failed to create transaction after {max_retries} attempts. Last error: {last_error}"
    print(error_msg)
    return error_msg
