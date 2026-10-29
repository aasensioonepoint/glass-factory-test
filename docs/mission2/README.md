# Graffard Racing Hackathon — Level 2 · "Build"

> **From the specification to the stable yard. Your stack, your architecture, a real racing stable.**

Graffard Racing is an international flat-racing stable based in Chantilly, France. Its motto: *Excellence. Precision. Passion.* Every morning from 5:15 am, many people feed, train, treat and shoe high-value horses, and today they coordinate it all through wall boards, paper diaries, WhatsApp and spreadsheets. Your mission: turn that scattered information into one reliable digital **360° horse record**, built for people standing in a yard with one hand free.

---

## Contents

1. [What is in this repository](#1-what-is-in-this-repository)
2. [The case](#2-the-case)
3. [Level 2 at a glance](#3-level-2-at-a-glance)
4. [The six core challenges (A–F)](#4-the-six-core-challenges-af)
5. [Non-negotiable design principles](#5-non-negotiable-design-principles)
6. [Visual identity](#6-visual-identity)
7. [The analysis challenge: MCD vs specification](#7-the-analysis-challenge-mcd-vs-specification)
8. [Priority acceptance criteria (spec §12)](#8-priority-acceptance-criteria-spec-12)
9. [Level 1 vs Level 2](#9-level-1-vs-level-2)

---

## 1. What is in this repository

| Path | What it is |
|---|---|
| [`docs/GRAFFARD RACING-specification fonctionnelle V0.docx`](docs/GRAFFARD%20RACING-specification%20fonctionnelle%20V0.docx) | **Functional specification V0** (Word, in French). The target: what the application must do. **It prevails** over the other document when they disagree. |
| [`docs/GRAFFARD RACING Processus et MCD V0.pptx`](docs/GRAFFARD%20RACING%20Processus%20et%20MCD%20V0.pptx) | **Processes and data model V0** (PowerPoint, 41 slides, in French). How the stable works today, the risks, and the proposed data model. |
| [`schema/DATA_MODEL.md`](schema/DATA_MODEL.md) | The proposed data model in **English**: 49 tables by domain, every foreign key, a relationship diagram, and the known gaps. |
| [`schema/graffard_racing_mcd_v0.sql`](schema/graffard_racing_mcd_v0.sql) | The same model as a ready-to-load **PostgreSQL** script: 49 tables, 287 columns, 80 foreign keys. A starting point, not an imposed design. |

The source documents are in French. Business terms are kept in French in the schema (for example *cour* = yard, *lot* = training rotation, *engagement* = race entry); [`schema/DATA_MODEL.md`](schema/DATA_MODEL.md) translates each of them.

### Inside the functional specification

| § | Content |
|---|---|
| 1 | Purpose, ambition and expected results |
| 2 | Design principles and input budget |
| 3 | The 9 personas and their rights |
| 4 | 4 reference journeys: field day, lots, health-to-race, arrival-departure |
| 5–6 | Architecture of the 12 screens and 6-entry navigation |
| 7 | Cross-cutting business rules |
| 8 | Target data model in 8 domains, with cardinalities |
| 9 | UX/UI direction |
| 10 | Technical requirements: PWA, API, relational database, synchronisation, observability, performance under 2 s, accessibility, French/English |
| 10.1 | Integrations: France Galop, Equitop, The Racing Manager, messaging, sensors |
| 11 | AI requirements: dictation, prescription OCR, assistant, summary, anomaly detection |
| 12 | Priority acceptance criteria and pilot indicators |
| 13 | Roadmap P0, P1, P2 and decisions to take before development |

### Inside the processes and data model deck

| Block | Content |
|---|---|
| Flow map | 8 flows: operational day; lots and training; treatments and race entries (**critical risk**); farrier and health follow-up; weekly vaccination; arrivals and departures; administration and location; race entries and owner communication. Plus cross-cutting constraints. |
| Day timeline | From 5:15 am to 9:30 am, with the risks identified at each step. |
| Risks and solutions | Current situation, risk and target solution for each flow. **Priority 1: treatments → withdrawal periods → race entries.** |
| Action inventory | 65 actions, each with its current medium (wall board, paper, WhatsApp, Google Sheets, France Galop, Equitop…). |
| Tool decision plan | 16 tools: 3 kept, 7 integrated, 6 replaced. |
| Functional process | 5 steps (Reference, Plan, Perform, Check, Enter/Inform), across 8 roles. |
| Roles | 10 personas, a RACI covering 16 activities, and the links between personas and business objects. |
| Data dictionary | **49 tables, 287 fields, 80 foreign keys** in 9 domains. |
| Relational diagrams | An overview and one view per domain. |
| Target environments | Target system landscape around the "360° horse record" platform and connected systems. An AWS environment shown **for information only**: Amplify, AppSync, API Gateway, Lambda, Aurora PostgreSQL, S3, Step Functions, Cognito. |
| Project | A 12-week Glass Factory AI plan and the scope of the first release. |

---

## 2. The case

### The stable and its problem

The stable has three yards, one of them large with limited connectivity (saturated Starlink). Many people are involved: trainer, assistant trainer, yard managers, riders and grooms, vets, farrier, administration and HR, entries officer, jockeys, transporters and owners.

Today, information is spread across labelled wall boards, whiteboards, paper diaries, WhatsApp, e-mails, Google Sheets and people's memory. This leads to:

- anomalies that are forgotten;
- track feedback that is never captured;
- no structured history per horse;
- a lot of re-typing.

**The priority risk** is the lack of an automatic link between treatments, withdrawal periods and race entries. In practice, a horse can be entered in a race while it is still within a withdrawal period.

### The target

A responsive business web application (PWA) usable on mobile, tablet, desktop and a read-only TV screen. It is built around a **360° horse record**, the single operational source of truth.

The official systems stay in place and are connected:

- **France Galop**: race entries, vaccinations, horse register;
- **Equitop**: billing, livery, HR, location;
- **The Racing Manager**: owners' portal.

---

## 3. Level 2 at a glance

### From blank page to yard: build the 360° horse record

*Two documents, one schema, your stack. Go as far as you can on a real stable.*

You start from the scoping documents and the proposed data model, not from existing code. Choose your stack, design your architecture and build the application, core business first. Read the specification, arbitrate where the data model contradicts it, and model what is missing. Then build field-first mobile screens for feeding, training, care, farriery and horse condition, with supervised AI on top. The stake is real: no horse may be entered in a race while its veterinary status forbids it. Depth matters more than breadth: every tier you reach must respect the business rules end to end. All demo data must be fictitious.

| | |
|---|---|
| **Difficulty** | ★★★ (3/3) |
| **Recommended team** | Full-stack developers comfortable with data modelling, plus someone with a UX or product mindset to read the specification and keep the field constraints in mind. |

### Resources provided

- The functional specification V0 (Word, 13 October 2026).
- The processes and data model deck V0 (PowerPoint, 41 slides).
- The data model as an English dictionary and a PostgreSQL script (this repository).

### Mission

Design and build the application, **core business first** (challenges A to F below), then widen the scope.

### Suggested tiers

| Tier | Scope |
|---|---|
| **1** | Data model, reference data (horses, actors, places) and the horse record. |
| **2** | Business challenges A to E, with field-oriented mobile screens. |
| **3** | Voice remark and supervised AI: dictation, prescription OCR, daily summary. |
| **4** | The critical rule: treatment → withdrawal period → race entry blocked. Plus offline mode, synchronisation, role-based rights and audit. |
| **5** | Beyond: vaccination, movements, races, owner communication, simulated connectors to France Galop and Equitop, TV view. |

### Deliverables

- A working application you can demo.
- Justified architecture and stack choices.
- The data schema implemented, with its changes explained.
- The priority acceptance criteria of the specification (§12, see [section 8](#8-priority-acceptance-criteria-spec-12)) covered and demonstrated.
- Fictitious demo data only.

### Success criteria

- Functional depth (tier reached).
- Faithfulness to the business rules.
- Quality of the data modelling.
- Field user experience.
- Responsible use of AI.

### Bonus

Anything from **tier 5** you deliver on top of a solid core: vaccination calendar, movements, races, owner communication, simulated France Galop and Equitop connectors, read-only TV view.

---

## 4. The six core challenges (A–F)

The core business is the horse and its activities. Its scope is fixed. Each card below gives the problem today, the target, the key rules and the tables involved. Table names refer to [`schema/DATA_MODEL.md`](schema/DATA_MODEL.md).

### A. Feeding — *Nothing missed at 5:15 am*

> Confirm a normal feed in one tap; only what goes wrong needs typing.

**Today.** Mangers are checked by eye and nothing is recorded. Special diets are marked with an asterisk on the box board. An anomaly is reported orally to the assistant trainer, who decides whether to tell the trainer.

**Target.**
- An offline mobile checklist, per yard and per box, with special diets visible.
- Only a refusal, partial consumption or anomaly is entered; everything else is simply confirmed.
- A photo or a dictation can be attached.
- A time-stamped alert is sent automatically, and the event is stored in the horse record.

**Key rules.**
- Input by exception: no comment is required when everything is normal.
- Horse, author, yard, date and time are pre-filled.
- The alert and the history entry are created by the system, not re-typed by someone.

**Tables.** `RATION` (cheval_id, auteur_id, date_heure, repas, part_consommee, remarque) · `EVENEMENT` for anomalies · `NOTIFICATION` and `RECEPTION` for alerts. ⚠️ Special diets have **no dedicated table** in the MCD.

**Acceptance criterion.** A rider confirms a normal feed in one action without typing anything; recording a partial meal creates a time-stamped alert and an entry in that horse's history.

### B. Training — *Lots, sessions and track feedback*

> Rebuild the morning lots in minutes, publish them to every yard, and capture what happened on the track.

**Today (5:45–6:15 am).** Every morning the assistant trainer rebuilds the lots on a wall board with coloured labels, based on the previous day, absences, horse condition, France Galop entries and horses on the walker or on box rest. The board is read on site, then sent to the other yards by WhatsApp. Briefing and track feedback are oral, and no history is kept.

**Target.**
- A digital card board with drag and drop (touch and mouse) and a keyboard alternative.
- A "Carry over from yesterday" button, with absent people removed automatically.
- Conflict detection.
- A versioned publication, shared with every yard.
- A mobile "My programme" view for riders: one task at a time, confirmed in one gesture. A deviation opens a detailed feedback form.

**Key rules.**
- A lot is a work rotation identified by its number, yard and date. **It has no time**: the `LOT.heure` field in the MCD is contradicted by the specification.
- A horse on box rest, out of the active list or under an incompatible restriction cannot be assigned without an explicit resolution.
- An unavailable rider, or one already assigned in the same lot, cannot receive a second horse. This check relies on the lot and the programme date, never on a time range.
- A draft never silently replaces the published version.

**Tables.** `LOT` · `SEANCE` (exercice, travail_prevu, travail_realise, commentaire) · `AFFECTATION` (fonction, consigne) · related: `ACTEUR`, `LIEU`, `ABSENCE`.

**Acceptance criterion.** The assistant trainer carries over yesterday's lots, fixes the unavailable people and publishes a new version without re-entering every session; assigning a rider already used in the same lot is refused, and no lot shows a time on any screen.

### C. Medical care — *From prescription to race-day clearance*

> A treatment that is only planned is never "done", and a horse under withdrawal never reaches the start.

**Today (8:30 am onwards).** Prescriptions, reports and invoices arrive by e-mail. Treatments are written in a paper diary, on the pharmacy whiteboard and on the yard whiteboards. The withdrawal period is computed from a Google Form feeding a Google Sheet (the "vet list"), which is compared by hand with France Galop. Prescriptions are archived on paper for 5 years. Vaccination is weekly: a France Galop export on Thursday, paper booklets, then a manual update.

**Target.**
- A single treatment register per horse, with the prescription attached.
- The list of today's care tasks, and confirmation of each administration actually performed.
- Automatic withdrawal-period calculation.
- A restriction that blocks or warns before any race entry.
- A vaccination calendar with reminders.
- Quick measurements (temperature, weight).

**Key rules.**
- A prescription plans. Only a confirmed administration records the act. An unconfirmed task stays "to do" or "late", never "done".
- For a sensitive treatment, the user explicitly re-reads product, dose and horse before confirming.
- Withdrawal periods, thresholds and protocols are versioned and validated by a competent person; AI never invents them.
- A restriction references its source, its scope and its validator. An expired date never lifts a restriction automatically.
- **Target rule: no horse can be declared a runner if its veterinary status is incompatible with the race date.**
- For temperature and weight, the user picks the horse and types the value on a numeric keypad. No text field is mandatory.

**Tables.** `PRODUIT` · `ACTE_SANTE` (type_acte, delai_retrait_jours, debut_retrait, fin_retrait, statut_certification…) · `PRESCRIPTION`, `ADMINISTRATION`, `EXAMEN`, `VACCINATION`, `ACTE_PRESCRIPTION`, `ACTE_DOCUMENT` · `ENGAGEMENT` and `COURSE` for the pre-race check. ⚠️ The MCD has **no `RESTRICTION` table and no `MESURE` table**.

**Acceptance criterion.** Confirming the administration of a product with a withdrawal period creates a restriction; validating a race entry for that horse on a date inside the period is then blocked, with the justification shown. A horse whose status is unknown is blocked the same way.

### D. Farriery — *Every shoe on record*

> Know which horses the farrier must see, what was done, and what changes before a race.

**Today.** The farrier comes every 3 to 4 weeks, or on specific need. Horses to see are written on a "Farrier" whiteboard and coordination is oral. Shoeing is recorded in the farrier's personal notebook. A "Runners / Shoeing" board is used to adapt shoes before a race, and a manual list is used for billing.

**Target.**
- A farriery module inside the horse record.
- Horses to see, with their due dates.
- Each intervention recorded: date, shoeing type, observations, farrier.
- A "Runners / Shoeing" view.
- The billing basis.
- Osteopathy and dentistry: processes still to be documented (bonus).

**Key rules.**
- Farriery is a health act: `ACTE_SANTE` with `type_acte = ferrure`.
- Every intervention carries its author, real date, source and status, like any other record (see [Traceability](#5-non-negotiable-design-principles)).

**Tables.** `ACTE_SANTE` (type_acte = ferrure, type_ferrure, observations, intervenant_id) · related: `ACTE_DOCUMENT`, `ENGAGEMENT`, `PRESTATION`.

**Acceptance criterion.** The "Runners / Shoeing" view lists every horse with an upcoming race entry next to its last recorded shoeing (date, type, farrier), and every recorded intervention appears in the billing basis.

### E. Scoring — *Horse condition and form*

> Turn the rider's impression into a trend you can act on.

The documents do not describe a standalone "scoring" module. Scoring is built from:

- the track feedback "3-level input + voice note";
- the lameness score in `EXAMEN` (membre, score_boiterie, sensibilite, protocole_recommande);
- the daily summary and alerts on recurring anomalies.

**Today.** Rider feedback is oral and subjective. The assistant trainer weighs it with personal judgement, then it is lost.

**Target.**
- Enter a condition level in one gesture.
- Store it per horse and show trends.
- Raise an alert when a problem recurs.
- Feed the daily summary.

**Guardrails.**
- No decorative indicators and **no individual ranking of people**.
- Always separate what is a fact, what is planned, what is missing and what is a hypothesis.
- AI flags, it never diagnoses.

> **Hypothesis to make explicit.** The labels of the 3 levels and the alert rules are **not defined** in the documents. Your team proposes them and presents them clearly as hypotheses.

**Tables.** `SEANCE` (track feedback) · `EXAMEN` (lameness score) · `EVENEMENT` · `NOTIFICATION`.

**Acceptance criterion.** A rider records a condition level in one gesture after a session; the level appears in the horse's history and trend; reaching the alert threshold your team defined (documented as a hypothesis) raises an alert without any automatic diagnosis.

### F. Cross-cutting: voice remark on interventions — *Speak, check, confirm*

> Dictate a remark on any intervention; the AI drafts, a human confirms.

**Today.** Feedback is oral and the trainer sends WhatsApp voice notes. Nothing is captured.

**Target.**
- On every intervention (feeding, track feedback, care, shoeing, observation), the user can dictate a remark.
- The remark is transcribed, and the AI suggests the horse and the type of event.
- The result is a **draft to confirm**; ambiguities are displayed.
- The audio is kept as an attachment.
- Works offline: local recording, deferred transcription.
- Languages: French and English.

**Key rules.**
- Dictation, OCR and summaries only produce drafts. AI makes no medical, sporting or regulatory decision.
- Nothing becomes official without a human confirmation.

**Tables.** `EVENEMENT` (type_evenement, texte, source, statut_validation) · `DOCUMENT` and `EVENEMENT_DOCUMENT` for the audio file · `REQUETE_IA`.

**Acceptance criterion.** A remark recorded offline is transcribed once the device is back online, appears as a draft with the suggested horse and event type, and enters the horse's history only after a user confirms it; the audio stays attached.

---

## 5. Non-negotiable design principles

| Principle | In practice |
|---|---|
| **Field first** | Screens usable standing up and with one hand. A common action takes **at most 3 interactions**, excluding horse selection. A normal task is confirmed in **under 5 seconds**. |
| **Input by exception** | A normal situation is simply confirmed. Only a deviation opens extra fields. No comment is mandatory when there is no anomaly. |
| **Progressive disclosure** | Details appear only according to the action type and the role. No overloaded generic form. |
| **Pre-filled context** | Horse, author, yard, date and time are filled in automatically. Known data is never typed twice. |
| **Planned ≠ done** | Planning, prescription and race entry stay separate from their execution. A missing confirmation never becomes "done". |
| **Offline** | Visible states: "on this device", "synchronised", "to resolve". Synchronisation is idempotent and creates no duplicates. |
| **Security** | Minimum rights by role, by yard and by horse. No shared accounts. Server-side checks. |
| **Supervised AI** | Dictation, OCR and summaries only produce drafts to confirm. AI makes no medical, sporting or regulatory decision. |
| **Traceability** | Every record carries a stable identifier, an author, a real date, a date of receipt, a source and a status (draft, validated, published, done, cancelled, corrected). Every correction keeps the before, the after and the reason. |

---

## 6. Visual identity

The interface takes its cue from the Graffard Racing corporate website: understated elegance and field readability.

| Token | Value |
|---|---|
| Night blue | `#142E3B` |
| Ivory | `#F5F2EB` |
| Soft gold | `#B89C63` |
| Text grey | `#56666D` |
| White | `#FFFFFF` |

- **Touch targets:** at least 44 px.
- **States:** a colour is never used alone; it always comes with an icon and a label.
- **Main navigation:** Today, Planning, Horses, Health, Races, More. A **"+ Add"** button is always visible.

---

## 7. The analysis challenge: MCD vs specification

The data model is an earlier draft; the specification is the target. Your team must **arbitrate and justify** the gaps between them, and show the result in your schema:

- `LOT.heure` contradicts the rule "a lot has no time";
- the `RESTRICTION`, `MESURE` and special-diet tables are missing;
- planning versions are not modelled;
- synchronisation, conflicts and audit are not modelled.

Details and pointers for each gap: [`schema/DATA_MODEL.md` § Known gaps](schema/DATA_MODEL.md#known-gaps-between-the-mcd-and-the-specification).

---

## 8. Priority acceptance criteria (spec §12)

Translated from §12 of the functional specification. These are the criteria your demo must cover.

1. An assistant can carry over the previous day's planning, fix unavailabilities and publish a new version without re-entering every session.
2. Drag and drop works with touch and mouse, and has a keyboard alternative.
3. A rider sees their programme without access to data they do not need.
4. A normal feedback is confirmed in one action; a deviation creates a trace and a follow-up.
5. Entering a temperature has no mandatory text field.
6. An unconfirmed treatment task stays "to do" or "late", never "done".
7. An active or unknown restriction blocks a race-entry validation locally and shows the justification.
8. A vaccination, the vaccination booklet and the official update can be tracked separately.
9. An offline entry shows a clear state and creates no duplicate on reconnection.
10. A planning or health conflict keeps both versions and requires an authorised resolution.
11. Every sensitive correction is audited with before/after and reason.
12. An owner can only see the horses and content explicitly shared with them.
13. On every screen showing lots (including Today, Planning, Calendar, horse record, mobile "My programme"), no lot shows a start time, end time or time range. The display keeps the lot number, the yard and the running order; the date is carried by the programme. No time is asked when a lot is created, edited, carried over or published. Times of care, races, transports and other events are unchanged.

---

## 9. Level 1 vs Level 2

| | Level 1 · "Integrate" | Level 2 · "Build" |
|---|---|---|
| **Starting point** | An existing application (React, Node.js, PostgreSQL with the 49-table model), a "Today" dashboard and the Glass Factory AI | The two scoping documents and the proposed data model only |
| **Stack freedom** | Imposed: respect the existing architecture | Free: your choice, to justify |
| **Expected depth** | Challenges A–F integrated end to end into the existing base | As far as possible across tiers 1 to 5, with the data model arbitrated and evolved |
| **Team profile** | Developers comfortable joining an existing codebase | Full-stack builders with data-modelling and product skills |
