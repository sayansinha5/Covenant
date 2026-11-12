"""Turn a Channel3 product into the fields a listing contract can rely on."""

from decimal import Decimal, InvalidOperation
from typing import Any


def search_mode(query: str) -> str:
    """A short product name stays on the fast search. A sentence is planned as a brief."""

    return "agentic" if len(query.split()) >= 8 else "default"


def map_product(raw: dict[str, Any]) -> dict[str, Any] | None:
    product_id = raw.get("id")
    title = raw.get("title")
    if not isinstance(product_id, str) or not isinstance(title, str) or not title.strip():
        return None
    offers = [_offer(item) for item in raw.get("offers") or []]
    offers = [offer for offer in offers if offer is not None][:4]
    prices = [Decimal(offer["price"]) for offer in offers if offer["price"]]
    description = raw.get("description") if isinstance(raw.get("description"), str) else ""
    return {
        "id": product_id,
        "title": title.strip()[:200],
        "description": " ".join(description.split())[:280],
        "brand": _brand(raw),
        "image_url": _image(raw),
        "price_from": f"{min(prices):.2f}" if prices else None,
        "currency": offers[0]["currency"] if offers else "USD",
        "offers": offers,
    }


def _brand(raw: dict[str, Any]) -> str:
    brands = raw.get("brands") or []
    if not brands:
        return ""
    first = brands[0]
    if isinstance(first, str):
        return first.strip()[:120]
    if isinstance(first, dict):
        name = first.get("name") or first.get("title") or ""
        return name.strip()[:120] if isinstance(name, str) else ""
    return ""


def _image(raw: dict[str, Any]) -> str | None:
    for image in raw.get("images") or []:
        url = image if isinstance(image, str) else ""
        if isinstance(image, dict):
            candidate = image.get("url") or image.get("src") or ""
            url = candidate if isinstance(candidate, str) else ""
        if url.startswith("https://"):
            return url
    return None


def _offer(raw: object) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    domain = raw.get("domain")
    if not isinstance(domain, str) or not domain:
        return None
    price_raw = raw.get("price") if isinstance(raw.get("price"), dict) else {}
    url = raw.get("url") if isinstance(raw.get("url"), str) else ""
    rate = raw.get("max_commission_rate")
    percent = None
    if isinstance(rate, int | float) and not isinstance(rate, bool) and rate > 0:
        percent = f"{rate * 100:.1f}".rstrip("0").rstrip(".")
    availability = raw.get("availability")
    return {
        "domain": domain[:120],
        "url": url if url.startswith("https://") else None,
        "price": _money(price_raw.get("price")),
        "currency": (
            price_raw.get("currency") if isinstance(price_raw.get("currency"), str) else "USD"
        ),
        "availability": availability if isinstance(availability, str) else "",
        "commission_percent": percent,
    }


def _money(value: object) -> str | None:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None
    if amount < 0:
        return None
    return f"{amount:.2f}"
