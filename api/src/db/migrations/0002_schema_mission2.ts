/**
 * Migration 0002 — arbitrations D5, D6, D8, D9 and Q1 (docs/mission2/DECISIONS.md).
 * Each change is explained, one line per arbitration, in schema/DATA_MODEL.md
 * § "Migration 0002". Inline SQL, run in one transaction by migrate().
 * Adds 5 tables to public: restriction, mesure, regime_special, audit, commande_sync.
 */
const sql = `
-- D9: one shared record status; "en retard" is computed, never stored.
CREATE TYPE statut_enregistrement AS ENUM ('brouillon', 'valide', 'publie', 'realise', 'annule', 'corrige');

-- D5: a lot has no time; identified by number (libelle), yard (lieu_id) and programme date.
ALTER TABLE lot DROP COLUMN heure;
ALTER TABLE lot ALTER COLUMN libelle SET NOT NULL;
ALTER TABLE lot ADD COLUMN ordre_passage integer NOT NULL CHECK (ordre_passage > 0);
ALTER TABLE lot ADD CONSTRAINT lot_numero_cour_date_key UNIQUE (libelle, lieu_id, date);

-- Q1 (pilot): withdrawal period of the product; NULL = unknown period.
-- acte_sante.delai_retrait_jours stays the copy frozen when the act is recorded.
ALTER TABLE produit ADD COLUMN delai_retrait_jours integer CHECK (delai_retrait_jours >= 0);

-- D8 + H1: common columns on the scope-A tables only.
-- ration already carries auteur_id (NOT NULL) in the MCD.
ALTER TABLE ration
  ADD COLUMN date_reelle timestamptz,
  ADD COLUMN date_reception timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN source text,
  ADD COLUMN statut statut_enregistrement NOT NULL DEFAULT 'brouillon';

ALTER TABLE acte_sante
  ADD COLUMN auteur_id bigint REFERENCES acteur (id),
  ADD COLUMN date_reelle timestamptz,
  ADD COLUMN date_reception timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN source text,
  ADD COLUMN statut statut_enregistrement NOT NULL DEFAULT 'brouillon';

ALTER TABLE administration
  ADD COLUMN auteur_id bigint REFERENCES acteur (id),
  ADD COLUMN date_reelle timestamptz,
  ADD COLUMN date_reception timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN source text,
  ADD COLUMN statut statut_enregistrement NOT NULL DEFAULT 'brouillon';

-- engagement.statut (text) is the official status: kept, renamed, never converted.
ALTER TABLE engagement RENAME COLUMN statut TO statut_officiel;
ALTER TABLE engagement
  ADD COLUMN auteur_id bigint REFERENCES acteur (id),
  ADD COLUMN date_reelle timestamptz,
  ADD COLUMN date_reception timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN source text,
  ADD COLUMN statut statut_enregistrement NOT NULL DEFAULT 'brouillon';

-- D6: a restriction references its source and validator; it is lifted only
-- explicitly, by someone, at a time, with a reason. A past fin_prevue lifts nothing.
CREATE TABLE restriction (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cheval_id       bigint NOT NULL REFERENCES cheval (id),
    source          text NOT NULL CHECK (source IN ('administration', 'examen', 'manuel')),
    source_id       bigint,
    debut           date NOT NULL,
    fin_prevue      date,
    statut          text NOT NULL DEFAULT 'active' CHECK (statut IN ('active', 'levee')),
    validateur_id   bigint REFERENCES acteur (id),
    leve_par_id     bigint REFERENCES acteur (id),
    leve_le         timestamptz,
    motif_levee     text,
    auteur_id       bigint REFERENCES acteur (id),
    date_reelle     timestamptz,
    date_reception  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT restriction_source_referencee CHECK (source = 'manuel' OR source_id IS NOT NULL),
    CONSTRAINT restriction_levee_tracee CHECK (
        statut <> 'levee'
        OR (leve_par_id IS NOT NULL AND leve_le IS NOT NULL
            AND motif_levee IS NOT NULL AND btrim(motif_levee) <> '')
    )
);
CREATE INDEX restriction_active_cheval_idx ON restriction (cheval_id) WHERE statut = 'active';

CREATE TABLE mesure (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cheval_id       bigint NOT NULL REFERENCES cheval (id),
    type            text NOT NULL CHECK (type IN ('temperature', 'poids')),
    valeur          numeric(8, 2) NOT NULL,
    unite           text NOT NULL,
    auteur_id       bigint NOT NULL REFERENCES acteur (id),
    date_reelle     timestamptz NOT NULL,
    date_reception  timestamptz NOT NULL DEFAULT now(),
    source          text,
    statut          statut_enregistrement NOT NULL DEFAULT 'brouillon'
);

CREATE TABLE regime_special (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cheval_id       bigint NOT NULL REFERENCES cheval (id),
    description     text NOT NULL,
    debut           date NOT NULL,
    fin             date,
    valide_par_id   bigint REFERENCES acteur (id),
    auteur_id       bigint REFERENCES acteur (id),
    date_reelle     timestamptz,
    date_reception  timestamptz NOT NULL DEFAULT now(),
    source          text,
    statut          statut_enregistrement NOT NULL DEFAULT 'brouillon',
    CONSTRAINT regime_special_periode CHECK (fin IS NULL OR fin >= debut)
);

-- D8: a correction keeps before, after and reason; the trail is append-only.
CREATE TABLE audit (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    objet       text NOT NULL,
    objet_id    bigint NOT NULL,
    avant       jsonb,
    apres       jsonb,
    motif       text NOT NULL CHECK (btrim(motif) <> ''),
    auteur_id   bigint NOT NULL REFERENCES acteur (id),
    horodatage  timestamptz NOT NULL DEFAULT now()
);

CREATE FUNCTION audit_immuable() RETURNS trigger LANGUAGE plpgsql AS $fn$
BEGIN
    RAISE EXCEPTION 'audit est en ajout seul : % refusé', TG_OP;
END;
$fn$;
CREATE TRIGGER audit_ajout_seul BEFORE UPDATE OR DELETE ON audit
    FOR EACH ROW EXECUTE FUNCTION audit_immuable();

-- D8: idempotency key generated by the device; a replayed command finds its row.
CREATE TABLE commande_sync (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_commande  text NOT NULL UNIQUE,
    statut       text NOT NULL DEFAULT 'recue' CHECK (statut IN ('recue', 'appliquee', 'rejetee')),
    accuse       jsonb,
    erreur       text,
    recu_le      timestamptz NOT NULL DEFAULT now()
);
`;

export const migration0002 = { id: '0002_schema_mission2', sql };
