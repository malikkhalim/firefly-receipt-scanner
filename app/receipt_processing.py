import os
import time
import json
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

# Muat environment variables
load_dotenv()

# Ambil kunci API dari environment variable
GOOGLE_AI_API_KEY = os.getenv("GOOGLE_AI_API_KEY")
if not GOOGLE_AI_API_KEY:
    raise ValueError("GOOGLE_AI_API_KEY environment variable is not set")

# Inisialisasi model Generative AI
# Gunakan GenerativeModel untuk library versi terbaru
client = genai.GenerativeModel('gemini-1.5-flash')


async def extract_receipt_data(file: UploadFile, token: str):
    """Mengekstrak data dari gambar struk."""
    try:
        print(f"Processing image: {file.filename}")

        image = await process_image(file, max_size=(768, 768))
        print("Image processed")

        print("Fetching categories and budgets...")
        categories = get_firefly_categories(token)
        budgets = get_firefly_budgets(token)

        # Gunakan nilai default jika gagal mengambil dari Firefly III
        if not categories:
            categories = ["Groceries", "Dining", "Shopping", "Transportation", "Entertainment", "Other"]
            print("Using default categories")

        if not budgets:
            budgets = ["Monthly", "Weekly", "Other"]
            print("Using default budgets")

        # Buat prompt untuk AI
        receipt_prompt = (
            "Please analyze the attached receipt image and extract the following details in JSON format: "
            "1) receipt amount (as a number), 2) receipt category (choose from: "
            + ", ".join(categories)
            + "), "
            "3) receipt budget (choose from: " + ", ".join(budgets) + "), "
            "4) destination account (store name), "
            "5) description of the transaction, "
            "6) date (in YYYY-MM-DD format). Today's date is "
            + datetime.now().strftime("%Y-%m-%d")
            + ". "
            "If a value is not found, provide a reasonable default. For the date, default to today if not present."
        )

        try:
            print("Sending request to Gemini for analysis...")
            
            # Tentukan skema output JSON yang diinginkan
            response_schema = {
                "type": "object",
                "properties": {
                    "date": {"type": "string"},
                    "amount": {"type": "number"},
                    "store_name": {"type": "string"},
                    "description": {"type": "string"},
                    "category": {"type": "string"},
                    "budget": {"type": "string"},
                },
                 "required": ["date", "amount", "store_name", "description", "category", "budget"]
            }

            # Panggil Gemini API dengan konfigurasi yang benar
            gemini_response = client.generate_content(
                contents=[receipt_prompt, image],
                generation_config={
                    "response_mime_type": "application/json",
                    "response_schema": response_schema
                },
                request_options={"timeout": 60.0},
            )
            print("Received response from Gemini")
            
            # Print untuk debugging
            print("================= DEBUG GEMINI RESPONSE =================")
            print(gemini_response.text)
            print("=========================================================")

            # Ubah teks JSON menjadi dictionary Python
            args = json.loads(gemini_response.text)

        except Exception as e:
            print(f"Error during Gemini analysis: {str(e)}")
            if "timeout" in str(e).lower():
                raise TimeoutError("The image processing timed out.")
            raise e

        # Validasi format tanggal
        try:
            date_obj = datetime.strptime(args.get('date'), "%Y-%m-%d")
            args['date'] = date_obj.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            print(f"Invalid or missing date: {args.get('date')}. Using current date instead.")
            args['date'] = datetime.now().strftime("%Y-%m-%d")

        # Siapkan data yang diekstrak
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
        
        print("================= FINAL EXTRACTED DATA ==================")
        print(extracted_data)
        print("=========================================================")
        
        return extracted_data

    except Exception as e:
        print(f"Unexpected error in extract_receipt_data: {str(e)}")
        raise


async def create_transaction_from_data(receipt_data, source_account, token: str):
    """Membuat transaksi di Firefly III dari data yang diberikan."""
    receipt = ReceiptModel(**receipt_data)

    max_retries = 3
    retry_delay = 3
    last_error = None

    for attempt in range(max_retries):
        try:
            transaction_result = create_firefly_transaction(receipt, source_account, token)
            if transaction_result:
                print(f"Transaction created successfully with ID: {transaction_result['data']['id']}")
                return f"Transaction created successfully with ID: {transaction_result['data']['id']}"
            else:
                last_error = "Failed to create transaction. No response from Firefly III."
        except Exception as e:
            last_error = str(e)
            print(f"Error creating transaction (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay * (2**attempt))
    
    error_msg = f"Failed to create transaction after {max_retries} attempts. Last error: {last_error}"
    print(error_msg)
    return error_msg