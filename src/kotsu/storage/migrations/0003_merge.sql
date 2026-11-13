-- 0003: identity for merging databases from different devices (D39).
-- `uid` identifies the record on any device; `id` stays local. `alterado_em` (changed at) is
-- the stamp of the last change (hybrid clock: milliseconds-counter-replica), comparable as
-- text. Deleting an entry leaves a tombstone (`lapide`), so it does not come back on merge.

CREATE TABLE meta (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);

INSERT INTO meta (chave, valor) VALUES ('replica', lower(hex(randomblob(4))));
INSERT INTO meta (chave, valor) VALUES ('relogio', '0000000000000-0000-00000000');

ALTER TABLE conta ADD COLUMN uid TEXT;
ALTER TABLE conta ADD COLUMN alterado_em TEXT NOT NULL DEFAULT '0000000000000-0000-00000000';
UPDATE conta SET uid = lower(hex(randomblob(16)));
CREATE UNIQUE INDEX conta_uid ON conta (uid);

ALTER TABLE categoria ADD COLUMN uid TEXT;
ALTER TABLE categoria ADD COLUMN alterado_em TEXT NOT NULL DEFAULT '0000000000000-0000-00000000';
UPDATE categoria SET uid = lower(hex(randomblob(16)));
CREATE UNIQUE INDEX categoria_uid ON categoria (uid);

-- The series already has a universal identity (`grupo`); only the template stamp is missing.
ALTER TABLE recorrencia ADD COLUMN alterado_em TEXT NOT NULL DEFAULT '0000000000000-0000-00000000';

-- `gerado` (generated) = month created by the series and never touched: left out of the
-- check code, because each device generates future months up to where the person browsed.
ALTER TABLE lancamento ADD COLUMN uid TEXT;
ALTER TABLE lancamento ADD COLUMN alterado_em TEXT NOT NULL DEFAULT '0000000000000-0000-00000000';
ALTER TABLE lancamento ADD COLUMN gerado INTEGER NOT NULL DEFAULT 0 CHECK (gerado IN (0, 1));
UPDATE lancamento SET uid = lower(hex(randomblob(16)));
CREATE UNIQUE INDEX lancamento_uid ON lancamento (uid);

CREATE TABLE lapide (
    uid         TEXT PRIMARY KEY,
    excluido_em TEXT NOT NULL
);

-- Whoever inserts without a `uid` gets one: no record is left without identity.
CREATE TRIGGER conta_uid_novo AFTER INSERT ON conta WHEN NEW.uid IS NULL
BEGIN
    UPDATE conta SET uid = lower(hex(randomblob(16))) WHERE id = NEW.id;
END;

CREATE TRIGGER categoria_uid_novo AFTER INSERT ON categoria WHEN NEW.uid IS NULL
BEGIN
    UPDATE categoria SET uid = lower(hex(randomblob(16))) WHERE id = NEW.id;
END;

CREATE TRIGGER lancamento_uid_novo AFTER INSERT ON lancamento WHEN NEW.uid IS NULL
BEGIN
    UPDATE lancamento SET uid = lower(hex(randomblob(16))) WHERE id = NEW.id;
END;
