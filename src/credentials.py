"""
Güvenli kimlik bilgisi yöneticisi.
Windows'ta → Windows Credential Manager (keyring)
Linux/Mac  → sistem keyring veya .env fallback
"""
import os
from pathlib import Path

try:
    import keyring
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False

SERVICE = "XtechnxProductSync"


def _key(platform, field):
    return f"{platform}_{field}"


def set_credential(platform: str, field: str, value: str):
    """Kimlik bilgisini güvenli depoya kaydeder."""
    if KEYRING_AVAILABLE:
        try:
            keyring.set_password(SERVICE, _key(platform, field), value)
            return True
        except Exception:
            pass
    # Fallback: .env dosyasına yaz
    _write_env(platform, field, value)
    return True


def get_credential(platform: str, field: str) -> str:
    """Kimlik bilgisini okur. Önce keyring, sonra env."""
    if KEYRING_AVAILABLE:
        try:
            val = keyring.get_password(SERVICE, _key(platform, field))
            if val:
                return val
        except Exception:
            pass
    # Env'den oku
    env_key = f"{platform.upper()}_{field.upper()}"
    return os.environ.get(env_key, "")


def delete_credential(platform: str, field: str):
    if KEYRING_AVAILABLE:
        try:
            keyring.delete_password(SERVICE, _key(platform, field))
        except Exception:
            pass


def check_credentials(platform: str) -> dict:
    """Platform kimlik bilgilerinin dolu olup olmadığını kontrol eder."""
    fields = {
        "trendyol":    ["api_key", "api_secret", "supplier_id"],
        "hepsiburada": ["username", "password", "merchant_id"],
        "n11":         ["app_key", "app_secret"],
        "amazon":      ["lwa_app_id", "lwa_client_secret", "refresh_token", "seller_id"],
    }
    result = {}
    for field in fields.get(platform, []):
        val = get_credential(platform, field)
        result[field] = bool(val)
    result["ready"] = all(result.values())
    return result


def _write_env(platform, field, value):
    env_file = Path(".env")
    key = f"{platform.upper()}_{field.upper()}"
    lines = env_file.read_text(encoding="utf-8").splitlines() if env_file.exists() else []
    updated = False
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            updated = True
            break
    if not updated:
        lines.append(f"{key}={value}")
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
