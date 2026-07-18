# Hold kontakten

Et enkelt, lokalt verktøy for å huske å ta kontakt med folk. Ingen ekstern
hosting, ingen innlogging – kjører kun på din egen maskin (`localhost`).

Bygget med **Flask + SQLite** (SQLite følger med Python, ingen database å sette opp).

## Kom i gang

```bash
# 1. (valgfritt) lag et virtuelt miljø
python3 -m venv .venv
source .venv/bin/activate

# 2. installer avhengigheter
pip install -r requirements.txt

# 3. start appen
python3 app.py
```

Åpne så **http://127.0.0.1:5000** i nettleseren.

Databasen (`hold_kontakten.db`) opprettes automatisk første gang appen starter,
og ligger i prosjektmappen. Den er med i `.gitignore` slik at dine personlige
data ikke havner i git.

## Datamodell

| Tabell              | Felter |
|---------------------|--------|
| `personer`          | id, navn, relasjon (venn/familie/kollega), interesser (tags), siste_kontakt_dato, notater |
| `ledige_dager`      | id, dato, tidspunkt (dag/kveld/helg), status (ledig/opptatt) |
| `aktivitetsforslag` | id, tittel, beskrivelse, passer_interesser (tags), meldingsmal |

## Funksjonalitet

### Fase 1 ✅ (ferdig)
- **Dashboard** – liste over personer sortert etter lengst tid siden siste kontakt.
  Personer du aldri har kontaktet, eller ikke har snakket med på over 60 dager,
  fremheves.
- **Personer** – legg til, rediger og slett personer.
- **Ledige dager** – legg til, rediger og slett dager du er ledig.

### Fase 2 (planlagt)
- CRUD for aktivitetsforslag.
- Matching-logikk: gitt en ledig dag, foreslå person (lengst siden kontakt +
  relevante interesser) og passende aktivitet.
- Forslagskort: «Inviter [navn] til [aktivitet] på [dato]» med ferdig utfylt
  meldingsmal.

### Fase 3 (valgfritt senere)
- «Kopier melding»-knapp til utklippstavlen.
- «Markert som kontaktet» som oppdaterer `siste_kontakt_dato` automatisk.

Tabellen `aktivitetsforslag` er allerede opprettet i databasen, klar for Fase 2.
