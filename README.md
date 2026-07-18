# Warframe Market — Preturi seturi Prime

Tool local care arata preturile tuturor seturilor Prime de pe [warframe.market](https://warframe.market), cu comparatie set intreg vs. piese separate si valoarea in ducati pentru Baro.

Zero dependinte externe — doar Python 3 (stdlib).

## Rulare

**Mac / Linux:**
```
python3 app.py
```

**Windows:**
```
py app.py
```

Apoi deschide **http://localhost:8777** in browser.

## Ce face

- **Lista seturilor Prime** (~160) cu pretul curent = cel mai mic seller aflat **in joc** (fallback: online, marcat cu flag)
- **Pe bucati** — suma componentelor cu cantitati corecte (ex. Fang Prime = 2x blade + 2x handle + 1x blueprint), cu badge care-ti spune direct ce merita: `set −4` (setul e mai ieftin) sau `bucati −3` (piesele separate ies mai ieftin)
- **Ducati** — valoarea totala in ducati a setului + raportul ducati/platina (util cand vine Baro)
- **Dropdown pe fiecare set** — preturile fiecarei componente, cu cantitati si ducati
- **Vaulted / Unvaulted** — badge violet "V" pe seturile vaulted + filtre dedicate, combinabile cu tipul (sursa: warframestat.us, actualizata zilnic; la vaulted supply-ul scade si pretul urca in timp, la unvaulted preturile-s la minim)
- **Cauta, filtre pe tip** (Warframe / Primary / Secondary / Melee...), sortare pe orice coloana
- **Checkbox "am"** — bifezi ce ai deja, cu optiune sa le ascunzi (se salveaza in browser, per calculator)

## Refresh

Butonul Refresh scaneaza in 3 faze: preturile seturilor → structura seturilor (doar prima data, apoi e cache) → preturile componentelor.

- Prima scanare completa: **~5 minute** (API-ul are rate limit ~3 cereri/sec)
- Urmatoarele: mai rapide, sar peste faza de structura
- Datele raman afisate in timpul scanarii si se actualizeaza pe parcurs

## Note

- Folderul `data/` e cache local (se regenereaza singur) — nu e in git
- Preturile vin din API-ul public warframe.market v2, doar pentru uz personal
