# Aksjescreener – prosjektinstruks for Claude Code

## Mål
Et halvautomatisk system: henter ferske tall, screener i kode, lar Claude-API-et
tolke de verifiserte tallene, og varsler meg. Jeg utfører alle handler **manuelt**
i Nordnet. Ingen automatisk ordreutførelse.

## Ufravikelig prinsipp
**Koden regner alle tall. Claude-API-et får KUN ferdig verifiserte tall** og skal
aldri finne på kurs, multipler eller utbytte. Mangler et tall (kommer som `null`)
→ hopp over den testen, ikke gjett. Output skal alltid skille tydelig mellom
«verifiserte tall» og «Claudes vurdering».

## To moduser
- **Daglig (lett, én intradag-kjøring):** kun terskel-/hendelsesvarsler. Helt
  stille hvis ingenting krysser en grense. Skal aldri si «vurder å handle» bare
  fordi kursen rørte seg litt.
- **Ukentlig (grundig rapport):** de tre seksjonene under.

## Ukentlig rapport
1. **Porteføljegjennomgang per aksje:** verifisert kurs + nøkkeltall; et estimert
   verdiintervall (fair value) med forutsetningene bak; vurdering av om den
   fortjener påfyll; og et foreslått **limit-kjøpsnivå** med margin of safety.
   Alt som estimat/intervall – ikke ett tall med fasit.
2. **Nye undervurderte ideer:** pris < 200 NOK/USD; estimert verdi eller
   analytikermål > dagens kurs; oppfyller verdikriteriene (lav P/E vs. bransje,
   P/B under ~1,5, EV/EBIT og EV/EBITDA under snitt, positiv fri kontantstrøm);
   oppgi oppside som spenn (pessimistisk/sannsynlig/optimistisk) med forutsetninger.
3. **Nyhetsdigest:** kun tese-relevante nyheter (resultat, utbytte, regulatorisk,
   oppkjøp) per aksje, med kort tolkning av mulig positiv/negativ effekt –
   tydelig merket som tolkning, ikke spådom.

## Data
- **Finnhub** for kurs + nøkkeltall (dekker USA godt).
- **Nordiske/Oslo-navn:** Finnhubs gratisnivå er tynt her. Lag et tydelig,
  **pluggbart datakilde-lag** (et interface) slik at en bedre Norden-feed kan
  settes inn senere, og støtt **manuelt innmatede tall** i config som fallback.
- Hemmeligheter ALDRI hardkodet – kun miljøvariabler.

## ASK-begrensning (viktig)
Alt som skal kunne utføres på min **ASK** må være EØS-aksjer eller aksjefond.
Amerikanske enkeltaksjer kan IKKE ligge i ASK → merk US-ideer tydelig som
«kun utenfor ASK (vanlig aksjekonto)».

## Varsling & drift
- **Telegram** (token/chat-id fra env); konsoll-fallback hvis ikke satt.
- **Cooldown** per navn for å unngå spam og overtrading.
- Logg alle varsler til `journal.jsonl` for etterprøving over tid.
- **Planlegging via GitHub Actions** (uovervåket, gratis): daglig kl 16:30 norsk
  tid på hverdager + ukentlig (f.eks. søndag kveld). Nøkler som repo-secrets.

## Output-stil
- Hver anbefaling: Sterkt kjøp / Kjøp / Hold / Avvent / Unngå + kort hvorfor.
- Oppside som 1/3/5-års spenn med forutsetninger.
- Avslutt alltid med at dette er til informasjon/læring, ikke finansiell rådgivning.

## Tekniske valg
- Python. Claude-API via `anthropic`-pakken, modell `claude-sonnet-4-6`
  (kostnadseffektiv for jevnlig bruk; kan byttes).
- Respekter rate limits (pause mellom kall).
- Hvis `screener.py` / `config.json` finnes i mappa: **utvid dem**. Ellers:
  bygg fra bunnen i samme ånd.
