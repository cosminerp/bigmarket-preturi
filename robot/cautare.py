"""Magazinele online care vând același cod de bare.
1. Căutarea (cu credite Serper) se face O SINGURĂ DATĂ pe produs; păstrăm adresele găsite.
2. Reverificarea e gratuită: deschidem direct paginile păstrate (doar unde robots.txt-ul magazinului permite) și citim prețul
   din datele structurate, doar dacă pagina are același cod de bare. Fără credite.
Plafon: MAX_TOTAL căutări în total (implicit 2.400, cele gratuite); peste, doar cu acordul lui Cosmin."""
import json
import os
import re
import time
import urllib.robotparser
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import requests

import jsonld_price as jl
from comun import OUT, UA, combine, eans, now_iso, read, write_rows

STARE = OUT / "_cautare_stare.json"
METODA = "cautare_google"
SKIP = re.compile(r"(^|\.)(bigmarket\.ro|auchan\.ro|compari\.ro|pricy\.ro|shopmania\.ro|price\.ro|biano\.ro|glami\.ro|okazii\.ro|olx\.ro|"
                  r"facebook\.com|instagram\.com|youtube\.com|tiktok\.com|pinterest\.|wikipedia\.org|openfoodfacts\.org|"
                  r"google\.|issuu\.com|scribd\.com|catalog|oferte|prospect|anpc|gs1)", re.I)
_ROBOTS = {}


def allowed(url):
    host = urlparse(url).netloc.lower()
    if host not in _ROBOTS:
        rp = urllib.robotparser.RobotFileParser()
        try:
            r = requests.get(f"https://{host}/robots.txt", headers=UA, timeout=12)
            rp.parse(r.text.splitlines() if r.status_code == 200 else [])
        except Exception:  # noqa: BLE001
            rp.parse([])
        _ROBOTS[host] = rp
    return _ROBOTS[host].can_fetch("BigMarketPriceCheck", url)


def shop_url(u):
    p = urlparse(u)
    host = p.netloc.lower().removeprefix("www.")
    return p.scheme in ("http", "https") and host.endswith(".ro") and not SKIP.search(host) and not u.lower().endswith(".pdf")


def read_price(url, ean):
    """(preț, stare). stare „eroare” = nu știm nimic (rețea, interzis): nu schimbăm rândul."""
    if not allowed(url):
        return None, "eroare"
    try:
        r = requests.get(url, headers=UA, timeout=20)
    except Exception:  # noqa: BLE001
        return None, "eroare"
    if r.status_code in (404, 410):
        return None, "pagina nu mai există"
    if r.status_code != 200:
        return None, "eroare"
    price = jl.parse_page(r.text[:2_000_000], ean)
    return (price, "ok") if price else (None, "fără preț sau alt cod de bare")


def put(ean, url, price, why):
    rows = read(OUT / f"{ean}.json", {}).get("preturi") or []
    dom = urlparse(url).netloc.lower().removeprefix("www.")
    prev = next((x for x in rows if x.get("url") == url or (x.get("metoda") == METODA and x.get("domeniu") == dom)), None)
    rows = [x for x in rows if x is not prev]
    t = now_iso()
    if price:
        rows.append({"url": url, "domeniu": dom, "pret": f"{price:.2f}", "stare": "ok", "verificat": t, "vazut": t, "metoda": METODA})
    elif prev and prev.get("pret"):
        rows.append({**prev, "stare": why, "verificat": t})                      # ultimul preț rămâne, cu data „vazut”
    write_rows(ean, rows)


def reverify(stop):
    now, n = datetime.now(timezone.utc), 0
    for f in sorted(OUT.glob("[0-9]*.json")):
        rec = read(f, {})
        for row in list(rec.get("preturi") or []):
            if time.monotonic() > stop:
                return n
            if row.get("metoda") != METODA:
                continue
            seen = datetime.fromisoformat(row.get("vazut") or row["verificat"])
            if now - datetime.fromisoformat(row["verificat"]) < timedelta(hours=6) or now - seen > timedelta(days=30):
                continue
            price, why = read_price(row["url"], rec["ean"])
            if why != "eroare":
                put(rec["ean"], row["url"], price, why)
            n += 1
            time.sleep(1.0)
    return n


def search(ean, key):
    r = requests.post("https://google.serper.dev/search", headers={"X-API-KEY": key, "Content-Type": "application/json"},
                      json={"q": ean, "gl": "ro", "hl": "ro", "num": 20}, timeout=25)
    if r.status_code in (400, 401, 402, 403, 429):
        raise PermissionError(f"Serper {r.status_code}: {r.text[:120]}")
    r.raise_for_status()
    return [x.get("link") or "" for x in (r.json().get("organic") or [])]


def main():
    stop = time.monotonic() + float(os.environ.get("MINUTE", "30")) * 60
    n_rev = reverify(stop - 10 * 60)                                  # reverificarea gratuită are prioritate, cel mult ~20 de minute
    key = os.environ.get("SERPER_API_KEY", "").strip()
    st = read(STARE, {})
    budget = int(os.environ.get("MAX_CAUTARI", "300"))
    cap = int(os.environ.get("MAX_TOTAL", "2400"))
    budget = max(0, min(budget, cap - len(st)))
    n = {"cautari": 0, "gasite": 0, "preturi": 0}
    if key and budget:
        for ean in [e for e in eans() if e not in st]:
            if n["cautari"] >= budget or time.monotonic() > stop:
                break
            try:
                links = search(ean, key)
            except PermissionError as e:
                print(f"Oprit: {e}")
                break
            except Exception as e:  # noqa: BLE001
                print(f"{ean}: {e}")
                continue
            n["cautari"] += 1
            shops, doms = [], set()
            for u in links:
                d = urlparse(u).netloc.lower().removeprefix("www.")
                if shop_url(u) and d not in doms:
                    shops.append(u)
                    doms.add(d)
            found = 0
            for u in shops[:8]:
                price, why = read_price(u, ean)
                if price:
                    put(ean, u, price, why)
                    found += 1
                time.sleep(0.7)
            st[ean] = {"t": now_iso(), "magazine": found}
            n["gasite"] += bool(found)
            n["preturi"] += found
        STARE.write_text(json.dumps(st, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tot = combine()
    print(f"Căutare: {n['cautari']} căutări noi ({len(st)} din plafonul de {cap}), {n['gasite']} produse găsite în {n['preturi']} magazine; "
          f"reverificate gratuit {n_rev}; {tot} produse cu prețuri în preturi.json" + ("" if key else "; fără cheia SERPER_API_KEY"))


if __name__ == "__main__":
    main()
