"""
Claude API-integrasjon.
PRINSIPP: sender KUN ferdig verifiserte tall fra StockData.
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
_WARN_RECS = {"avvent", "selg"}


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
        if sd.pb_ratio < 0:
            lines.append(f"P/B: {sd.pb_ratio:.2f} ⚠️ (negativ bokverdi – høy gjeld)")
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
    """Extract JSON from Claude response, tolerating markdown fences."""
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
    """Call Claude and return {"rec": str, "grunn": str, "oppside": str}."""
    verified = _format_verified_numbers(sd)
    ask_txt = "ASK-berettiget" if sd.ask_eligible else "IKKE ASK"

    if mode == "portfolio":
        rec_opts = "Sterkt kjøp|Kjøp|Hold|Avvent|Selg"
        json_tmpl = '{"rec": "...", "grunn": "maks 12 ord"}'
    else:
        rec_opts = "Sterkt kjøp|Kjøp|Hold|Avvent|Unngå"
        json_tmpl = '{"rec": "...", "grunn": "maks 12 ord", "oppside": "spenn f.eks +10-30%"}'

    prompt = (
        f"Verdiinvestor. Svar KUN med JSON – ingen annen tekst:\n"
        f"{json_tmpl}\n"
        f"rec må være én av: {rec_opts}\n\n"
        f"Tall:\n{verified}\n{ask_txt}."
    )
    raw = _call_claude(prompt, max_tokens=100)
    data = _parse_json(raw)

    all_opts = ["Sterkt kjøp", "Kjøp", "Hold", "Avvent", "Selg", "Unngå"]
    rec = data.get("rec") or _fallback_rec(raw, all_opts)
    return {
        "rec": rec,
        "grunn": data.get("grunn", ""),
        "oppside": data.get("oppside", ""),
    }


def _key_metrics(sd: StockData) -> str:
    bits = []
    if sd.price:          bits.append(f"Kurs {sd.price:.1f}")
    if sd.pe_ratio:       bits.append(f"P/E {sd.pe_ratio:.1f}")
    if sd.pb_ratio:       bits.append(f"P/B {sd.pb_ratio:.2f}")
    if sd.ev_ebitda:      bits.append(f"EV/EBITDA {sd.ev_ebitda:.1f}")
    if sd.free_cash_flow: bits.append(f"FCF {sd.free_cash_flow:.0f}M")
    return " · ".join(bits)


def analyse_portfolio(stocks: list[StockData], thresholds: dict) -> str:
    """Returnerer kun salgssignaler (Selg/Avvent); én OK-linje hvis alt er greit."""
    with_data = [s for s in stocks if _has_data(s)]
    alerts = []

    for sd in with_data:
        result = _analyse_stock(sd, mode="portfolio")
        rec = result["rec"].lower()
        if rec in _WARN_RECS:
            emoji = "\U0001f534" if rec == "selg" else "\U0001f7e1"
            lines = [f"{emoji} *{sd.name}* ({sd.ticker}) – {result['rec']}"]
            m = _key_metrics(sd)
            if m:
                lines.append(m)
            if result["grunn"]:
                lines.append(result["grunn"])
            alerts.append("\n".join(lines))
        time.sleep(0.3)

    no_data = [s for s in stocks if not _has_data(s)]
    footer = f"\n\n_⚠️ Mangler kursdata for {len(no_data)} aksje(r): {', '.join(s.ticker for s in no_data)}_" if no_data else ""
    if not alerts:
        return f"✅ Ingen salgssignaler – alle {len(with_data)} aksjer OK{footer}"
    return "\n\n".join(alerts) + footer


def find_undervalued_ideas(stocks: list[StockData], thresholds: dict) -> str:
    """Returnerer kun Kjøp/Sterkt kjøp i kompakt format."""
    candidates = [sd for sd in stocks if sd.price is not None]
    if not candidates:
        return "_Ingen kandidater med kursdata._"

    buys = []
    for sd in candidates:
        result = _analyse_stock(sd, mode="idea")
        rec = result["rec"].lower()
        if rec in _BUY_RECS:
            emoji = "\U0001f7e2" if rec == "sterkt kjøp" else "✅"
            lines = [f"{emoji} *{sd.name}* ({sd.ticker}) – {result['rec']}"]
            m = _key_metrics(sd)
            if m:
                lines.append(m)
            if result["grunn"]:
                lines.append(result["grunn"])
            if result["oppside"]:
                lines.append(f"Oppside: {result['oppside']}")
            buys.append("\n".join(lines))
        time.sleep(0.3)

    if not buys:
        return "_Ingen kjøpsideer passerte kriteriene denne uken._"
    return "\n\n".join(buys)


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
    return _call_claude(prompt, max_tokens=500)


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
