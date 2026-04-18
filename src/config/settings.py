from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    trendyol_api_key: str = ""
    trendyol_api_secret: str = ""
    trendyol_supplier_id: str = ""

    hepsiburada_username: str = ""
    hepsiburada_password: str = ""
    hepsiburada_merchant_id: str = ""

    n11_app_key: str = ""
    n11_app_secret: str = ""
    n11_shipment_template: str = "Aras Kargo"

    amazon_lwa_app_id: str = ""
    amazon_lwa_client_secret: str = ""
    amazon_refresh_token: str = ""
    amazon_seller_id: str = ""
    amazon_marketplace_id: str = "A33AVAJ2PDY3EV"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
