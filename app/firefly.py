import json
import os
from datetime import datetime
from urllib.parse import urljoin

import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Firefly III configuration (only base URL is needed now as a fallback)
FIREFLY_III_URL_FALLBACK = os.getenv("FIREFLY_III_URL", "").rstrip("/")
API_BASE_PATH = "/api/v1/"

# Increase timeout for all requests
TIMEOUT = 30


def get_firefly_categories(firefly_url: str, firefly_token: str):
    api_url = urljoin(firefly_url, API_BASE_PATH)
    url = urljoin(api_url, "categories")
    headers = {
        "Authorization": f"Bearer {firefly_token}",
        "Accept": "application/json",
    }
    try:
        print(f"DEBUG: Mencoba terhubung ke URL: {url}") # <-- TAMBAHKAN INI
        response = requests.get(url, headers=headers, timeout=TIMEOUT)
        response.raise_for_status()
        categories_data = response.json()["data"]
        return [category["attributes"]["name"] for category in categories_data]
    except requests.exceptions.Timeout:
        print("Request to Firefly III timed out when fetching categories")
        return []
    except requests.exceptions.RequestException as e:
        print(f"DEBUG: Error saat mengambil kategori: {e}") # <-- TAMBAHKAN INI
        print(f"Error fetching categories: {e}")
        return []


def get_firefly_budgets(firefly_url: str, firefly_token: str):
    api_url = urljoin(firefly_url, API_BASE_PATH)
    url = urljoin(api_url, "budgets")
    headers = {
        "Authorization": f"Bearer {firefly_token}",
        "Accept": "application/json",
    }
    try:
        response = requests.get(url, headers=headers, timeout=TIMEOUT)
        response.raise_for_status()
        budgets_data = response.json()["data"]
        return [budget["attributes"]["name"] for budget in budgets_data]
    except requests.exceptions.Timeout:
        print("Request to Firefly III timed out when fetching budgets")
        return []
    except requests.exceptions.RequestException as e:
        print(f"Error fetching budgets: {e}")
        return []
    
    
def get_firefly_tags(firefly_url: str, firefly_token: str):
    api_url = urljoin(firefly_url, API_BASE_PATH)
    url = urljoin(api_url, "tags")
    headers = {
        "Authorization": f"Bearer {firefly_token}",
        "Accept": "application/json",
    }
    try:
        response = requests.get(url, headers=headers, timeout=TIMEOUT)
        response.raise_for_status()
        budgets_data = response.json()["data"]
        return [budget["attributes"]["name"] for budget in budgets_data]
    except requests.exceptions.Timeout:
        print("Request to Firefly III timed out when fetching tags")
        return []
    except requests.exceptions.RequestException as e:
        print(f"Error fetching budgets: {e}")
        return []



def get_firefly_asset_accounts(firefly_url: str, firefly_token: str):
    api_url = urljoin(firefly_url, API_BASE_PATH)
    url = urljoin(api_url, "accounts")
    headers = {
        "Authorization": f"Bearer {firefly_token}",
        "Accept": "application/json",
    }
    params = {"type": "asset"}
    try:
        response = requests.get(url, headers=headers, params=params, timeout=TIMEOUT)
        response.raise_for_status()
        accounts_data = response.json()["data"]
        return [account["attributes"]["name"] for account in accounts_data]
    except requests.exceptions.Timeout:
        print("Request to Firefly III timed out when fetching asset accounts")
        return []
    except requests.exceptions.RequestException as e:
        print(f"Error fetching asset accounts: {e}")
        return []


def create_firefly_transaction(
    receipt,
    source_account: str,
    firefly_url: str,
    firefly_token: str,
):
    api_url = urljoin(firefly_url, API_BASE_PATH)
    url = urljoin(api_url, "transactions")
    headers = {
        "Authorization": f"Bearer {firefly_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    try:
        date_obj = datetime.strptime(receipt.date, "%Y-%m-%d")
        formatted_date = date_obj.strftime("%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        print(f"Invalid date format: {receipt.date}. Using current date instead.")
        formatted_date = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")

    payload = {
        "transactions": [
            {
                "type": "withdrawal",
                "date": formatted_date,
                "amount": str(receipt.amount),
                "description": receipt.description,
                "destination_name": receipt.store_name,
                "source_name": source_account,
                "category_name": receipt.category,
                "budget_name": receipt.budget,
                "tags": receipt.tags,
            }
        ]
    }

    try:
        print(f"Sending transaction to Firefly III: {json.dumps(payload, indent=2)}")
        response = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT)

        print(f"Response status: {response.status_code}")
        print(f"Response headers: {response.headers}")

        if response.status_code in [200, 201]:
            return response.json()
        elif response.status_code == 401:
            raise Exception(
                "Authentication failed. Please check your Firefly III API token."
            )
        else:
            error_message = f"Error creating transaction: HTTP {response.status_code}"
            try:
                error_data = response.json()
                if "message" in error_data:
                    error_message += f" - {error_data['message']}"
            except Exception:
                error_message += f" - {response.text}"
            raise Exception(error_message)
    except requests.exceptions.Timeout:
        print("Request to Firefly III timed out when creating transaction")
        raise Exception(
            "The request to Firefly III timed out. The server might be experiencing high load or connectivity issues."
        )
    except requests.exceptions.ConnectionError:
        print("Connection error when creating transaction")
        raise Exception(
            "Could not connect to Firefly III. Please check your internet connection and Firefly III URL."
        )
    except requests.exceptions.RequestException as e:
        print(f"Error creating transaction: {e}")
        raise Exception(f"Error communicating with Firefly III: {str(e)}")