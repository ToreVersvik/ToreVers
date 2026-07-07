"""
Claude API-integrasjon.
PRINSIPP: sender KUN ferdig verifiserte og kodumberegnede tall fra StockData.
Claude gjetter aldri kurs, multipler eller utbytte.
"""
import json
import os
import re
import time
import logging
from typing import Optional

import anthropic

from .data_sources.base import StockData

log = logging.getLogger(__name__)

_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")
_client: Optional[anthropic.Anthropic] = None

_BUY_RECS  = {"sterkt kjøp", "kjøp"}
_WARN_RECS = {"reduser", "selg"}

_SYSTEM_PROMPT = """Du er en konservativ, profesjonell porteføljeforvalter og aksjeanalytiker.

GRUNNPRINSIPPER:
- Baser alltid konklusjoner på de oppgitte, verifiserte tallene – aldri på synsing eller hype.
- Vær konservativ: hvis du er usikker, velg den mest forsiktige konklusjonen.
- En ny aksje anbefales KUN hvis den er bedre enn de svakeste i eksisterende portefølje.
- Det er fullt akseptabelt å konkludere: "Porteføljen er allerede sterk – ingen handling."
- Svar ALLTID på norsk.

KURSFALL – TOLKNING:
- Et kursfall er IKKE automatisk negativt. Undersøk om det skyldes utbytte, splitt, spin-off eller emisjon.
- GAV (gjennomsnittlig anskaffelseskurs) reflekterer ikke mottatte utbytter.
- Vurder alltid totalavkastning (kurs + utbytte), ikke kun prisutvikling.

KLASSIFISERING:
🟢 BEHOLD – investeringscaset er intakt
🟡 FØLG NØYE – noen forhold må overvåkes
🟠 REDUSER – risikoen har økt eller bedre alternativer finnes
🔴 SELG – investeringscaset er vesentlig svekket

SCORING (0–100 poeng):
- Fundamentale forhold (0–40): vekst, EPS, FCF, marginer, gjeld, kapitalavkastning
- Verdsettelse (0–20): P/E, EV/EBITDA, EV/FCF, historisk verdsettelse
- Kvalitet (0–20): ledelse, konkurransefortrinn, markedsposisjon
- Teknisk bilde (0–20): trend, momentum, RSI, relativ styrke

Svar KUN med gyldig JSON, ingen annen tekst."""


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise EnvironmentError("ANTHROPIC_API_KEY ikke satt")
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


def _has_data(sd: StockData) -> bool:
    return sd.price is not None


def _format_verified_numbers(sd: StockData) -> str:
    lines = [f"{sd.ticker} | {sd.name} | {sd.exchange} | {sd.currency}"]
    if sd.price is not None:
        lines.append(f"Kurs: {sd.price:.2f}")
    if sd.prev_close is not None and sd.price is not None:
        chg = (sd.price - sd.prev_close) / sd.prev_close * 100
        lines.append(f"Daglig endring: {chg:+.1f}%")
    if sd.week52_high is not None and sd.week52_low is not None:
        lines.append(f"52-ukers intervall: {sd.week52_low:.2f} – {sd.week52_high:.2f}")
    if sd.sma50 is not None and sd.price is not None:
        diff = (sd.price - sd.sma50) / sd.sma50 * 100
        lines.append(f"SMA50: {sd.sma50:.2f} (kurs {diff:+.1f}% vs. SMA50)")
    if sd.sma200 is not None and sd.price is not None:
        diff = (sd.price - sd.sma200) / sd.sma200 * 100
        lines.append(f"SMA200: {sd.sma200:.2f} (kurs {diff:+.1f}% vs. SMA200)")
    if sd.rsi14 is not None:
        lines.append(f"RSI(14): {sd.rsi14:.0f}")
    if sd.pe_ratio is not None:
        lines.append(f"P/E: {sd.pe_ratio:.1f}")
    if sd.pb_ratio is not None:
        if sd.pb_ratio < 0:
            lines.append(f"P/B: {sd.pb_ratio:.2f} ⚠️ (negativ bokverdi)")
        else:
            lines.append(f"P/B: {sd.pb_ratio:.2f}")
    if sd.ev_ebitda is not None:
        lines.append(f"EV/EBITDA: {sd.ev_ebitda:.1f}")
    if sd.free_cash_flow is not None:
        lines.append(f"FCF: {sd.free_cash_flow:.0f}M")
    if sd.dividend_yield is not None:
        lines.append(f"Utbytte: {sd.dividend_yield*100:.1f}%")
    if sd.roe is not None:
        lines.append(f"ROE: {sd.roe*100:.1f}%")
    if sd.debt_to_equity is not None:
        lines.append(f"Gjeld/EK: {sd.debt_to_equity:.2f}")
    if sd.analyst_target_price is not None:
        lines.append(f"Analytikermål: {sd.analyst_target_price:.2f}")
    if sd.analyst_rating:
        lines.append(f"Konsensus: {sd.analyst_rating}")
    if not sd.ask_eligible:
        lines.append("⚠️ Kun utenfor ASK")
    return "\n".join(lines)


def _parse_json(raw: str) -> dict:
    text = re.sub(r"```(?:json)?\s*", "", raw).strip()
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return {}


def _fallback_rec(raw: str, options: list[str]) -> str:
    raw_lower = raw.lower()
    for r in options:
        if r.lower() in raw_lower:
            return r
    return "ukjent"


def _analyse_stock(sd: StockData, mode: str) -> dict:
    verified = _format_verified_numbers(sd)
    ask_txt = "ASK-berettiget" if sd.ask_eligible else "IKKE ASK"

    if mode == "portfolio":
        json_tmpl = ('{"score": 0-100, "rec": "BEHOLD|FØLG NØYE|REDUSER|SELG", '
                     '"grunn": "maks 15 ord", "tiltak": "maks 10 ord eller null"}')
        rec_opts = "BEHOLD|FØLG NØYE|REDUSER|SELG"
        framing = ""
    else:
        json_tmpl = ('{"score": 0-100, "rec": "Sterkt kjøp|Kjøp|Hold|Avvent|Unngå", '
                     '"grunn": "maks 15 ord", "oppside": "spenn f.eks +10-30%"}')
        rec_opts = "Sterkt kjøp|Kjøp|Hold|Avvent|Unngå"
        framing = (
            "Dette er et VERDI-idéscreen: mål er undervurderte aksjer med margin of safety "
            "og oppside, ikke bare de tryggeste store selskapene. Mindre og sykliske selskaper "
            "er akseptable dersom verdsettelsen er lav og kontantstrøm/balanse er intakt. "
            "Men avvis tydelige VERDIFELLER (fallende inntjening, uholdbar gjeld, strukturell "
            "nedgang) – billig alene er ikke nok.\n"
        )

    prompt = (
        f"{framing}"
        f"Analyser denne aksjen og svar KUN med JSON:\n{json_tmpl}\n"
        f"rec må være én av: {rec_opts}\n\n"
        f"Verifiserte tall:\n{verified}\n{ask_txt}."
    )
    raw = _call_claude(prompt, max_tokens=150)
    data = _parse_json(raw)

    all_portfolio_opts = ["BEHOLD", "FØLG NØYE", "REDUSER", "SELG"]
    all_idea_opts = ["Sterkt kjøp", "Kjøp", "Hold", "Avvent", "Unngå"]
    opts = all_portfolio_opts if mode == "portfolio" else all_idea_opts
    rec = data.get("rec") or _fallback_rec(raw, opts)
    return {
        "score": data.get("score"),
        "rec": rec,
        "grunn": data.get("grunn", ""),
        "oppside": data.get("oppside", ""),
        "tiltak": data.get("tiltak", ""),
    }


def _key_metrics(sd: StockData) -> str:
    bits = []
    if sd.price:          bits.append(f"Kurs {sd.price:.1f}")
    if sd.market_cap:     bits.append(f"Mcap {_fmt_mcap(sd.market_cap)}")
    if sd.pe_ratio:       bits.append(f"P/E {sd.pe_ratio:.1f}")
    if sd.pb_ratio:       bits.append(f"P/B {sd.pb_ratio:.2f}")
    if sd.ev_ebitda:      bits.append(f"EV/EBITDA {sd.ev_ebitda:.1f}")
    if sd.free_cash_flow: bits.append(f"FCF {sd.free_cash_flow:.0f}M")
    up = _upside_to_target(sd)
    if up is not None:    bits.append(f"→ mål {up*100:+.0f}%")
    if sd.rsi14:          bits.append(f"RSI {sd.rsi14:.0f}")
    return " · ".join(bits)


def _fmt_mcap(mcap: float) -> str:
    """Markedsverdi i mrd/mill NOK, kort format."""
    if mcap >= 1e9:
        return f"{mcap/1e9:.1f}mrd"
    return f"{mcap/1e6:.0f}M"


def _upside_to_target(sd: StockData) -> Optional[float]:
    """Verifisert oppside til analytikermål (andel), None hvis mangler."""
    if sd.analyst_target_price and sd.price and sd.price > 0:
        return (sd.analyst_target_price - sd.price) / sd.price
    return None


def _value_score(sd: StockData) -> float:
    """Kode-beregnet verdiscore: belønner billighet + oppside + mindre størrelse.
    Høyere = mer attraktiv verdi. Alle input er verifiserte tall – ingen gjetning.
    Brukes til å RANGERE kjøpsideer slik at de billigste/mest oppside-tunge
    kommer først, i stedet for de største og tryggeste blue-chip-navnene."""
    score = 0.0

    # Billighet: P/E (lavere = bedre)
    if sd.pe_ratio is not None and sd.pe_ratio > 0:
        if sd.pe_ratio <= 8:     score += 3
        elif sd.pe_ratio <= 12:  score += 2
        elif sd.pe_ratio <= 18:  score += 1

    # P/B (lavere = bedre)
    if sd.pb_ratio is not None and sd.pb_ratio > 0:
        if sd.pb_ratio <= 0.8:   score += 3
        elif sd.pb_ratio <= 1.2: score += 2
        elif sd.pb_ratio <= 1.5: score += 1

    # EV/EBITDA (lavere = bedre)
    if sd.ev_ebitda is not None and sd.ev_ebitda > 0:
        if sd.ev_ebitda <= 4:    score += 3
        elif sd.ev_ebitda <= 7:  score += 2
        elif sd.ev_ebitda <= 10: score += 1

    # Positiv fri kontantstrøm
    if sd.free_cash_flow is not None and sd.free_cash_flow > 0:
        score += 1

    # Oppside til analytikermål (verifisert)
    up = _upside_to_target(sd)
    if up is not None:
        if up >= 0.40:   score += 4
        elif up >= 0.25: score += 3
        elif up >= 0.15: score += 2
        elif up >= 0.05: score += 1

    # Utbytte (moderat bonus)
    if sd.dividend_yield is not None and sd.dividend_yield >= 0.03:
        score += 1

    # Størrelse-tilt: mindre selskaper får bonus (større oppside over tid)
    if sd.market_cap is not None:
        if sd.market_cap < 2e9:     score += 2   # small cap (< 2 mrd NOK)
        elif sd.market_cap < 20e9:  score += 1   # mid cap (2–20 mrd NOK)

    return score


_REC_EMOJI = {
    "behold":     "🟢",
    "følg nøye":  "🟡",
    "reduser":    "🟠",
    "selg":       "🔴",
}


def analyse_portfolio(stocks: list[StockData], thresholds: dict) -> str:
    """Returnerer tabell for alle aksjer + detaljert seksjon for varsel-aksjer."""
    with_data = [s for s in stocks if _has_data(s)]
    no_data   = [s for s in stocks if not _has_data(s)]

    rows = []
    alerts = []

    for sd in with_data:
        result = _analyse_stock(sd, mode="portfolio")
        rec     = result["rec"]
        rec_key = rec.lower()
        emoji   = _REC_EMOJI.get(rec_key, "⚪")
        score   = result.get("score")
        score_s = str(score) if score is not None else "–"
        tiltak  = result.get("tiltak") or "–"

        rows.append(f"| {sd.ticker:<8} | {score_s:>5} | {emoji} {rec:<12} | {tiltak} |")

        if rec_key in _WARN_RECS:
            detail = [f"\n{emoji} *{sd.name}* ({sd.ticker}) – {rec}"]
            m = _key_metrics(sd)
            if m:
                detail.append(m)
            if result["grunn"]:
                detail.append(result["grunn"])
            alerts.append("\n".join(detail))

        time.sleep(0.3)

    # Tabell
    header = "| Aksje    | Score | Status       | Tiltak |\n|----------|-------|--------------|--------|"
    table  = header + "\n" + "\n".join(rows) if rows else "_Ingen kursdata._"

    # Detaljer for varselaksjer
    detail_section = ("\n" + "\n".join(alerts)) if alerts else ""

    # Manglende data
    missing = (f"\n\n_⚠️ Mangler kursdata for: {', '.join(s.ticker for s in no_data)}_"
               if no_data else "")

    return table + detail_section + missing


def find_undervalued_ideas(stocks: list[StockData], thresholds: dict) -> str:
    """Rangerer kjøpsideer etter KODE-BEREGNET verdiscore (billighet + oppside +
    størrelse), ikke etter kvalitet. Slik surfacet de billigste/mest oppside-tunge
    ideene – der man historisk tjener mest – i stedet for de samme blue-chip-navnene.
    Claude VETER hver kandidat (Kjøp/Hold/Unngå) for å luke ut verdifeller."""
    candidates = [sd for sd in stocks if sd.price is not None]
    if not candidates:
        return "_Ingen kandidater med kursdata._"

    # Rangér etter kode-beregnet verdiscore – billigst/mest oppside først
    ranked = sorted(candidates, key=_value_score, reverse=True)
    log.info("Evaluerer %d kjøpskandidat(er) med Claude, rangert etter verdiscore…", len(ranked))

    buys = []
    for sd in ranked:
        vscore = _value_score(sd)
        result = _analyse_stock(sd, mode="idea")
        rec = result["rec"].lower()
        if rec in _BUY_RECS:
            emoji = "🟢" if rec == "sterkt kjøp" else "✅"
            lines = [f"{emoji} *{sd.name}* ({sd.ticker}) – {result['rec']}"]
            m = _key_metrics(sd)
            if m:
                lines.append(m)
            if result["grunn"]:
                lines.append(result["grunn"])
            if result["oppside"]:
                lines.append(f"Oppside: {result['oppside']}")
            if not sd.ask_eligible:
                lines.append("⚠️ Kun utenfor ASK")
            buys.append((vscore, "\n".join(lines)))
            log.info("  KJØP: %s (verdiscore %.0f, %s)", sd.ticker, vscore, result["rec"])
        time.sleep(0.3)

    log.info("Kjøpsideer: %d av %d kandidater fikk Kjøp/Sterkt kjøp.", len(buys), len(ranked))

    if not buys:
        return "_Ingen kjøpsideer passerte kriteriene denne uken._"

    # Vis de 6 med høyest verdiscore blant kjøpsanbefalingene
    buys.sort(key=lambda x: -x[0])
    top = buys[:6]
    header = "_Rangert etter verdi (billighet + oppside + størrelse), ikke kvalitet._\n"
    return header + "\n\n".join(text for _, text in top)


def news_digest(stocks: list[StockData]) -> str:
    all_news_stocks = [sd for sd in stocks if sd.news]
    if not all_news_stocks:
        return "_Ingen nyheter de siste 7 dagene._"

    news_payload = {
        sd.ticker: {
            "name": sd.name,
            "ask_eligible": sd.ask_eligible,
            "news": sd.news[:3],
        }
        for sd in all_news_stocks
    }

    prompt = (
        "Nyheter siste 7 dager for disse aksjene. Skriv KUN ren tekst – INGEN JSON.\n"
        "Format: én linje per aksje med tese-relevante nyheter (resultat, utbytte, regulatorisk, oppkjøp).\n"
        "Ignorer generell markedskommentar og prisanalyser.\n"
        "Hvis ingen tese-relevante nyheter: hopp over aksjen.\n"
        "Maks 2 nyheter per aksje. Svar på norsk. Vær konkret.\n\n"
        f"{json.dumps(news_payload, ensure_ascii=False)}"
    )
    return _call_claude(prompt, max_tokens=600, system=_NEWS_SYSTEM)


_NEWS_SYSTEM = (
    "Du er en finansanalytiker. Skriv korte, faktabaserte nyhetssammendrag på norsk. "
    "Svar med ren tekst, IKKE JSON. "
    "Format: én linje per aksje: *Ticker* – effekt på investeringstesen (maks 20 ord). "
    "Inkluder kun tese-relevante nyheter (resultat, utbytte, regulatorisk, oppkjøp). "
    "Ignorer generell markedskommentar. Vær konkret og kortfattet."
)


def _call_claude(prompt: str, max_tokens: int = 300, system: str = "") -> str:
    try:
        client = _get_client()
        response = client.messages.create(
            model=_MODEL,
            max_tokens=max_tokens,
            system=system or _SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception as exc:
        log.error("Claude API-feil: %s", exc)
        return f"_[Claude API-feil: {exc}]_"
