from pydantic import BaseModel
from typing import List, Optional


class Product(BaseModel):
    title: str
    description: str
    price: float
    currency: str = "TRY"
    stock: int = 10
    brand: Optional[str] = None
    barcode: Optional[str] = None
    sku: Optional[str] = None
    category: Optional[str] = None
    images: List[str] = []
    attributes: dict = {}
    source_url: str = ""
    weight_kg: Optional[float] = None
