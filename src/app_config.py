import json
from pathlib import Path

_CONFIG_FILE = Path(__file__).parent.parent / "data" / "app_config.json"
_DEFAULTS = {
    "price_multiplier": 2.0,
    "source_site_selected": "merter",
    "source_site_name": "merterelektronik.com",
    "source_site_search_url": "https://www.merterelektronik.com/Arama?1&kelime={}",
    "source_site_login_url": "",
    "source_site_member_no": "",
    "source_site_username": "",
    "source_site_password": "",
}


def get_config() -> dict:
    if _CONFIG_FILE.exists():
        try:
            return {**_DEFAULTS, **json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))}
        except Exception:
            pass
    return dict(_DEFAULTS)


def set_config_value(key: str, value) -> None:
    cfg = get_config()
    cfg[key] = value
    _CONFIG_FILE.parent.mkdir(exist_ok=True)
    _CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
