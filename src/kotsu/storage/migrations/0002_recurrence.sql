-- 0002: recurring categories (D36). An entry in a recurring category repeats every month,
-- endlessly, until the person ends it. Each series stores the template and up to which
-- month it has been generated.

ALTER TABLE categoria ADD COLUMN recorrente INTEGER NOT NULL DEFAULT 0 CHECK (recorrente IN (0, 1));

CREATE TABLE recorrencia (
    grupo        TEXT    PRIMARY KEY,
    dia          INTEGER NOT NULL CHECK (dia BETWEEN 1 AND 31),
    descricao    TEXT    NOT NULL,
    valor        INTEGER NOT NULL CHECK (typeof(valor) = 'integer' AND valor > 0),
    tipo         TEXT    NOT NULL CHECK (tipo IN ('receita', 'despesa')),
    conta_id     INTEGER NOT NULL REFERENCES conta (id) ON DELETE RESTRICT,
    categoria_id INTEGER REFERENCES categoria (id) ON DELETE RESTRICT,
    gerada_ate   TEXT    NOT NULL CHECK (date(gerada_ate) IS gerada_ate),
    encerrada    INTEGER NOT NULL DEFAULT 0 CHECK (encerrada IN (0, 1))
);

ALTER TABLE lancamento ADD COLUMN grupo_recorrencia TEXT REFERENCES recorrencia (grupo);

CREATE INDEX lancamento_recorrencia ON lancamento (grupo_recorrencia, data)
    WHERE grupo_recorrencia IS NOT NULL;
