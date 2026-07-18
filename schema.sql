-- Datamodell for "Hold kontakten"

CREATE TABLE IF NOT EXISTS personer (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    navn              TEXT NOT NULL,
    relasjon          TEXT NOT NULL CHECK (relasjon IN ('venn', 'familie', 'kollega')),
    interesser        TEXT DEFAULT '',      -- kommaseparerte tags, f.eks. "fotball, matlaging, jakt"
    siste_kontakt_dato TEXT,                -- ISO-dato (YYYY-MM-DD), kan være NULL
    notater           TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS ledige_dager (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    dato      TEXT NOT NULL,               -- ISO-dato (YYYY-MM-DD)
    tidspunkt TEXT NOT NULL CHECK (tidspunkt IN ('dag', 'kveld', 'helg')),
    status    TEXT NOT NULL DEFAULT 'ledig' CHECK (status IN ('ledig', 'opptatt'))
);

CREATE TABLE IF NOT EXISTS aktivitetsforslag (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    tittel            TEXT NOT NULL,
    beskrivelse       TEXT DEFAULT '',
    passer_interesser TEXT DEFAULT '',      -- kommaseparerte tags
    meldingsmal       TEXT DEFAULT ''       -- tekst med plassholder {navn}
);
