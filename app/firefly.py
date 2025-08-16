
import json
import os
from datetime import datetime
from urllib.parse import urljoin

import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Firefly III configuration
FIREFLY_III_URL = os.getenv("FIREFLY_III_URL", "").rstrip("/")
API_BASE_PATH = "/api/v1/"
API_URL = urljoin(FIREFLY_III_URL, API_BASE_PATH)

TIMEOUT = 30


def get_firefly_categories(token: str):
    if not token:
        print("Error: Firefly III token is missing.")
        return []
    url = urljoin(API_URL, "categories")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    try:
        response = requests.get(url, headers=headers, timeout=TIMEOUT)
        response.raise_for_status()
        categories_data = response.json()["data"]
        return [category["attributes"]["name"] for category in categories_data]
    except requests.exceptions.RequestException as e:
        print(f"Error fetching categories: {e}")
        return None


def get_firefly_budgets(token: str):
    if not token:
        print("Error: Firefly III token is missing.")
        return []
    url = urljoin(API_URL, "budgets")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    try:
        response = requests.get(url, headers=headers, timeout=TIMEOUT)
        response.raise_for_status()
        budgets_data = response.json()["data"]
        return [budget["attributes"]["name"] for budget in budgets_data]
    except requests.exceptions.RequestException as e:
        print(f"Error fetching budgets: {e}")
        return None


def get_firefly_asset_accounts(token: str):
    if not token:
        print("Error: Firefly III token is missing.")
        return []
    url = urljoin(API_URL, "accounts")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    params = {"type": "asset"}
    try:
        response = requests.get(url, headers=headers, params=params, timeout=TIMEOUT)
        response.raise_for_status()
        accounts_data = response.json()["data"]
        return [account["attributes"]["name"] for account in accounts_data]
    except requests.exceptions.RequestException as e:
        print(f"Error fetching asset accounts: {e}")
        return None


def create_firefly_transaction(receipt, source_account, token: str):
    if not token:
        raise ValueError("Firefly III token is required to create a transaction.")
    url = urljoin(API_URL, "transactions")
    headers = {
        "Authorization": f"Bearer {token}",
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
                "tags": ["automated"],
            }
        ]
    }

    try:
        print(f"Sending transaction to Firefly III: {json.dumps(payload, indent=2)}")
        response = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error creating transaction: {e}")
        if e.response:
            print(f"Response Body: {e.response.text}")
        raise