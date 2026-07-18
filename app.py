#!/usr/bin/env python3
"""
Warframe Market - Preturi seturi Prime (server local).
Ruleaza: python3 app.py  ->  http://localhost:8777
Zero dependinte externe (doar stdlib).

- Lista = doar seturi Prime.
- Refresh = scaneaza preturile seturilor (~80s).
- Componentele se incarca on-demand cand deschizi dropdown-ul unui set.
"""
import json
import os
import threading
import time
import urllib.request
import urllib.error
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data")
ITEMS_FILE = os.path.join(DATA_DIR, "items.json")     # metadata toate item-urile (id/slug/name/tags)
SETS_FILE = os.path.join(DATA_DIR, "sets.json")       # slug set -> componente (cache static)
PRICES_FILE = os.path.join(DATA_DIR, "prices.json")   # slug -> pret
VAULTED_FILE = os.path.join(DATA_DIR, "vaulted.json") # nume item -> vaulted (sursa: warframestat.us)
PORT = 8777

API = "https://api.warframe.market/v2"
UA = "wfm-prices-local/1.0 (personal use)"
REQ_DELAY = 0.34  # ~3 req/s

CDN = "https://warframe.market/static/assets/"

os.makedirs(DATA_DIR, exist_ok=True)


def set_type(tags):
    t = set(tags)
    for tag, label in [("warframe", "Warframe"), ("primary", "Primary"),
                       ("secondary", "Secondary"), ("melee", "Melee"),
                       ("sentinel", "Companion"), ("archwing", "Archwing"),
                       ("archgun", "Archgun")]:
        if tag in t:
            return label
    return "Altele"

STATE = {"running": False, "done": 0, "total": 0, "phase": "", "started": 0, "error": ""}
LOCK = threading.Lock()
_ITEMS_CACHE = None  # (items_list, id2slug)


def http_get(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(2 + i * 2)
                continue
            if e.code == 404:
                return None
            time.sleep(1 + i)
        except Exception:
            time.sleep(1 + i)
    return None


def load_items(force=False):
    """Toate item-urile (metadata) + map id->slug. Cache pe disc + in memorie."""
    global _ITEMS_CACHE
    if _ITEMS_CACHE and not force:
        return _ITEMS_CACHE
    items = None
    if not force and os.path.exists(ITEMS_FILE):
        with open(ITEMS_FILE) as f:
            items = json.load(f)
    if items is None:
        d = http_get(f"{API}/items")
        if not d or "data" not in d:
            return [], {}
        items = []
        for it in d["data"]:
            en = it.get("i18n", {}).get("en", {})
            thumb = en.get("thumb")
            items.append({
                "id": it.get("id"),
                "slug": it.get("slug"),
                "name": en.get("name", it.get("slug")),
                "tags": it.get("tags", []),
                "thumb": (CDN + thumb) if thumb else None,
            })
        with open(ITEMS_FILE, "w") as f:
            json.dump(items, f)
    id2slug = {it["id"]: it["slug"] for it in items}
    _ITEMS_CACHE = (items, id2slug)
    return _ITEMS_CACHE


def prime_sets():
    """Doar seturile Prime (tag 'set' + 'prime')."""
    items, _ = load_items()
    return [it for it in items if "set" in it["tags"] and "prime" in it["tags"]]


def load_json(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def save_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f)
    os.replace(tmp, path)


def fetch_top(slug):
    """Pretul de acum = cel mai mic seller INGAME (ce arata si market-ul).
    Daca nu e nimeni ingame, cade pe cel mai mic online (marcat kind='online').
    """
    d = http_get(f"{API}/orders/item/{slug}/top")
    if not d or "data" not in d:
        return None
    sells = d["data"].get("sell", [])  # deja sortate crescator dupa platinum
    ingame = [s for s in sells if s.get("user", {}).get("status") == "ingame"]
    online = [s for s in sells if s.get("user", {}).get("status") == "online"]
    if ingame:
        r = {"price": ingame[0]["platinum"], "kind": "ingame", "sellers": len(ingame)}
    elif online:
        r = {"price": online[0]["platinum"], "kind": "online", "sellers": 0}
    else:
        r = {"price": None, "kind": None, "sellers": 0}
    r["updated"] = int(time.time())
    return r


def get_components(set_slug):
    """Componentele unui set: slug, nume, cantitate in set, ducati.
    Cache static in sets.json; intrarile vechi (fara qty) se refac automat.
    """
    sets = load_json(SETS_FILE, {})
    cached = sets.get(set_slug)
    if cached and all("qty" in c for c in cached):
        return cached
    items, _ = load_items()
    slug2name = {it["slug"]: it["name"] for it in items}
    d = http_get(f"{API}/item/{set_slug}/set")
    comps = []
    if d and d.get("data"):
        for it in d["data"].get("items", []):
            if it.get("setRoot"):
                continue  # exclude setul insusi
            s = it.get("slug")
            en = it.get("i18n", {}).get("en", {})
            comps.append({
                "slug": s,
                "name": slug2name.get(s) or en.get("name") or s,
                "qty": it.get("quantityInSet") or 1,
                "ducats": it.get("ducats") or 0,
            })
    sets[set_slug] = comps
    save_json(SETS_FILE, sets)
    return comps


WS_API = "https://api.warframestat.us/items?only=name,category,vaulted"
WS_CATS = {"Warframes", "Primary", "Secondary", "Melee", "Sentinels", "Pets", "Arch-Gun", "Archwing"}


def refresh_vaulted(max_age=86400):
    """Status vaulted/unvaulted per item Prime, dintr-un singur call bulk la
    warframestat.us (dataset WFCD; warframe.market nu are asta pe seturi).
    Cache in vaulted.json, reimprospatat daca e mai vechi de o zi.
    """
    v = load_json(VAULTED_FILE, None)
    if v and time.time() - v.get("updated", 0) < max_age:
        return v["map"]
    d = http_get(WS_API, tries=2)
    if not isinstance(d, list):
        return (v or {}).get("map", {})
    vm = {it["name"].lower(): bool(it.get("vaulted"))
          for it in d
          if it.get("category") in WS_CATS and "vaulted" in it and it.get("name")}
    save_json(VAULTED_FILE, {"updated": int(time.time()), "map": vm})
    return vm


def set_extras(comps, prices):
    """Ducati totali + suma pe bucati (cu cantitati) din cache-ul de preturi."""
    if not comps or not all("qty" in c for c in comps):
        return None, None
    ducats = sum(c["qty"] * (c.get("ducats") or 0) for c in comps)
    pp = [prices.get(c["slug"], {}).get("price") for c in comps]
    parts_sum = sum(v * c["qty"] for v, c in zip(pp, comps)) if all(v is not None for v in pp) else None
    return ducats, parts_sum


def scan_worker():
    """Scaneaza preturile seturilor Prime, apoi ale tuturor componentelor."""
    targets = prime_sets()
    prices = load_json(PRICES_FILE, {})
    with LOCK:
        STATE.update(running=True, done=0, total=len(targets), phase="seturi",
                     started=time.time(), error="")
    refresh_vaulted()  # un singur call bulk, doar daca cache-ul e mai vechi de o zi
    for i, it in enumerate(targets, 1):
        r = fetch_top(it["slug"])
        if r is not None:
            prices[it["slug"]] = r
        if i % 20 == 0:
            save_json(PRICES_FILE, prices)
        with LOCK:
            STATE["done"] = i
        time.sleep(REQ_DELAY)
    save_json(PRICES_FILE, prices)

    # structura seturilor (un call /set per set, doar prima data - apoi e cache)
    sets_cache = load_json(SETS_FILE, {})
    with LOCK:
        STATE.update(done=0, total=len(targets), phase="structura")
    for i, it in enumerate(targets, 1):
        cached = sets_cache.get(it["slug"])
        if not (cached and all("qty" in c for c in cached)):
            get_components(it["slug"])
            time.sleep(REQ_DELAY)
        with LOCK:
            STATE["done"] = i
    sets_cache = load_json(SETS_FILE, {})

    # preturile componentelor
    part_slugs, seen = [], set()
    for it in targets:
        for c in sets_cache.get(it["slug"], []):
            if c["slug"] not in seen:
                seen.add(c["slug"])
                part_slugs.append(c["slug"])
    with LOCK:
        STATE.update(done=0, total=len(part_slugs), phase="componente")
    for i, s in enumerate(part_slugs, 1):
        r = fetch_top(s)
        if r is not None:
            prices[s] = r
        if i % 25 == 0:
            save_json(PRICES_FILE, prices)
        with LOCK:
            STATE["done"] = i
        time.sleep(REQ_DELAY)
    save_json(PRICES_FILE, prices)
    with LOCK:
        STATE["running"] = False


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path, qs = parsed.path, urllib.parse.parse_qs(parsed.query)

        if path == "/" or path.startswith("/index"):
            with open(os.path.join(BASE, "index.html"), "rb") as f:
                self._send(200, f.read(), "text/html; charset=utf-8")

        elif path == "/api/data":
            prices = load_json(PRICES_FILE, {})
            sets_cache = load_json(SETS_FILE, {})
            vaulted_map = load_json(VAULTED_FILE, {}).get("map", {})
            rows = []
            for it in prime_sets():
                p = prices.get(it["slug"], {})
                ducats, parts_sum = set_extras(sets_cache.get(it["slug"]), prices)
                base = it["name"].lower().removesuffix(" set")
                rows.append({"slug": it["slug"], "name": it["name"],
                             "type": set_type(it["tags"]), "thumb": it.get("thumb"),
                             "ducats": ducats, "parts_sum": parts_sum,
                             "vaulted": vaulted_map.get(base), **p})
            self._send(200, json.dumps({"sets": rows}))

        elif path == "/api/components":
            slug = qs.get("slug", [""])[0]
            comps = get_components(slug)
            prices = load_json(PRICES_FILE, {})
            out, changed = [], False
            for c in comps:
                p = prices.get(c["slug"])
                # reia pretul daca lipseste sau e vechi (>15 min)
                if not p or time.time() - p.get("updated", 0) > 900:
                    r = fetch_top(c["slug"])
                    if r:
                        prices[c["slug"]] = r
                        p = r
                        changed = True
                    time.sleep(REQ_DELAY)
                out.append({"slug": c["slug"], "name": c["name"], "qty": c.get("qty", 1),
                            "ducats": c.get("ducats", 0), **(p or {})})
            if changed:
                save_json(PRICES_FILE, prices)
            # suma pe bucati tine cont de cantitati (ex: Fang Prime = 2x blade + 2x handle + 1x blueprint)
            sum_price = (sum(c["price"] * c["qty"] for c in out)
                         if out and all(c.get("price") is not None for c in out) else None)
            self._send(200, json.dumps({"components": out, "sum_price": sum_price}))

        elif path == "/api/status":
            with LOCK:
                s = dict(STATE)
            self._send(200, json.dumps(s))
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        if urllib.parse.urlparse(self.path).path == "/api/refresh":
            with LOCK:
                if STATE["running"]:
                    self._send(409, json.dumps({"error": "scan in curs"}))
                    return
            threading.Thread(target=scan_worker, daemon=True).start()
            self._send(200, json.dumps({"ok": True}))
        else:
            self._send(404, json.dumps({"error": "not found"}))


if __name__ == "__main__":
    print(f"Warframe Market - Preturi seturi Prime -> http://localhost:{PORT}")
    print("Ctrl+C ca sa opresti.")
    threading.Thread(target=refresh_vaulted, daemon=True).start()
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
