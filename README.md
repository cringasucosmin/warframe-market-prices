# Warframe Market — Prime Set Prices

Local tool that shows live prices for every Prime set on [warframe.market](https://warframe.market), with a full-set vs. buy-the-parts comparison and ducat values for Baro.

Zero external dependencies — just Python 3 (stdlib only).

## Run it

**Mac / Linux:**
```
python3 app.py
```

**Windows:**
```
py app.py
```

Then open **http://localhost:8777** in your browser.

## Features

- **All Prime sets** (~160) with the current price = lowest seller who is **ingame** (fallback: online, flagged)
- **By parts** — sum of the components with correct quantities (e.g. Fang Prime = 2x blade + 2x handle + 1x blueprint), with a badge showing the signed difference vs. the set: `+2` (parts cost more, buy the set) or `−4` in green (parts are cheaper, worth buying individually)
- **Ducats** — total ducat value of each set + ducats-per-platinum ratio (handy when Baro arrives)
- **Vaulted / Unvaulted status** — colored tag per set + dedicated filters, combinable with type filters (source: warframestat.us, refreshed daily; vaulted supply only shrinks over time, unvaulted prices are at their lowest)
- **Per-set dropdown** — every component with its own price, quantity and ducats
- **Search, type filters** (Warframe / Primary / Secondary / Melee...), sortable columns
- **"Own it" checkboxes** — mark what you already have; owned sets are hidden by default and all counters update accordingly (stored in the browser, per machine)
- **English / Romanian UI** — toggle button in the header, choice is remembered

## Refresh

The Refresh button scans in 3 phases: set prices → set structure (first run only, then cached) → component prices.

- First full scan: **~5 minutes** (the API allows ~3 requests/sec)
- Subsequent scans are faster (structure phase is skipped)
- Existing data stays visible while scanning and updates as it goes

## Notes

- The `data/` folder is a local cache (rebuilds itself) — not tracked in git
- Prices come from the public warframe.market v2 API; vaulted status from the public warframestat.us API. Be nice to both — the built-in rate limiting stays within their guidelines
