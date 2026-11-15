"""Citirea prețului din datele structurate ale unei pagini de produs (schema.org Product), fără Django:
o folosește și serverul (comparator.py), și robotul de pe GitHub (tools/date_din_github.py)."""
import json
import re
from decimal import Decimal, InvalidOperation


def num(v):
    try:
        x = Decimal(str(v).replace(" ", "").replace(",", "."))
        return x if x > 0 else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def iter_products(node):
    if isinstance(node, list):
        for x in node:
            yield from iter_products(x)
    elif isinstance(node, dict):
        t = node.get("@type")
        if t == "Product" or (isinstance(t, list) and "Product" in t):
            yield node
        for k in ("@graph", "itemListElement", "item", "mainEntity"):
            if k in node:
                yield from iter_products(node[k])


def parse_page(html, ean):
    """Prețul din pagină, doar dacă produsul are același cod de bare. Întoarce Decimal sau None."""
    ean = re.sub(r"\D", "", ean or "").lstrip("0")
    for m in re.finditer(r"<script[^>]+application/ld\+json[^>]*>(.*?)</script>", html, re.S | re.I):
        try:
            data = json.loads(m.group(1).strip())
        except Exception:  # noqa: BLE001
            continue
        for prod in iter_products(data):
            codes = [str(prod.get(k) or "") for k in ("gtin13", "gtin", "gtin8", "gtin14", "gtin12", "sku", "mpn")]
            if not ean or not any(re.sub(r"\D", "", c).lstrip("0") == ean for c in codes if c):
                continue
            offers = prod.get("offers") or {}
            offers = offers if isinstance(offers, list) else [offers]
            for o in offers:
                if not isinstance(o, dict):
                    continue
                cur = (o.get("priceCurrency") or "RON").upper()
                spec = o.get("priceSpecification") or {}
                spec = next((x for x in spec if isinstance(x, dict) and x.get("price")), {}) if isinstance(spec, list) else spec
                price = num(o.get("price") or o.get("lowPrice") or (spec.get("price") if isinstance(spec, dict) else None))
                avail = str(o.get("availability") or "")
                if price and cur in ("RON", "LEI") and "OutOfStock" not in avail and "Discontinued" not in avail:
                    return price
    return None
