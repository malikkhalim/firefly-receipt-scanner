from pydantic import BaseModel


class ReceiptModel(BaseModel):
    date: str
    amount: float
    store_name: str
    category: str
    budget: str
