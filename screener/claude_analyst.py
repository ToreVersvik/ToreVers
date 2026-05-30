"""
Claude API-integrasjon.
PRINSIPP: sender KUN ferdig verifiserte tall fra StockData.
"""
import os
import json
import time
import logging
from typing import Optional

import anthropic

from .data_sources.base import StockData

log = logging.getLogger(__name__)

_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")
_client: Optional[anthropic.Anthropic] = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise EnvironmentError("ANTHROPIC_API_KEY ikke satt")
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


def _format_verified_numbers(sd: StockData) -> str:
    lines = [f"Ticker: {sd.ticker} | Navn: {sd.name} | Børs: {sd.exchange} | Valuta: {sd.currency}"]
    if sd.price is not None:
        lines.append(f"Kurs: {sd.price:.2f}")
    if sd.prev_close is not None and sd.price is not None:
        chg = (sd.price - sd.prev_close) / sd.prev_close * 100
        lines.append(f"Endring siste dag: {chg:+.1f}%")
    if sd.pe_ratio is not None:
        lines.append(f"P/E: {sd.pe_ratio:.1f}")
    if sd.pb_ratio is not None:
        lines.append(f"P/B: {sd.pb_ratio:.2f}")
    if sd.ps_ratio is not None:
        lines.append(f"P/S: {sd.ps_ratio:.2f}")
    if sd.ev_ebitda is not None:
        lines.append(f"EV/EBITDA: {sd.ev_ebitda:.1f}")
    if sd.ev_ebit is not None:
        lines.append(f"EV/EBIT: {sd.ev_ebit:.1f}")
    if sd.free_cash_flow is not None:
        lines.append(f"Fri kontantstrøm (siste år): {sd.free_cash_flow:.0f}M {sd.currency}")
    if sd.dividend_yield is not None:
        lines.append(f"Dividendeavkastning: {sd.dividend_yield*100:.1f}%")
    if sd.roe is not None:
        lines.append(f"ROE: {sd.roe*100:.1f}%")
    if sd.debt_to_equity is not None:
        lines.append(f"Gjeld/EK: {sd.debt_to_equity:.2f}")
    if sd.analyst_target_price is not None:
        lines.append(f"Analytikermål (snitt): {sd.analyst_target_price:.2f}")
    if sd.analyst_rating:
        lines.append(f"Analytikerkonsensus: {sd.analyst_rating}")
    if not sd.ask_eligible:
        lines.append("ASK: NEI – kun utenfor ASK (vanlig aksjekonto)")
    return "\n".join(lines)


def analyse_portfolio(stocks: list[StockData], thresholds: dict) -> str:
    blocks = []
    for sd in stocks:
        if sd.fetch_error:
            blocks.append(f"*{sd.name}* ({sd.ticker}): datafeil – {sd.fetch_error}")
            continue
        blocks.append(_analyse_single(sd, thresholds, mode="portfolio"))
        time.sleep(0.5)
    return "\n\n---\n\n".join(blocks)


def find_undervalued_ideas(stocks: list[StockData], thresholds: dict) -> str:
    candidates = []
    for sd in stocks:
        if sd.price is None:
            continue
        max_price = thresholds.get("max_price_nok" if sd.currency == "NOK" else "max_price_usd", 200.0)
        if sd.price > max_price:
            continue
        candidates.append(sd)

    if not candidates:
        return "_Ingen kandidater oppfyller pris-kravet i watchlisten._"

    blocks = []
    for sd in candidates:
        blocks.append(_analyse_single(sd, thresholds, mode="idea"))
        time.sleep(0.5)
    return "\n\n---\n\n".join(blocks)


def news_digest(stocks: list[StockData]) -> str:
    all_news_stocks = [sd for sd in stocks if sd.news]
    if not all_news_stocks:
        return "_Ingen nyheter de siste 7 dagene._"

    news_payload = {}
    for sd in all_news_stocks:
        news_payload[sd.ticker] = {
            "name": sd.name,
            "ask_eligible": sd.ask_eligible,
            "news": sd.news[:5],
        }

    prompt = (
        "Du er en nøktern finansanalytiker. Under er nyheter (siste 7 dager) for aksjer "
        "i portefølje/watchlist. Alle data er hentet fra ekstern API – du skal IKKE finne "
        "på tall, kurs eller multipler.\n\n"
        "Filtrer ut kun nyheter som er tese-relevante: resultat, utbytte, regulatorisk, "
        "oppkjøp/fusjon. Ignorer generell markedskommentar. For hver relevant nyhet: "
        "gi én setning om mulig positiv/negativ effekt. Merk tydelig at dette er tolkning, "
        "ikke spådom. Aksjer som ikke er ASK-berettigede skal merkes «kun utenfor ASK».\n\n"
        f"DATA (JSON):\n{json.dumps(news_payload, ensure_ascii=False, indent=2)}\n\n"
        "Skriv svaret på norsk. Format: én seksjon per aksje med overskrift."
    )

    return _call_claude(prompt)


def _analyse_single(sd: StockData, thresholds: dict, mode: str) -> str:
    verified = _format_verified_numbers(sd)

    if mode == "portfolio":
        instructions = (
            "Du er en verdiinvestor. Du har mottatt *kun verifiserte tall* for én aksje. "
            "Du skal IKKE finne på tall, kurs, multipler eller utbytte – kun tolke de du har fått.\n\n"
            "Gi:\n"
            "1. Kort vurdering av nøkkeltallene\n"
            "2. Estimert verdiintervall (fair value) – oppgi som spenn og list forutsetningene\n"
            "3. Vurdering: Sterkt kjøp / Kjøp / Hold / Avvent / Unngå + kort begrunnelse\n"
            "4. Foreslått limit-kjøpsnivå med margin of safety (hvis aktuelt)\n"
            "5. Oppside som 1/3/5-års spenn med forutsetninger\n\n"
            "Hopp over vurderinger der du mangler grunnlagsdata (tall er ikke oppgitt).\n"
            "Skill tydelig mellom 'Verifiserte tall' og 'Claudes vurdering'.\n"
            f"Aksje er {'ASK-berettiget' if sd.ask_eligible else 'IKKE ASK-berettiget (kun vanlig aksjekonto)'}.\n"
            "Avslutt med: _Dette er til informasjon/læring, ikke finansiell rådgivning._"
        )
    else:
        instructions = (
            "Du er en verdiinvestor som leter etter undervurderte ideer. "
            "Du har mottatt *kun verifiserte tall*. Tall som mangler skal ikke gjettes.\n\n"
            "Gi:\n"
            "1. Er verdikriteriene oppfylt? (lav P/E vs bransje, P/B < 1,5, positiv FCF)\n"
            "2. Estimert oppside: pessimistisk / sannsynlig / optimistisk scenario med forutsetninger\n"
            "3. Anbefaling: Sterkt kjøp / Kjøp / Hold / Avvent / Unngå\n\n"
            "Hopp over kriterier der data mangler.\n"
            "Skill tydelig mellom 'Verifiserte tall' og 'Claudes vurdering'.\n"
            f"Aksje er {'ASK-berettiget' if sd.ask_eligible else 'IKKE ASK-berettiget (kun vanlig aksjekonto)'}.\n"
            "Avslutt med: _Dette er til informasjon/læring, ikke finansiell rådgivning._"
        )

    prompt = f"{instructions}\n\n**Verifiserte tall:**\n{verified}"
    return f"### {sd.name} ({sd.ticker})\n\n{_call_claude(prompt)}"


def _call_claude(prompt: str) -> str:
    try:
        client = _get_client()
        response = client.messages.create(
            model=_MODEL,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception as exc:
        log.error("Claude API-feil: %s", exc)
        return f"_[Claude API-feil: {exc}]_"
