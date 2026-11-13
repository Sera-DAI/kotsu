-- 0001: initial v1 schema.
-- Table and column names are in Portuguese here; migration 0004 renames them to English.
-- Money in positive integer cents; the sign comes from `tipo` (kind).
-- ISO calendar dates (YYYY-MM-DD), no time zone. Totals are never stored.
-- Every entry has an account (D21); the category is optional.

CREATE TABLE conta (
    id   INTEGER PRIMARY KEY,
    nome TEXT NOT NULL UNIQUE COLLATE NOCASE CHECK (length(trim(nome)) > 0),
    cor  TEXT NOT NULL
);

CREATE TABLE categoria (
    id   INTEGER PRIMARY KEY,
    nome TEXT NOT NULL UNIQUE COLLATE NOCASE CHECK (length(trim(nome)) > 0)
);

CREATE TABLE lancamento (
    id             INTEGER PRIMARY KEY,
    data           TEXT    NOT NULL CHECK (date(data) IS data),
    descricao      TEXT    NOT NULL,
    valor          INTEGER NOT NULL CHECK (typeof(valor) = 'integer' AND valor > 0),
    tipo           TEXT    NOT NULL CHECK (tipo IN ('receita', 'despesa')),
    conta_id       INTEGER NOT NULL REFERENCES conta (id) ON DELETE RESTRICT,
    categoria_id   INTEGER REFERENCES categoria (id) ON DELETE RESTRICT,
    grupo_parcela  TEXT,
    parcela_numero INTEGER,
    parcela_total  INTEGER,
    CHECK (
        (grupo_parcela IS NULL AND parcela_numero IS NULL AND parcela_total IS NULL)
        OR (grupo_parcela IS NOT NULL AND parcela_numero BETWEEN 1 AND parcela_total)
    )
);

CREATE INDEX lancamento_data ON lancamento (data, id);
CREATE INDEX lancamento_grupo ON lancamento (grupo_parcela) WHERE grupo_parcela IS NOT NULL;
