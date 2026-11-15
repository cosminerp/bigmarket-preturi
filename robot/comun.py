"""Comun pentru roboții de prețuri: lista codurilor de bare, citirea și scrierea fișierelor din preturi/."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "preturi"
UA = {"User-Agent": "Mozilla/5.0 (compatible; BigMarketPriceCheck/1.0; +https://bigmarket.ro)", "Accept-Language": "ro-RO,ro;q=0.9"}


def eans():
    """Codurile de bare ale produselor Big Market (coduri.txt; primele sunt cele mai vândute)."""
    out = []
    for line in (ROOT / "coduri.txt").read_text(encoding="utf-8").splitlines():
        e = re.sub(r"\D", "", line)
        if len(e) in (8, 12, 13, 14) and not e.startswith("2") and e not in out:
            out.append(e)
    return out


def read(p, default):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_rows(ean, rows):
    f = OUT / f"{ean}.json"
    if rows:
        f.write_text(json.dumps({"ean": ean, "preturi": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    elif f.exists():
        f.unlink()


def combine():
    """Un singur fișier cu toate prețurile (preturi.json), pe care îl citește serverul bigmarket.ro."""
    allr = {}
    for f in sorted(OUT.glob("[0-9]*.json")):
        rec = read(f, {})
        if rec.get("preturi"):
            allr[rec.get("ean") or f.stem] = rec["preturi"]
    (ROOT / "preturi.json").write_text(json.dumps({"actualizat": now_iso(), "produse": allr}, ensure_ascii=False, separators=(",", ":")),
                                       encoding="utf-8")
    return len(allr)
