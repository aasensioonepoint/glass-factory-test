-- =============================================================================
-- Graffard Racing — conceptual data model (MCD) V0, as a PostgreSQL schema
-- -----------------------------------------------------------------------------
-- Source : "GRAFFARD RACING – Processus et MCD V0" (PowerPoint),
--          data dictionary slides 12–20, relationship slides 23–28.
-- Scope  : 49 tables, 287 columns, 80 foreign keys — exactly the V0 proposal.
--
-- READ THIS FIRST
--   * This is a faithful transcription of a PROPOSED model that has NOT been
--     validated by the client. It is your starting point, not your target.
--   * The MCD lists field names only. Data types, NOT NULL and UNIQUE
--     constraints below are indicative choices made for this file:
--       field?  in the MCD  -> nullable foreign key
--       field!  in the MCD  -> unique foreign key (one-to-one)
--   * Known gaps against the functional specification are left AS IS on
--     purpose (see schema/DATA_MODEL.md § "Known gaps"). Arbitrating and
--     justifying them is part of the Level 2 challenge.
--   * Identifiers are kept in French, as in the source documents.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. Reference data (3 tables)
-- -----------------------------------------------------------------------------

CREATE TABLE cheval (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sire            text UNIQUE,
    nom             text NOT NULL,
    sexe            text,
    date_naissance  date,
    statut          text
);

CREATE TABLE acteur (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nom             text NOT NULL,
    type_acteur     text,          -- person or organisation
    roles_metier    text[],        -- business roles; distinct from application roles
    email           text,
    telephone       text,
    adresse         text
);

CREATE TABLE ecurie (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nom             text NOT NULL,
    adresse         text,
    statut          text
);

-- -----------------------------------------------------------------------------
-- 2. Horse population and location (4 tables)
-- -----------------------------------------------------------------------------

CREATE TABLE lieu (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ecurie_id       bigint NOT NULL REFERENCES ecurie (id),
    lieu_parent_id  bigint REFERENCES lieu (id),
    libelle         text NOT NULL,
    type_lieu       text,          -- site, yard (cour), building, box
    capacite        integer
);

CREATE TABLE sejour (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cheval_id       bigint NOT NULL REFERENCES cheval (id),
    lieu_id         bigint NOT NULL REFERENCES lieu (id),
    date_debut      date NOT NULL,
    date_fin        date,
    motif           text
);

CREATE TABLE mouvement (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cheval_id          bigint NOT NULL REFERENCES cheval (id),
    lieu_depart_id     bigint REFERENCES lieu (id),
    lieu_arrivee_id    bigint REFERENCES lieu (id),
    transporteur_id    bigint REFERENCES acteur (id),
    date_heure         timestamptz NOT NULL,
    sens               text,       -- arrival, departure, transfer
    provenance_texte   text,
    destination_texte  text,
    reference_bon      text
);

CREATE TABLE detention (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cheval_id        bigint NOT NULL REFERENCES cheval (id),
    proprietaire_id  bigint NOT NULL REFERENCES acteur (id),
    date_debut       date NOT NULL,
    date_fin         date,
    quote_part       numeric(5, 2)  -- ownership share for co-ownership
);

-- -----------------------------------------------------------------------------
-- 3. Health and compliance (8 tables)
-- -----------------------------------------------------------------------------

CREATE TABLE produit (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nom        text NOT NULL,
    categorie  text,               -- medicine, vaccine, other
    unite      text
);

-- Shared by care, examinations, vaccinations and farriery (type_acte).
CREATE TABLE acte_sante (
    id                    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cheval_id             bigint NOT NULL REFERENCES cheval (id),
    intervenant_id        bigint NOT NULL REFERENCES acteur (id),
    certificateur_id      bigint REFERENCES acteur (id),
    date_heure            timestamptz NOT NULL,
    type_acte             text NOT NULL,   -- care, examination, vaccination, ferrure...
    soin                  text,
    delai_retrait_jours   integer,         -- withdrawal period, in days
    debut_retrait         date,
    fin_retrait           date,
    statut_certification  text,
    date_certification    date,
    type_ferrure          text,
    observations          text
);

CREATE TABLE prescription (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cheval_id          bigint NOT NULL REFERENCES cheval (id),
    prescripteur_id    bigint NOT NULL REFERENCES acteur (id),
    produit_id         bigint NOT NULL REFERENCES produit (id),
    ordonnance_id      bigint,          -- FK to document, added after section 7
    date_prescription  date NOT NULL,
    posologie          text,
    duree_jours        integer
);

CREATE TABLE examen (
    id                    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    acte_id               bigint NOT NULL UNIQUE REFERENCES acte_sante (id),
    membre                text,
    score_boiterie        numeric(3, 1),  -- lameness score
    sensibilite           text,
    protocole_recommande  text
);

CREATE TABLE vaccination (
    id                    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    acte_id               bigint NOT NULL UNIQUE REFERENCES acte_sante (id),
    vaccin_id             bigint NOT NULL REFERENCES produit (id),
    date_prochain_rappel  date
);

CREATE TABLE administration (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    acte_id     bigint NOT NULL REFERENCES acte_sante (id),
    produit_id  bigint NOT NULL REFERENCES produit (id),
    date_heure  timestamptz NOT NULL,
    dose        numeric(10, 3),
    unite       text,
    voie        text                 -- route of administration
);

CREATE TABLE acte_prescription (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    acte_id          bigint NOT NULL REFERENCES acte_sante (id),
    prescription_id  bigint NOT NULL REFERENCES prescription (id)
);

CREATE TABLE acte_document (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    acte_id      bigint NOT NULL REFERENCES acte_sante (id),
    document_id  bigint NOT NULL       -- FK to document, added after section 7
);

-- -----------------------------------------------------------------------------
-- 4. Field work and feeding (4 tables)
-- -----------------------------------------------------------------------------

-- A LOT is a training rotation, not a place. The yard is the LIEU.
CREATE TABLE lot (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lieu_id         bigint NOT NULL REFERENCES lieu (id),
    responsable_id  bigint NOT NULL REFERENCES acteur (id),
    date            date NOT NULL,
    heure           time,  -- KNOWN GAP: the specification states a lot has NO time (§7, §12)
    libelle         text
);

CREATE TABLE seance (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cheval_id        bigint NOT NULL REFERENCES cheval (id),
    lot_id           bigint NOT NULL REFERENCES lot (id),
    exercice         text,
    travail_prevu    text,           -- planned work
    travail_realise  text,           -- work actually done
    commentaire      text
);

CREATE TABLE affectation (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    seance_id   bigint NOT NULL REFERENCES seance (id),
    acteur_id   bigint NOT NULL REFERENCES acteur (id),
    date_heure  timestamptz,
    fonction    text,                -- e.g. rider in charge of the horse
    consigne    text
);

CREATE TABLE ration (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cheval_id       bigint NOT NULL REFERENCES cheval (id),
    auteur_id       bigint NOT NULL REFERENCES acteur (id),
    date_heure      timestamptz NOT NULL,
    repas           text,
    part_consommee  text,            -- share of the meal eaten
    remarque        text
);

-- -----------------------------------------------------------------------------
-- 5. Races and travel (6 tables)
-- -----------------------------------------------------------------------------

-- A COURSE is a race. Not to be confused with a yard ("cour"), which is a LIEU.
CREATE TABLE course (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    date_heure  timestamptz NOT NULL,
    nom         text NOT NULL,
    edition     text,
    hippodrome  text,
    pays        text,
    distance    integer               -- metres
);

CREATE TABLE engagement (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cheval_id          bigint NOT NULL REFERENCES cheval (id),
    course_id          bigint NOT NULL REFERENCES course (id),
    jockey_id          bigint REFERENCES acteur (id),
    date_engagement    date NOT NULL,
    statut             text,
    cout               numeric(10, 2),
    resultat_controle  text,          -- outcome of the pre-race check
    date_controle      timestamptz
);

CREATE TABLE resultat (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    engagement_id  bigint NOT NULL UNIQUE REFERENCES engagement (id),
    rang           integer,
    temps          interval,
    commentaire    text
);

CREATE TABLE transport (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    transporteur_id  bigint NOT NULL REFERENCES acteur (id),
    lieu_depart_id   bigint REFERENCES lieu (id),
    lieu_arrivee_id  bigint REFERENCES lieu (id),
    date_depart      timestamptz,
    date_arrivee     timestamptz,
    statut           text,
    consignes        text
);

CREATE TABLE prise_en_charge (
    id                    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cheval_id             bigint NOT NULL REFERENCES cheval (id),
    transport_id          bigint NOT NULL REFERENCES transport (id),
    lieu_prise_id         bigint REFERENCES lieu (id),
    lieu_depose_id        bigint REFERENCES lieu (id),
    heure_prise_en_charge timestamptz,
    heure_depose          timestamptz
);

CREATE TABLE engagement_transport (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    engagement_id  bigint NOT NULL REFERENCES engagement (id),
    transport_id   bigint NOT NULL REFERENCES transport (id)
);

-- -----------------------------------------------------------------------------
-- 6. Human resources (5 tables)
-- -----------------------------------------------------------------------------

-- Only salaried staff get an EMPLOYE record; external providers stay ACTEUR.
CREATE TABLE employe (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    acteur_id    bigint NOT NULL UNIQUE REFERENCES acteur (id),
    matricule    text UNIQUE,
    poste        text,
    contrat      text,
    date_entree  date,
    date_sortie  date
);

CREATE TABLE creneau (
    id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lieu_id   bigint REFERENCES lieu (id),
    debut     timestamptz NOT NULL,
    fin       timestamptz NOT NULL,
    activite  text
);

CREATE TABLE employe_creneau (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    employe_id  bigint NOT NULL REFERENCES employe (id),
    creneau_id  bigint NOT NULL REFERENCES creneau (id)
);

CREATE TABLE pointage (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    employe_id        bigint NOT NULL REFERENCES employe (id),
    correcteur_id     bigint REFERENCES acteur (id),
    heure_entree      timestamptz NOT NULL,
    heure_sortie      timestamptz,
    duree             interval,
    motif_correction  text
);

CREATE TABLE absence (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    employe_id       bigint NOT NULL REFERENCES employe (id),
    validateur_id    bigint REFERENCES acteur (id),
    debut            date NOT NULL,
    fin              date NOT NULL,
    type_absence     text,
    statut           text,
    date_validation  date
);

-- -----------------------------------------------------------------------------
-- 7. History and communication (5 tables)
-- -----------------------------------------------------------------------------

CREATE TABLE evenement (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cheval_id          bigint NOT NULL REFERENCES cheval (id),
    auteur_id          bigint NOT NULL REFERENCES acteur (id),
    date_heure         timestamptz NOT NULL,
    type_evenement     text NOT NULL,
    texte              text,
    source             text,           -- e.g. typed, dictation, import
    statut_validation  text            -- e.g. draft, validated
);

CREATE TABLE document (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    type_document  text NOT NULL,      -- prescription, certificate, photo, audio...
    date_document  date,
    uri            text NOT NULL,      -- storage address
    version        integer
);

CREATE TABLE evenement_document (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    evenement_id  bigint NOT NULL REFERENCES evenement (id),
    document_id   bigint NOT NULL REFERENCES document (id)
);

CREATE TABLE notification (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    evenement_id   bigint REFERENCES evenement (id),
    date_creation  timestamptz NOT NULL,
    objet          text NOT NULL,
    priorite       text
);

CREATE TABLE reception (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    notification_id  bigint NOT NULL REFERENCES notification (id),
    destinataire_id  bigint NOT NULL REFERENCES acteur (id),
    date_envoi       timestamptz,
    date_lecture     timestamptz,
    statut           text
);

-- Health tables that point to DOCUMENT (declared above it).
ALTER TABLE prescription
    ADD FOREIGN KEY (ordonnance_id) REFERENCES document (id);
ALTER TABLE acte_document
    ADD FOREIGN KEY (document_id) REFERENCES document (id);

-- -----------------------------------------------------------------------------
-- 8. Billing (6 tables) — proposed extension, scope still to be arbitrated
-- -----------------------------------------------------------------------------

CREATE TABLE facture (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ecurie_id        bigint NOT NULL REFERENCES ecurie (id),
    destinataire_id  bigint NOT NULL REFERENCES acteur (id),
    numero           text NOT NULL UNIQUE,
    date_emission    date NOT NULL,
    date_echeance    date,
    statut           text
);

CREATE TABLE ligne_facture (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    facture_id     bigint NOT NULL REFERENCES facture (id),
    libelle        text NOT NULL,
    quantite       numeric(10, 2) NOT NULL,
    prix_unitaire  numeric(10, 2) NOT NULL,
    taux_taxe      numeric(5, 2)
);

CREATE TABLE prestation (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cheval_id        bigint NOT NULL REFERENCES cheval (id),
    justificatif_id  bigint REFERENCES document (id),
    date             date NOT NULL,
    type_prestation  text NOT NULL,
    montant          numeric(10, 2)
);

CREATE TABLE imputation (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ligne_id          bigint NOT NULL REFERENCES ligne_facture (id),
    prestation_id     bigint NOT NULL REFERENCES prestation (id),
    quantite_imputee  numeric(10, 2),
    montant_impute    numeric(10, 2)
);

CREATE TABLE reglement (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    date       date NOT NULL,
    montant    numeric(10, 2) NOT NULL,
    mode       text,
    reference  text
);

CREATE TABLE affectation_paiement (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    facture_id       bigint NOT NULL REFERENCES facture (id),
    reglement_id     bigint NOT NULL REFERENCES reglement (id),
    montant_affecte  numeric(10, 2) NOT NULL
);

-- -----------------------------------------------------------------------------
-- 9. Access, interfaces and assistance (8 tables) — technical model, to frame
-- -----------------------------------------------------------------------------

-- An ACTEUR may exist without an account.
CREATE TABLE compte (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    acteur_id  bigint NOT NULL UNIQUE REFERENCES acteur (id),
    login      text NOT NULL UNIQUE,
    etat       text
);

-- Application role (rights profile), distinct from the actor's business role.
CREATE TABLE role (
    id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    libelle  text NOT NULL UNIQUE
);

CREATE TABLE habilitation (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    compte_id  bigint NOT NULL REFERENCES compte (id),
    role_id    bigint NOT NULL REFERENCES role (id),
    ecurie_id  bigint NOT NULL REFERENCES ecurie (id)
);

CREATE TABLE permission (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code       text NOT NULL UNIQUE,
    libelle    text,
    ressource  text NOT NULL,
    action     text NOT NULL           -- read, create, update
);

CREATE TABLE role_permission (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    role_id        bigint NOT NULL REFERENCES role (id),
    permission_id  bigint NOT NULL REFERENCES permission (id)
);

-- Trace of an import, export or exchange with an external system
-- (France Galop, Equitop, The Racing Manager...).
CREATE TABLE echange (
    id                           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    initiateur_id                bigint REFERENCES compte (id),
    source                       text NOT NULL,
    date_heure                   timestamptz NOT NULL,
    sens                         text,   -- inbound, outbound
    etat                         text,
    anomalies                    text,
    correspondances_identifiants jsonb   -- external <-> internal id mapping
);

CREATE TABLE requete_ia (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    compte_id   bigint NOT NULL REFERENCES compte (id),
    date_heure  timestamptz NOT NULL,
    question    text NOT NULL,
    reponse     text,
    contexte    jsonb
);

CREATE TABLE article_aide (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    auteur_id  bigint NOT NULL REFERENCES compte (id),
    titre      text NOT NULL,
    theme      text,
    contenu    text,
    version    integer
);
