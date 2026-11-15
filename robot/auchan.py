"""Prețurile Auchan după codul de bare (catalogul lor public VTEX, permis de robots.txt-ul lor):
  /api/catalog_system/pub/products/search?fq=alternateIds_Ean:<cod>
Doar același cod de bare, în stoc, prețul de vânzare de acum. O cerere pe secundă.
Codurile găsite se reverifică la 6 ore (urmărim cum evoluează prețul), cele negăsite după 7 zile."""
import argparse
import json
import re
import time
from datetime import datetime, timedelta, timezone

import requests

from comun import OUT, UA, combine, eans, now_iso, read, write_rows

STARE = OUT / "_auchan_stare.json"
API = "https://www.auchan.ro/api/catalog_system/pub/products/search"
DOM = "auchan.ro"


def lookup(ean, s):
    r = s.get(API, params={"fq": f"alternateIds_Ean:{ean}"}, headers={**UA, "Accept": "application/json"}, timeout=20)
    if r.status_code == 429:
        raise RuntimeError("429")
    if r.status_code not in (200, 206):
        raise RuntimeError(f"http {r.status_code}")
    for prod in r.json() or []:
        for it in prod.get("items") or []:
            if re.sub(r"\D", "", str(it.get("ean") or "")) != ean:
                continue
            for sel in it.get("sellers") or []:
                co = sel.get("commertialOffer") or {}
                if (co.get("Price") or 0) > 0 and (co.get("AvailableQuantity") or 0) > 0:
                    link = prod.get("link") or f"https://www.auchan.ro/{prod.get('linkText')}/p"
                    return round(float(co["Price"]), 2), link, (prod.get("productName") or "")[:200], co.get("ListPrice")
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minute", type=float, default=30)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    st = read(STARE, {})
    now = datetime.now(timezone.utc)

    def due(e):
        x = st.get(e)
        if not x:
            return True
        return now - datetime.fromisoformat(x["t"]) > (timedelta(hours=6) if x.get("ok") else timedelta(days=7))
    todo = [e for e in eans() if due(e)]
    todo.sort(key=lambda e: (e in st, st.get(e, {}).get("t", "")))
    stop = time.monotonic() + a.minute * 60
    s = requests.Session()
    n = {"verificate": 0, "gasite": 0, "erori": 0}
    errs = 0
    for e in todo:
        if time.monotonic() > stop:
            break
        try:
            hit = lookup(e, s)
            errs = 0
        except Exception as ex:  # noqa: BLE001
            n["erori"] += 1
            errs += 1
            if "429" in str(ex) or errs >= 5:
                time.sleep(30)
            if errs >= 12:
                break
            continue
        t = now_iso()
        rows = [x for x in read(OUT / f"{e}.json", {}).get("preturi") or [] if (x.get("domeniu") or "") != DOM]
        prev = next((x for x in read(OUT / f"{e}.json", {}).get("preturi") or [] if x.get("domeniu") == DOM), None)
        if hit:
            price, link, name, lst = hit
            rows.append({"url": link, "domeniu": DOM, "pret": f"{price:.2f}", "stare": "ok", "verificat": t, "vazut": t, "metoda": "auchan_catalog",
                         "nume": name, **({"pret_vechi": f"{float(lst):.2f}"} if lst and float(lst) > price else {})})
            n["gasite"] += 1
        elif prev and prev.get("pret"):
            rows.append({**prev, "stare": "nu mai e în stoc / nu mai există", "verificat": t})   # ultimul preț rămâne, cu data la care l-am văzut
        write_rows(e, rows)
        st[e] = {"t": t, "ok": bool(hit)}
        n["verificate"] += 1
        time.sleep(1.0)
    STARE.write_text(json.dumps(st, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tot = combine()
    print(f"Auchan: {n['verificate']} verificate ({n['gasite']} găsite, {n['erori']} erori); "
          f"{sum(1 for x in st.values() if x.get('ok'))} găsite la Auchan din {len(st)} verificate; {tot} produse cu prețuri în preturi.json")


if __name__ == "__main__":
    main()
