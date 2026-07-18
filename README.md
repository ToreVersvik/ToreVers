# Hold kontakten

Et enkelt verktøy for å huske å ta kontakt med folk. Kan kjøres helt lokalt
(uten innlogging) eller hostes på internett med passordbeskyttelse, slik at du
når den fra både mobil og PC.

Bygget med **Flask + SQLite** (SQLite følger med Python, ingen database å sette opp).

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

### Miljøvariabler

| Variabel                 | Hva den gjør |
|--------------------------|--------------|
| `HOLD_KONTAKTEN_PASSORD` | Passordet for å logge inn. **Settes den ikke, er appen åpen** (greit lokalt, men aldri ved hosting). |
| `SECRET_KEY`             | Hemmelig nøkkel som signerer innloggingscookien. Sett en lang, tilfeldig verdi så du slipper å logge inn på nytt ved omstart. |
| `DATABASE_PATH`          | Hvor databasefila skal ligge. Ved hosting **må** denne peke på en varig disk (se under). |
| `PORT` / `HOST`          | Port og adresse. Hostingtjenester setter som regel `PORT` selv. |

### Viktig: dataene må overleve omstart

Mange hostingtjenester nullstiller filsystemet ved hver nye utrulling. Da vil
kontaktlista di forsvinne hvis SQLite-fila ligger «løst». Løsningen er en
**varig disk (volume)** som `DATABASE_PATH` peker inn i.

### Enkleste vei: Render

Repoet inneholder en ferdig `render.yaml`:

1. Lag konto på [render.com](https://render.com) og koble til GitHub-kontoen din.
2. Velg **New → Blueprint**, og pek på dette repoet. Render leser `render.yaml`.
3. Fyll inn `HOLD_KONTAKTEN_PASSORD` (passordet du vil bruke) når den spør.
4. Trykk deploy. Etter et par minutter får du en `https://…onrender.com`-adresse
   du kan åpne på både mobil og PC.

`render.yaml` setter opp en produksjonsserver (gunicorn), en tilfeldig
`SECRET_KEY`, og en 1 GB varig disk montert på `/data` der databasen lagres.

> **Merk:** varig disk krever Render sin «starter»-plan (betalt). Vil du teste
> gratis først, kan du fjerne `disk`-blokka og `DATABASE_PATH` i `render.yaml` –
> men da nullstilles dataene ved hver utrulling. Andre tjenester med gratis
> volum (f.eks. Fly.io) fungerer også; da kjører du samme `gunicorn`-kommando
> som i `Procfile`.

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
