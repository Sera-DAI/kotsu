-- 0004: English names for every table, column and value.
-- Tables are rebuilt (SQLite cannot change a CHECK constraint in place) and the data is
-- copied with the same ids, uids and stamps, so merging with other devices keeps working.
-- `tipo` values 'receita'/'despesa' become kind 'income'/'expense'.

CREATE TABLE account (
    id         INTEGER PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE COLLATE NOCASE CHECK (length(trim(name)) > 0),
    color      TEXT NOT NULL,
    uid        TEXT,
    changed_at TEXT NOT NULL DEFAULT '0000000000000-0000-00000000'
);

CREATE TABLE category (
    id         INTEGER PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE COLLATE NOCASE CHECK (length(trim(name)) > 0),
    recurring  INTEGER NOT NULL DEFAULT 0 CHECK (recurring IN (0, 1)),
    uid        TEXT,
    changed_at TEXT NOT NULL DEFAULT '0000000000000-0000-00000000'
);

CREATE TABLE recurrence (
    group_id        TEXT    PRIMARY KEY,
    day             INTEGER NOT NULL CHECK (day BETWEEN 1 AND 31),
    description     TEXT    NOT NULL,
    amount          INTEGER NOT NULL CHECK (typeof(amount) = 'integer' AND amount > 0),
    kind            TEXT    NOT NULL CHECK (kind IN ('income', 'expense')),
    account_id      INTEGER NOT NULL REFERENCES account (id) ON DELETE RESTRICT,
    category_id     INTEGER REFERENCES category (id) ON DELETE RESTRICT,
    generated_until TEXT    NOT NULL CHECK (date(generated_until) IS generated_until),
    ended           INTEGER NOT NULL DEFAULT 0 CHECK (ended IN (0, 1)),
    changed_at      TEXT    NOT NULL DEFAULT '0000000000000-0000-00000000'
);

CREATE TABLE entry (
    id                 INTEGER PRIMARY KEY,
    date               TEXT    NOT NULL CHECK (date(date) IS date),
    description        TEXT    NOT NULL,
    amount             INTEGER NOT NULL CHECK (typeof(amount) = 'integer' AND amount > 0),
    kind               TEXT    NOT NULL CHECK (kind IN ('income', 'expense')),
    account_id         INTEGER NOT NULL REFERENCES account (id) ON DELETE RESTRICT,
    category_id        INTEGER REFERENCES category (id) ON DELETE RESTRICT,
    installment_group  TEXT,
    installment_number INTEGER,
    installment_total  INTEGER,
    recurrence_group   TEXT REFERENCES recurrence (group_id),
    uid                TEXT,
    changed_at         TEXT    NOT NULL DEFAULT '0000000000000-0000-00000000',
    generated          INTEGER NOT NULL DEFAULT 0 CHECK (generated IN (0, 1)),
    CHECK (
        (installment_group IS NULL AND installment_number IS NULL AND installment_total IS NULL)
        OR (installment_group IS NOT NULL
            AND installment_number BETWEEN 1 AND installment_total)
    )
);

CREATE TABLE tombstone (
    uid        TEXT PRIMARY KEY,
    deleted_at TEXT NOT NULL
);

CREATE TABLE meta_new (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

INSERT INTO account (id, name, color, uid, changed_at)
    SELECT id, nome, cor, uid, alterado_em FROM conta;

INSERT INTO category (id, name, recurring, uid, changed_at)
    SELECT id, nome, recorrente, uid, alterado_em FROM categoria;

INSERT INTO recurrence (group_id, day, description, amount, kind, account_id, category_id,
                        generated_until, ended, changed_at)
    SELECT grupo, dia, descricao, valor,
           CASE tipo WHEN 'receita' THEN 'income' ELSE 'expense' END,
           conta_id, categoria_id, gerada_ate, encerrada, alterado_em
    FROM recorrencia;

INSERT INTO entry (id, date, description, amount, kind, account_id, category_id,
                   installment_group, installment_number, installment_total,
                   recurrence_group, uid, changed_at, generated)
    SELECT id, data, descricao, valor,
           CASE tipo WHEN 'receita' THEN 'income' ELSE 'expense' END,
           conta_id, categoria_id, grupo_parcela, parcela_numero, parcela_total,
           grupo_recorrencia, uid, alterado_em, gerado
    FROM lancamento;

INSERT INTO tombstone (uid, deleted_at) SELECT uid, excluido_em FROM lapide;

INSERT INTO meta_new (key, value)
    SELECT CASE chave WHEN 'relogio' THEN 'clock' ELSE chave END, valor FROM meta;

DROP TABLE lancamento;
DROP TABLE recorrencia;
DROP TABLE categoria;
DROP TABLE conta;
DROP TABLE lapide;
DROP TABLE meta;
ALTER TABLE meta_new RENAME TO meta;

CREATE INDEX entry_date ON entry (date, id);
CREATE INDEX entry_installment ON entry (installment_group) WHERE installment_group IS NOT NULL;
CREATE INDEX entry_recurrence ON entry (recurrence_group, date)
    WHERE recurrence_group IS NOT NULL;
CREATE UNIQUE INDEX account_uid ON account (uid);
CREATE UNIQUE INDEX category_uid ON category (uid);
CREATE UNIQUE INDEX entry_uid ON entry (uid);

-- Whoever inserts without a `uid` gets one: no record is left without identity.
CREATE TRIGGER account_new_uid AFTER INSERT ON account WHEN NEW.uid IS NULL
BEGIN
    UPDATE account SET uid = lower(hex(randomblob(16))) WHERE id = NEW.id;
END;

CREATE TRIGGER category_new_uid AFTER INSERT ON category WHEN NEW.uid IS NULL
BEGIN
    UPDATE category SET uid = lower(hex(randomblob(16))) WHERE id = NEW.id;
END;

CREATE TRIGGER entry_new_uid AFTER INSERT ON entry WHEN NEW.uid IS NULL
BEGIN
    UPDATE entry SET uid = lower(hex(randomblob(16))) WHERE id = NEW.id;
END;
