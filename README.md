# Madplan 🥕

En enkel madplan og indkøbshjælp til [nemlig.com](https://www.nemlig.com).

1. **Læser din ordrehistorik** og finder det, du typisk køber.
2. **Foreslår lækre retter**, der passer til det, du plejer at købe. Du kan bytte retter, vælge præferencer og tilføje dine egne opskrifter fra et link.
3. **Laver en indkøbsliste.** Varer, du har købt før, bliver brugt først. Andre varer bliver fundet ved søgning.
4. **Foreslår basisvarer**, du ofte køber (mælk, rugbrød, æg …). Varer, som det er "tid til" at købe igen, er valgt på forhånd.
5. **Spørger, før den lægger noget i kurven.** Du betaler og vælger levering selv på nemlig.com.

Appen kører lokalt på din computer. Dit kodeord bliver ikke sendt andre steder hen end til nemlig.com.

## Installation

Kræver Python 3.10 eller nyere.

```bash
git clone https://github.com/WallAI/Madplan.git
cd Madplan
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Brug

Prøv appen med falske data (ingen login):

```bash
madplan --demo
```

Brug din rigtige nemlig.com-konto:

```bash
madplan
```

Browseren åbner http://127.0.0.1:8321. Log ind på siden. Du kan også sætte `NEMLIG_USERNAME` og `NEMLIG_PASSWORD` (fx i en `.env`-fil), så logger appen ind automatisk.

## Sådan virker det

| Del | Fil |
|---|---|
| Login, søgning, kurv | [`nemlig-shopper`](https://github.com/mhattingpete/nemlig-shopper) (MIT) |
| Ordrehistorik | `madplan/nemlig.py` – `webapi/order/GetBasicOrderHistory` og `webapi/order/GetOrderHistory` |
| Analyse (hyppighed, "tid til at købe igen") | `madplan/history.py` |
| 23 indbyggede opskrifter + import fra URL | `madplan/recipes.py` |
| Valg af retter og indkøbsliste | `madplan/planner.py` |
| Web-app og brugerflade | `madplan/app.py`, `madplan/static/index.html` |

Hentede ordrer bliver gemt i `~/.madplan/`, så appen ikke henter dem igen.

## Begrænsninger

- Nemlig.com har ikke et officielt API. Endpoints kan ændre sig uden varsel.
- Ordrehistorik-endpoints er ikke testet mod en rigtig konto endnu. Hvis historikken ikke kan hentes, virker appen stadig, men forslagene er ikke personlige.
- Appen gennemfører aldrig en bestilling. Den lægger kun varer i kurven.

## Test

```bash
pip install -e ".[dev]"
pytest
```

## Demo-side uden server

Byg én HTML-fil med demo-data, som kan åbnes direkte i en browser:

```bash
python scripts/build_preview.py madplan-demo.html
```
