-- 0003: identidade para mesclar bancos de aparelhos diferentes (D39).
-- `uid` identifica o registro em qualquer aparelho; `id` continua local. `alterado_em` é o
-- carimbo da última alteração (relógio híbrido: milissegundos-contador-réplica), comparável
-- como texto. Exclusão de lançamento deixa uma lápide, para ele não voltar na mesclagem.

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

-- A série já tem identidade universal (`grupo`); falta só o carimbo do modelo.
ALTER TABLE recorrencia ADD COLUMN alterado_em TEXT NOT NULL DEFAULT '0000000000000-0000-00000000';

-- `gerado` = mês criado pela série e nunca mexido: fica fora do código de conferência,
-- porque cada aparelho gera meses futuros até onde a pessoa navegou.
ALTER TABLE lancamento ADD COLUMN uid TEXT;
ALTER TABLE lancamento ADD COLUMN alterado_em TEXT NOT NULL DEFAULT '0000000000000-0000-00000000';
ALTER TABLE lancamento ADD COLUMN gerado INTEGER NOT NULL DEFAULT 0 CHECK (gerado IN (0, 1));
UPDATE lancamento SET uid = lower(hex(randomblob(16)));
CREATE UNIQUE INDEX lancamento_uid ON lancamento (uid);

CREATE TABLE lapide (
    uid         TEXT PRIMARY KEY,
    excluido_em TEXT NOT NULL
);

-- Quem insere sem `uid` ganha um: nenhum registro fica sem identidade.
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
