"""Channel3, the product catalog behind a listing contract."""

from app.integrations.channel3.client import CatalogError, search_catalog

__all__ = ["CatalogError", "search_catalog"]
