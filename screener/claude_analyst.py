"""
Claude API-integrasjon.
PRINSIPP: sender KUN ferdig verifiserte tall fra StockData.
Claude gjetter aldri kurs, multipler eller utbytte.
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

_NO_DATA_MSG = "⚠️ Ingen kursdata – sjekk ticker i config.json."


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
        lines.append(f"Endring: {chg:+.1f}%")
    if sd.pe_ratio is not None:
        lines.append(f"P/E: {sd.pe_ratio:.1f}")
    if sd.pb_ratio is not None:
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


def analyse_portfolio(stocks: list[StockData], thresholds: dict) -> str:
    blocks = []
    for sd in stocks:
        if sd.fetch_error:
            blocks.append(f"*{sd.name}* ({sd.ticker}): datafeil – {sd.fetch_error}")
            continue
        if not _has_data(sd):
            blocks.append(f"*{sd.name}* ({sd.ticker})\n{_NO_DATA_MSG}")
            continue
        blocks.append(_analyse_single(sd, thresholds, mode="portfolio"))
        time.sleep(0.3)
    return "\n\n---\n\n".join(blocks)


def find_undervalued_ideas(stocks: list[StockData], thresholds: dict) -> str:
    candidates = [sd for sd in stocks if sd.price is not None]
    if not candidates:
        return "_Ingen kandidater med kursdata fra Oslo Børs-screener._"

    blocks = []
    for sd in candidates:
        blocks.append(_analyse_single(sd, thresholds, mode="idea"))
        time.sleep(0.3)
    return "\n\n---\n\n".join(blocks)


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
        "Finansanalytiker. Nyheter siste 7 dager – kun tese-relevante (resultat, utbytte, "
        "regulatorisk, oppkjøp). Ignorer generell markedskommentar.\n"
        "Format per aksje: *Ticker* – én setning om effekt (merket som tolkning).\n"
        "Maks 2 nyheter per aksje. Svar på norsk. Vær kort.\n\n"
        f"{json.dumps(news_payload, ensure_ascii=False)}"
    )
    return _call_claude(prompt, max_tokens=600)


def _analyse_single(sd: StockData, thresholds: dict, mode: str) -> str:
    verified = _format_verified_numbers(sd)
    ask_txt = "ASK-berettiget" if sd.ask_eligible else "IKKE ASK (vanlig konto)"

    if mode == "portfolio":
        prompt = (
            f"Verdiinvestor-analyse. Kun verifiserte tall – ikke finn på noe.\n"
            f"Svar MAKS 120 ord. Bruk bullet-punkter. Norsk.\n\n"
            f"Tall:\n{verified}\n\n"
            f"Gi: 1) Vurdering av tallene 2) Anbefaling (Sterkt kjøp/Kjøp/Hold/Avvent/Unngå) "
            f"3) Foreslått kjøpsnivå med margin of safety (kun hvis data finnes) "
            f"4) Oppside 1/3/5 år som spenn\n"
            f"{ask_txt}. "
            f"Avslutt: _Informasjon/læring, ikke finansiell rådgivning._"
        )
    else:
        prompt = (
            f"Verdiinvestor – undervurdert idé? Kun verifiserte tall.\n"
            f"Svar MAKS 80 ord. Norsk.\n\n"
            f"Tall:\n{verified}\n\n"
            f"Gi: 1) Verdikriterier oppfylt? (P/E, P/B, FCF) "
            f"2) Oppside pessimistisk/sannsynlig/optimistisk "
            f"3) Anbefaling (Sterkt kjøp/Kjøp/Hold/Avvent/Unngå)\n"
            f"{ask_txt}. "
            f"Avslutt: _Informasjon/læring, ikke finansiell rådgivning._"
        )

    return f"*{sd.name}* ({sd.ticker})\n{_call_claude(prompt, max_tokens=300)}"


def _call_claude(prompt: str, max_tokens: int = 300) -> str:
    try:
        client = _get_client()
        response = client.messages.create(
            model=_MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception as exc:
        log.error("Claude API-feil: %s", exc)
        return f"_[Claude API-feil: {exc}]_"
