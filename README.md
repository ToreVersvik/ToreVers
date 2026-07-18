# Hold kontakten

Et enkelt verktøy for å huske å ta kontakt med folk. Kan kjøres helt lokalt
(uten innlogging) eller hostes på internett med passordbeskyttelse, slik at du
når den fra både mobil og PC.

Bygget med **Flask**. Lokalt brukes **SQLite** (følger med Python, ingenting å
sette opp); ved hosting brukes **PostgreSQL** automatisk hvis `DATABASE_URL` er
satt, slik at dataene består.

## Kjøre lokalt

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

### Nå appen fra mobil på samme WiFi

Vil du åpne den på telefonen mens du er hjemme, start appen slik at andre
enheter på nettet ditt slipper til, og finn PC-ens lokale IP-adresse:

```bash
HOST=0.0.0.0 python3 app.py
```

Åpne så `http://<PC-ens-IP>:5000` på mobilen (f.eks. `http://192.168.1.42:5000`).
PC-en må stå på og kjøre appen. Sett gjerne et passord (se under) hvis andre er
på nettverket.

## Hoste på internett (mobil + PC, hvor som helst)

For å nå appen fra hvor som helst må den hostes. Siden dette er personlige data
**skal du sette et passord** – da kreves innlogging før noen slipper inn.

### Helt gratis, og dataene består

Gratis hostingtjenester nullstiller filsystemet hver gang appen sover eller
oppdateres. Da forsvinner kontaktlista di hvis den ligger i en SQLite-fil «løst»
på serveren. Løsningen er å lagre dataene i en **gratis database utenfor**
web-appen. Appen bruker automatisk PostgreSQL når miljøvariabelen `DATABASE_URL`
er satt – ellers SQLite lokalt. Ingen kodeendring nødvendig.

Gratis-oppskrift: **Render** (web-app) + **Neon** (database). Begge har ekte
gratisnivåer, og til sammen koster det ingenting.

**Steg 1 – lag en gratis database (Neon):**

1. Lag konto på [neon.tech](https://neon.tech) (gratis).
2. Opprett et prosjekt. Du får en **tilkoblingsstreng** som ser slik ut:
   `postgresql://bruker:passord@ep-noe.eu-central-1.aws.neon.tech/neondb`
3. Kopier den – du trenger den i steg 2.

**Steg 2 – host web-appen gratis (Render):**

1. Lag konto på [render.com](https://render.com) og koble til GitHub-kontoen din.
2. Velg **New → Blueprint**, og pek på dette repoet. Render leser `render.yaml`.
3. Når den spør, fyll inn:
   - `HOLD_KONTAKTEN_PASSORD` = passordet du vil bruke for å logge inn.
   - `DATABASE_URL` = tilkoblingsstrengen fra Neon.
   - (`SECRET_KEY` lager Render selv.)
4. Trykk deploy. Etter et par minutter får du en `https://…onrender.com`-adresse
   du åpner på **både mobil og PC**. Tabellene opprettes automatisk første gang.

> **Godt å vite:** Render sin gratisplan lar appen «sove» etter en stund uten
> bruk, så første åpning kan ta 30–60 sekunder mens den våkner. Dataene i Neon
> ligger trygt uansett.

### Miljøvariabler

| Variabel                 | Hva den gjør |
|--------------------------|--------------|
| `HOLD_KONTAKTEN_PASSORD` | Passordet for å logge inn. **Settes den ikke, er appen åpen** (greit lokalt, men aldri ved hosting). |
| `DATABASE_URL`           | Tilkoblingsstreng til PostgreSQL. Er den satt, brukes Postgres; ellers lokal SQLite-fil. |
| `SECRET_KEY`             | Hemmelig nøkkel som signerer innloggingscookien. Sett en lang, tilfeldig verdi så du slipper å logge inn på nytt ved omstart. |
| `PORT` / `HOST`          | Port og adresse. Hostingtjenester setter som regel `PORT` selv. |
| `DATABASE_PATH`          | (Kun SQLite) hvor databasefila skal ligge lokalt. |

### Produksjonsserver lokalt (for test)

```bash
HOLD_KONTAKTEN_PASSORD=hemmelig SECRET_KEY=noe-langt-og-tilfeldig \
  gunicorn app:app --bind 0.0.0.0:8000
```

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
