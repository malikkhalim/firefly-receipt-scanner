// app/receipt_processing.py

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

# Load environment variables
load_dotenv()

# Get API key from environment variable
GOOGLE_AI_API_KEY = os.getenv("GOOGLE_AI_API_KEY")
if not GOOGLE_AI_API_KEY:
    raise ValueError("GOOGLE_AI_API_KEY environment variable is not set")

client = genai.Client(api_key=GOOGLE_AI_API_KEY)


async def extract_receipt_data(file: UploadFile, token: str):
    """Extract data from the receipt image without creating a transaction."""
    try:
        print(f"Processing image: {file.filename}")

        # Process the image (resize and compress)
        image = await process_image(file, max_size=(768, 768))
        print("Image processed")

        # Fetch dynamic data from Firefly III
        print("Fetching categories and budgets...")
        categories = get_firefly_categories(token)
        budgets = get_firefly_budgets(token)
        print(
            f"Found {len(categories) if categories else 0} categories and {len(budgets) if budgets else 0} budgets"
        )

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
            "5) description of the transaction"
            "5) date (in YYYY-MM-DD format). Today's date is "
            + datetime.now().strftime("%Y-%m-%d")
            + ". "
            "Most receipts are from the past few days, so use today's date as a reference point when interpreting dates. "
            "If the date is not on the receipt, use today's date as the default."
        )

        try:
            print("Sending request to Gemini for analysis...")
            # Generate receipt details using genai
            gemini_response = client.models.generate_content(
                model="gemini-1.5-flash",
                contents=[
                    receipt_prompt,
                    image,
                ],
                generation_config={
                    "response_mime_type": "application/json",
                },
                request_options={"timeout": 60.0},
                # The schema definition is now part of the tool config
                tools=[genai.protos.Tool(
                    function_declarations=[
                        genai.protos.FunctionDeclaration(
                            name="extract_receipt_info",
                            description="Extracts information from a receipt.",
                            parameters=genai.protos.Schema(
                                type=genai.protos.Type.OBJECT,
                                properties={
                                    "date": genai.protos.Schema(type=genai.protos.Type.STRING),
                                    "amount": genai.protos.Schema(type=genai.protos.Type.NUMBER),
                                    "store_name": genai.protos.Schema(type=genai.protos.Type.STRING),
                                    "description": genai.protos.Schema(type=genai.protos.Type.STRING),
                                    "category": genai.protos.Schema(type=genai.protos.Type.STRING),
                                    "budget": genai.protos.Schema(type=genai.protos.Type.STRING),
                                }
                            )
                        )
                    ]
                )],
                tool_config=genai.protos.ToolConfig(
                    function_calling_config=genai.protos.FunctionCallingConfig(
                        mode=genai.protos.FunctionCallingConfig.Mode.ANY,
                    )
                ),
            )
            print("Received response from Gemini")
            
            # --- DEBUGGING PRINT STATEMENT ---
            print("================= DEBUG GEMINI RESPONSE =================")
            print(gemini_response)
            print("=========================================================")

        except Exception as e:
            print(f"Error during Gemini analysis: {str(e)}")
            print(f"Error type: {type(e)}")
            if "timeout" in str(e).lower():
                raise TimeoutError(
                    "The image processing timed out. Please try again with a smaller or clearer image."
                )
            raise e

        # Extract function call data
        function_call = gemini_response.candidates[0].content.parts[0].function_call
        args = {key: value for key, value in function_call.args.items()}
        
        # Validate and format the date
        try:
            print(f"Validating date: {args.get('date')}")
            # Try to parse the date to ensure it's valid
            date_obj = datetime.strptime(args.get('date'), "%Y-%m-%d")
            # Format it back to the expected format
            args['date'] = date_obj.strftime("%Y-%m-%d")
            print("Date validation successful")
        except (ValueError, TypeError):
            # If the date is invalid or missing, use the current date
            print(
                f"Invalid or missing date: {args.get('date')}. Using current date instead."
            )
            args['date'] = datetime.now().strftime("%Y-%m-%d")

        # Return the extracted data as a dictionary
        extracted_data = {
            "date": args.get('date'),
            "amount": args.get('amount'),
            "store_name": args.get('store_name'),
            "description": args.get('description'),
            "category": args.get('category'),
            "budget": args.get('budget'),
            "available_categories": categories,
            "available_budgets": budgets,
        }

        # --- DEBUGGING PRINT STATEMENT ---
        print("================= FINAL EXTRACTED DATA ==================")
        print(extracted_data)
        print("=========================================================")
        
        print("Successfully extracted all data")
        return extracted_data

    except Exception as e:
        print(f"Unexpected error in extract_receipt_data: {str(e)}")
        print(f"Error type: {type(e)}")
        raise


async def create_transaction_from_data(receipt_data, source_account, token: str):
    """Create a transaction in Firefly III using the provided data."""
    # Create a ReceiptModel object from the data
    receipt = ReceiptModel(
        date=receipt_data["date"],
        amount=receipt_data["amount"],
        store_name=receipt_data["store_name"],
        description=receipt_data["description"],
        category=receipt_data["category"],
        budget=receipt_data["budget"],
    )

    # Implement retry logic with exponential backoff
    max_retries = 3
    retry_delay = 3
    last_error = None

    for attempt in range(max_retries):
        try:
            # Create a transaction based on the receipt data
            transaction_result = create_firefly_transaction(receipt, source_account, token)

            if transaction_result:
                print("Transaction created successfully:")
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