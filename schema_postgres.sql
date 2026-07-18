-- Datamodell for "Hold kontakten" (PostgreSQL-variant, brukes ved hosting).
-- Samme felter som schema.sql, men med SERIAL i stedet for AUTOINCREMENT.

CREATE TABLE IF NOT EXISTS personer (
    id                 SERIAL PRIMARY KEY,
    navn               TEXT NOT NULL,
    relasjon           TEXT NOT NULL CHECK (relasjon IN ('venn', 'familie', 'kollega')),
    interesser         TEXT DEFAULT '',
    siste_kontakt_dato TEXT,
    notater            TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS ledige_dager (
    id        SERIAL PRIMARY KEY,
    dato      TEXT NOT NULL,
    tidspunkt TEXT NOT NULL CHECK (tidspunkt IN ('dag', 'kveld', 'helg')),
    status    TEXT NOT NULL DEFAULT 'ledig' CHECK (status IN ('ledig', 'opptatt'))
);

CREATE TABLE IF NOT EXISTS aktivitetsforslag (
    id                SERIAL PRIMARY KEY,
    tittel            TEXT NOT NULL,
    beskrivelse       TEXT DEFAULT '',
    passer_interesser TEXT DEFAULT '',
    meldingsmal       TEXT DEFAULT ''
);
