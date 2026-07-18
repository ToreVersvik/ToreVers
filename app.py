"""Hold kontakten – lokal Flask-app for å huske å ta kontakt med folk.

Fase 1:
  - Dashboard: personer sortert etter lengst tid siden siste kontakt
  - CRUD for personer
  - CRUD for ledige dager
"""
from datetime import date, datetime

from flask import Flask, flash, redirect, render_template, request, url_for

import db

app = Flask(__name__)
app.config["SECRET_KEY"] = "hold-kontakten-lokal-dev"  # kun for lokal flash-melding

db.init_app(app)

RELASJONER = ["venn", "familie", "kollega"]
TIDSPUNKTER = ["dag", "kveld", "helg"]
STATUSER = ["ledig", "opptatt"]


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


if __name__ == "__main__":
    db.init_db()
    app.run(host="127.0.0.1", port=5000, debug=True)
