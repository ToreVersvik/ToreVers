"""Hold kontakten – lokal Flask-app for å huske å ta kontakt med folk.

Fase 1:
  - Dashboard: personer sortert etter lengst tid siden siste kontakt
  - CRUD for personer
  - CRUD for ledige dager

Fase 2:
  - CRUD for aktivitetsforslag
  - Matching: gitt en ledig dag, foreslå person (lengst siden kontakt +
    relevante interesser) og passende aktivitet, som ferdig utfylt melding
"""
import hmac
import os
import secrets
from datetime import date, datetime

from flask import (Flask, flash, redirect, render_template, request, session,
                   url_for)

import db

app = Flask(__name__)

# Hemmelig nøkkel for signering av innloggingscookien. Sett SECRET_KEY som
# miljøvariabel når appen hostes, så beholder du innloggingen mellom omstarter.
# Lokalt er en tilfeldig nøkkel helt fint.
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

# Passord for tilgang. Er den ikke satt, er appen åpen (praktisk lokalt,
# «ingen innlogging»). Setter du HOLD_KONTAKTEN_PASSORD – f.eks. når du hoster
# på internett – kreves passordet før du slipper inn.
APP_PASSORD = os.environ.get("HOLD_KONTAKTEN_PASSORD", "")

db.init_app(app)
# Sørg for at tabellene finnes, også når appen startes av en produksjonsserver
# (gunicorn) som ikke kjører __main__-blokka nederst.
with app.app_context():
    db.init_db()

RELASJONER = ["venn", "familie", "kollega"]
TIDSPUNKTER = ["dag", "kveld", "helg"]
STATUSER = ["ledig", "opptatt"]


# ---------------------------------------------------------------------------
# Innlogging (aktiv kun når HOLD_KONTAKTEN_PASSORD er satt)
# ---------------------------------------------------------------------------
# Sider som er tilgjengelige uten å være logget inn.
AAPNE_ENDEPUNKTER = {"login", "static"}


@app.before_request
def krev_innlogging():
    if not APP_PASSORD:
        return  # ingen passord satt – appen er åpen (lokal bruk)
    if request.endpoint in AAPNE_ENDEPUNKTER:
        return
    if session.get("innlogget"):
        return
    return redirect(url_for("login", neste=request.path))


@app.route("/login", methods=["GET", "POST"])
def login():
    # Er appen åpen, eller allerede innlogget, er det ingen grunn til login-siden.
    if not APP_PASSORD or session.get("innlogget"):
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        oppgitt = request.form.get("passord", "")
        if hmac.compare_digest(oppgitt, APP_PASSORD):
            session["innlogget"] = True
            session.permanent = True
            neste = request.args.get("neste") or url_for("dashboard")
            # Kun tillat interne stier (unngå åpen redirect).
            if not neste.startswith("/"):
                neste = url_for("dashboard")
            return redirect(neste)
        flash("Feil passord.", "feil")
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Du er logget ut.", "ok")
    return redirect(url_for("login"))


@app.context_processor
def injiser_auth():
    """Gjør innloggingsstatus tilgjengelig i alle maler (for logg ut-knappen)."""
    return {"auth_paa": bool(APP_PASSORD), "innlogget": session.get("innlogget", False)}


# ---------------------------------------------------------------------------
# Hjelpefunksjoner
# ---------------------------------------------------------------------------
def dager_siden(iso_dato):
    """Antall dager siden en ISO-dato, eller None hvis tom/ugyldig."""
    if not iso_dato:
        return None
    try:
        d = datetime.strptime(iso_dato, "%Y-%m-%d").date()
    except ValueError:
        return None
    return (date.today() - d).days


def parse_tags(tekst):
    """Gjør en kommaseparert streng til en liste med rensede, små tags."""
    if not tekst:
        return []
    return [t.strip().lower() for t in tekst.split(",") if t.strip()]


def fyll_melding(mal, navn, dato=None, aktivitet=None, tidspunkt=None):
    """Fyll inn plassholdere i en meldingsmal. Støtter {navn}, {dato},
    {aktivitet} og {tidspunkt}. Ukjente plassholdere lar vi stå."""
    if not mal:
        return ""
    erstatninger = {
        "navn": navn or "",
        "dato": dato or "",
        "aktivitet": aktivitet or "",
        "tidspunkt": tidspunkt or "",
    }
    resultat = mal
    for nokkel, verdi in erstatninger.items():
        resultat = resultat.replace("{" + nokkel + "}", verdi)
    return resultat


app.jinja_env.filters["dager_siden"] = dager_siden


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@app.route("/")
def dashboard():
    conn = db.get_db()
    # Sorter etter lengst tid siden siste kontakt. NULL (aldri kontaktet)
    # regnes som lengst siden, så de havner øverst.
    personer = conn.execute(
        """
        SELECT * FROM personer
        ORDER BY (siste_kontakt_dato IS NULL) DESC,
                 siste_kontakt_dato ASC,
                 navn ASC
        """
    ).fetchall()
    return render_template("dashboard.html", personer=personer)


# ---------------------------------------------------------------------------
# Personer – CRUD
# ---------------------------------------------------------------------------
@app.route("/personer")
def personer():
    conn = db.get_db()
    rader = conn.execute("SELECT * FROM personer ORDER BY navn ASC").fetchall()
    return render_template("personer.html", personer=rader)


@app.route("/personer/ny", methods=["GET", "POST"])
def person_ny():
    if request.method == "POST":
        data = _les_person_skjema()
        feil = _valider_person(data)
        if feil:
            flash(feil, "feil")
            return render_template("person_form.html", person=data,
                                   relasjoner=RELASJONER, tittel="Ny person")
        conn = db.get_db()
        conn.execute(
            """INSERT INTO personer (navn, relasjon, interesser, siste_kontakt_dato, notater)
               VALUES (?, ?, ?, ?, ?)""",
            (data["navn"], data["relasjon"], data["interesser"],
             data["siste_kontakt_dato"] or None, data["notater"]),
        )
        conn.commit()
        flash(f"La til {data['navn']}.", "ok")
        return redirect(url_for("personer"))
    return render_template("person_form.html", person={}, relasjoner=RELASJONER,
                           tittel="Ny person")


@app.route("/personer/<int:person_id>/rediger", methods=["GET", "POST"])
def person_rediger(person_id):
    conn = db.get_db()
    person = conn.execute("SELECT * FROM personer WHERE id = ?", (person_id,)).fetchone()
    if person is None:
        flash("Fant ikke personen.", "feil")
        return redirect(url_for("personer"))

    if request.method == "POST":
        data = _les_person_skjema()
        feil = _valider_person(data)
        if feil:
            flash(feil, "feil")
            data["id"] = person_id
            return render_template("person_form.html", person=data,
                                   relasjoner=RELASJONER, tittel="Rediger person")
        conn.execute(
            """UPDATE personer
               SET navn = ?, relasjon = ?, interesser = ?,
                   siste_kontakt_dato = ?, notater = ?
               WHERE id = ?""",
            (data["navn"], data["relasjon"], data["interesser"],
             data["siste_kontakt_dato"] or None, data["notater"], person_id),
        )
        conn.commit()
        flash(f"Oppdaterte {data['navn']}.", "ok")
        return redirect(url_for("personer"))

    return render_template("person_form.html", person=person,
                           relasjoner=RELASJONER, tittel="Rediger person")


@app.route("/personer/<int:person_id>/slett", methods=["POST"])
def person_slett(person_id):
    conn = db.get_db()
    conn.execute("DELETE FROM personer WHERE id = ?", (person_id,))
    conn.commit()
    flash("Slettet person.", "ok")
    return redirect(url_for("personer"))


def _les_person_skjema():
    return {
        "navn": request.form.get("navn", "").strip(),
        "relasjon": request.form.get("relasjon", "").strip(),
        "interesser": request.form.get("interesser", "").strip(),
        "siste_kontakt_dato": request.form.get("siste_kontakt_dato", "").strip(),
        "notater": request.form.get("notater", "").strip(),
    }


def _valider_person(data):
    if not data["navn"]:
        return "Navn er påkrevd."
    if data["relasjon"] not in RELASJONER:
        return "Velg en gyldig relasjon."
    if data["siste_kontakt_dato"]:
        try:
            datetime.strptime(data["siste_kontakt_dato"], "%Y-%m-%d")
        except ValueError:
            return "Siste kontakt-dato må være på formatet ÅÅÅÅ-MM-DD."
    return None


# ---------------------------------------------------------------------------
# Ledige dager – CRUD
# ---------------------------------------------------------------------------
@app.route("/dager")
def dager():
    conn = db.get_db()
    rader = conn.execute(
        "SELECT * FROM ledige_dager ORDER BY dato ASC, tidspunkt ASC"
    ).fetchall()
    return render_template("dager.html", dager=rader)


@app.route("/dager/ny", methods=["GET", "POST"])
def dag_ny():
    if request.method == "POST":
        data = _les_dag_skjema()
        feil = _valider_dag(data)
        if feil:
            flash(feil, "feil")
            return render_template("dag_form.html", dag=data, tidspunkter=TIDSPUNKTER,
                                   statuser=STATUSER, tittel="Ny ledig dag")
        conn = db.get_db()
        conn.execute(
            "INSERT INTO ledige_dager (dato, tidspunkt, status) VALUES (?, ?, ?)",
            (data["dato"], data["tidspunkt"], data["status"]),
        )
        conn.commit()
        flash("La til ledig dag.", "ok")
        return redirect(url_for("dager"))
    return render_template("dag_form.html", dag={}, tidspunkter=TIDSPUNKTER,
                           statuser=STATUSER, tittel="Ny ledig dag")


@app.route("/dager/<int:dag_id>/rediger", methods=["GET", "POST"])
def dag_rediger(dag_id):
    conn = db.get_db()
    rad = conn.execute("SELECT * FROM ledige_dager WHERE id = ?", (dag_id,)).fetchone()
    if rad is None:
        flash("Fant ikke dagen.", "feil")
        return redirect(url_for("dager"))

    if request.method == "POST":
        data = _les_dag_skjema()
        feil = _valider_dag(data)
        if feil:
            flash(feil, "feil")
            data["id"] = dag_id
            return render_template("dag_form.html", dag=data, tidspunkter=TIDSPUNKTER,
                                   statuser=STATUSER, tittel="Rediger ledig dag")
        conn.execute(
            "UPDATE ledige_dager SET dato = ?, tidspunkt = ?, status = ? WHERE id = ?",
            (data["dato"], data["tidspunkt"], data["status"], dag_id),
        )
        conn.commit()
        flash("Oppdaterte ledig dag.", "ok")
        return redirect(url_for("dager"))

    return render_template("dag_form.html", dag=rad, tidspunkter=TIDSPUNKTER,
                           statuser=STATUSER, tittel="Rediger ledig dag")


@app.route("/dager/<int:dag_id>/slett", methods=["POST"])
def dag_slett(dag_id):
    conn = db.get_db()
    conn.execute("DELETE FROM ledige_dager WHERE id = ?", (dag_id,))
    conn.commit()
    flash("Slettet ledig dag.", "ok")
    return redirect(url_for("dager"))


def _les_dag_skjema():
    return {
        "dato": request.form.get("dato", "").strip(),
        "tidspunkt": request.form.get("tidspunkt", "").strip(),
        "status": request.form.get("status", "").strip() or "ledig",
    }


def _valider_dag(data):
    if not data["dato"]:
        return "Dato er påkrevd."
    try:
        datetime.strptime(data["dato"], "%Y-%m-%d")
    except ValueError:
        return "Dato må være på formatet ÅÅÅÅ-MM-DD."
    if data["tidspunkt"] not in TIDSPUNKTER:
        return "Velg et gyldig tidspunkt."
    if data["status"] not in STATUSER:
        return "Velg en gyldig status."
    return None


# ---------------------------------------------------------------------------
# Aktivitetsforslag – CRUD
# ---------------------------------------------------------------------------
@app.route("/aktiviteter")
def aktiviteter():
    conn = db.get_db()
    rader = conn.execute(
        "SELECT * FROM aktivitetsforslag ORDER BY tittel ASC"
    ).fetchall()
    return render_template("aktiviteter.html", aktiviteter=rader)


@app.route("/aktiviteter/ny", methods=["GET", "POST"])
def aktivitet_ny():
    if request.method == "POST":
        data = _les_aktivitet_skjema()
        feil = _valider_aktivitet(data)
        if feil:
            flash(feil, "feil")
            return render_template("aktivitet_form.html", aktivitet=data,
                                   tittel="Nytt aktivitetsforslag")
        conn = db.get_db()
        conn.execute(
            """INSERT INTO aktivitetsforslag (tittel, beskrivelse, passer_interesser, meldingsmal)
               VALUES (?, ?, ?, ?)""",
            (data["tittel"], data["beskrivelse"], data["passer_interesser"],
             data["meldingsmal"]),
        )
        conn.commit()
        flash(f"La til «{data['tittel']}».", "ok")
        return redirect(url_for("aktiviteter"))
    return render_template("aktivitet_form.html", aktivitet={},
                           tittel="Nytt aktivitetsforslag")


@app.route("/aktiviteter/<int:aktivitet_id>/rediger", methods=["GET", "POST"])
def aktivitet_rediger(aktivitet_id):
    conn = db.get_db()
    rad = conn.execute(
        "SELECT * FROM aktivitetsforslag WHERE id = ?", (aktivitet_id,)
    ).fetchone()
    if rad is None:
        flash("Fant ikke aktiviteten.", "feil")
        return redirect(url_for("aktiviteter"))

    if request.method == "POST":
        data = _les_aktivitet_skjema()
        feil = _valider_aktivitet(data)
        if feil:
            flash(feil, "feil")
            data["id"] = aktivitet_id
            return render_template("aktivitet_form.html", aktivitet=data,
                                   tittel="Rediger aktivitetsforslag")
        conn.execute(
            """UPDATE aktivitetsforslag
               SET tittel = ?, beskrivelse = ?, passer_interesser = ?, meldingsmal = ?
               WHERE id = ?""",
            (data["tittel"], data["beskrivelse"], data["passer_interesser"],
             data["meldingsmal"], aktivitet_id),
        )
        conn.commit()
        flash(f"Oppdaterte «{data['tittel']}».", "ok")
        return redirect(url_for("aktiviteter"))

    return render_template("aktivitet_form.html", aktivitet=rad,
                           tittel="Rediger aktivitetsforslag")


@app.route("/aktiviteter/<int:aktivitet_id>/slett", methods=["POST"])
def aktivitet_slett(aktivitet_id):
    conn = db.get_db()
    conn.execute("DELETE FROM aktivitetsforslag WHERE id = ?", (aktivitet_id,))
    conn.commit()
    flash("Slettet aktivitetsforslag.", "ok")
    return redirect(url_for("aktiviteter"))


def _les_aktivitet_skjema():
    return {
        "tittel": request.form.get("tittel", "").strip(),
        "beskrivelse": request.form.get("beskrivelse", "").strip(),
        "passer_interesser": request.form.get("passer_interesser", "").strip(),
        "meldingsmal": request.form.get("meldingsmal", "").strip(),
    }


def _valider_aktivitet(data):
    if not data["tittel"]:
        return "Tittel er påkrevd."
    return None


# ---------------------------------------------------------------------------
# Forslag – matching mellom ledig dag, personer og aktiviteter
# ---------------------------------------------------------------------------
def _formater_dato(iso_dato):
    """Gjør 2026-07-25 til «lørdag 25. juli 2026» (norsk)."""
    ukedager = ["mandag", "tirsdag", "onsdag", "torsdag", "fredag",
                "lørdag", "søndag"]
    maaneder = ["januar", "februar", "mars", "april", "mai", "juni", "juli",
                "august", "september", "oktober", "november", "desember"]
    try:
        d = datetime.strptime(iso_dato, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return iso_dato
    return f"{ukedager[d.weekday()]} {d.day}. {maaneder[d.month - 1]} {d.year}"


def lag_forslag(dag, personer, aktiviteter_rader, maks=6):
    """Bygg forslagskort for en gitt ledig dag.

    Hver person pares med aktiviteten som passer interessene deres best.
    Kortene rangeres etter en kombinert score: lengst tid siden kontakt teller
    mest, og overlapp i interesser gir et løft.
    """
    dato_tekst = _formater_dato(dag["dato"])
    forslag = []

    for p in personer:
        p_tags = set(parse_tags(p["interesser"]))

        # Finn aktiviteten med størst overlapp i interesser.
        beste_akt = None
        beste_overlapp = -1
        felles_tags = []
        for a in aktiviteter_rader:
            a_tags = set(parse_tags(a["passer_interesser"]))
            felles = p_tags & a_tags
            if len(felles) > beste_overlapp:
                beste_overlapp = len(felles)
                beste_akt = a
                felles_tags = sorted(felles)

        if beste_akt is None:
            continue  # ingen aktiviteter finnes enda

        overlapp = max(beste_overlapp, 0)
        dager = dager_siden(p["siste_kontakt_dato"])
        # Aldri kontaktet rangeres helt øverst.
        dager_score = 400 if dager is None else min(dager, 400)
        score = dager_score + overlapp * 45

        melding = fyll_melding(
            beste_akt["meldingsmal"], navn=p["navn"], dato=dato_tekst,
            aktivitet=beste_akt["tittel"], tidspunkt=dag["tidspunkt"],
        )

        forslag.append({
            "person": p,
            "aktivitet": beste_akt,
            "overlapp": overlapp,
            "felles_tags": felles_tags,
            "dager_siden": dager,
            "score": score,
            "melding": melding,
            "dato_tekst": dato_tekst,
        })

    forslag.sort(key=lambda f: (f["score"], f["overlapp"]), reverse=True)
    return forslag[:maks]


@app.route("/forslag")
def forslag():
    conn = db.get_db()
    ledige = conn.execute(
        """SELECT * FROM ledige_dager
           WHERE status = 'ledig'
           ORDER BY dato ASC, tidspunkt ASC"""
    ).fetchall()
    personer_rader = conn.execute("SELECT * FROM personer").fetchall()
    aktiviteter_rader = conn.execute("SELECT * FROM aktivitetsforslag").fetchall()

    valgt_id = request.args.get("dag_id", type=int)
    valgt_dag = None
    if valgt_id is not None:
        for d in ledige:
            if d["id"] == valgt_id:
                valgt_dag = d
                break
    elif ledige:
        valgt_dag = ledige[0]

    kort = []
    if valgt_dag is not None:
        kort = lag_forslag(valgt_dag, personer_rader, aktiviteter_rader)

    return render_template(
        "forslag.html",
        ledige=ledige,
        valgt_dag=valgt_dag,
        kort=kort,
        dato_formatert=_formater_dato,
        antall_personer=len(personer_rader),
        antall_aktiviteter=len(aktiviteter_rader),
    )


if __name__ == "__main__":
    # Lokal kjøring. HOST=0.0.0.0 lar andre enheter på samme WiFi nå appen;
    # ellers kun denne maskinen. PORT kan overstyres via miljøvariabel.
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    app.run(host=host, port=port, debug=True)
