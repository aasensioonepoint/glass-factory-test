"""Une décision consignée sans tâche est un VŒU — et ce filet le refuse.

POURQUOI CE FICHIER EXISTE, et il a été payé trois fois dans la même journée.
La règle permanente n° 3 de `PLAN-ETAT.md` dit qu'une décision déjà prise ne se
repose pas en point ouvert. Elle a été écrite le 2026-09-13 **avec deux
contre-exemples vivants dans le même fichier** : les points ouverts `A` et `F`
étaient tranchés au § « Décisions du pilote, appliquées » et restaient posés en
QUESTION au tableau des points ouverts. Une session obéissante, appliquant la
règle à la lettre, trouvait les deux réponses et rouvrait — ce qui a coûté au
pilote une reprise sèche : « c'est pourtant pas difficile comme suite, on a déjà
parlé de ça ».

LE MÉCANISME DE LA FAUTE, qui est plus utile que la faute. La décision était
ENREGISTRÉE mais non APPLIQUÉE : le §5 du plan de référence disait toujours « les
trois surfaces », et **aucune tâche ne portait l'écart**. Une décision sans tâche
se relit comme une question ouverte à la session suivante, indéfiniment.

CE QUE CE FILET PROUVE, ET CE QU'IL NE PROUVE PAS — dit plutôt que découvert.
Il prouve que chaque décision NOMME une tâche ou se déclare appliquée. Il ne
prouve PAS que la tâche a fait le travail, ni que la décision est juste : c'est
un filet contre l'OUBLI, comme la garde du binôme, pas contre l'erreur. La règle
n° 3 restait autrement tenue par la seule mémoire — et ce dépôt a mesuré ce que
vaut une règle tenue par la mémoire.

`PLAN-ETAT.md` NE VOYAGE PAS (`strip:` le retient), donc ce banc saute hors du
dépôt du kit plutôt que de rougir chez un adoptant qui n'a pas ce fichier.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
# adopting-tree: PLAN-ETAT.md ne voyage pas ; tout ce banc saute sans lui.
PLAN = RACINE / "PLAN-ETAT.md"
# SPLIT DU 2026-09-14 — les sections que ce banc inspecte (« Décisions du pilote,
# appliquées », « Points ouverts pour le pilote ») ont migré dans le fichier de
# détail. Lire le seul `PLAN-ETAT.md` aurait rendu chaque `section()` VIDE, donc
# chaque assertion VACUEMENT VERTE : le filet aurait survécu à la perte de son
# objet sans un seul rouge — la façon exacte dont un filet meurt sans bruit.
DETAIL = RACINE / "PLAN-ETAT-DETAIL.md"

# LA BORNE SE LIT DANS LE HOOK, ELLE NE SE RECOPIE PAS. Un `6000` codé en dur ici
# resterait vert si `_PE_MAX` baissait : le banc certifierait alors une tête qui
# EST tronquée. C'est la faute que ce fichier reproche partout ailleurs — l'état
# se dérive, il ne se recopie pas — appliquée à son propre filet.
# Repli sur 6000 si le hook est illisible : ce banc ne doit pas mourir avec lui,
# et une borne par défaut trop STRICTE ne peut produire qu'un faux rouge, jamais
# un faux vert.
_HOOK = RACINE / ".claude/hooks/session-start.sh"
_m = (re.search(r"^\s*_PE_MAX=(\d+)", _HOOK.read_text(encoding="utf-8"), re.M)
      if _HOOK.is_file() else None)
FENETRE = int(_m.group(1)) if _m else 6000

# UNE DÉCISION EST « PORTÉE » si elle cite un identifiant de tâche OU se déclare
# appliquée. Les deux formes sont admises parce qu'une décision peut être
# appliquée dans le même geste que sa prise — auquel cas exiger une tâche
# fabriquerait un ticket vide, et un ticket vide se ferme sans rien faire.
# Un `T-<ULID>` (T-00000726 : 26 symboles Crockford MAJUSCULES) cite aussi une
# tâche ; il est jugé SANS l'insensibilité à la casse (`(?-i:…)`), qui ne vaut que
# pour « appliqué » : un `t-<ulid>` en minuscules n'est pas un id.
PORTEE = re.compile(r"(?-i:T-[0-9A-HJKMNP-TV-Z]{26})|T-\d{6,8}|appliqué|APPLIQUÉ", re.IGNORECASE)


def section(texte: str, titre: str) -> str:
    m = re.search(
        rf"^## {re.escape(titre)}.*?$(.*?)(?=^## |\Z)", texte, re.S | re.M
    )
    return m.group(1) if m else ""


# LA TÊTE EST UN ROUTEUR (S-00003374, T-00001064) : par où commencer, ce qui te
# refusera, la porte, la carte — l'ÉTAT n'y vit plus. Deux bornes DÉCLARÉES, qui
# ne se lisent nulle part ailleurs : elles sont distinctes de `_PE_MAX` (la fenêtre
# d'injection de `session-start.sh`, qui ne bouge pas) et se relèvent par décision
# pilote TRACÉE seulement — relever le nombre pour faire passer un ajout est
# exactement la croissance que le routeur existe pour arrêter.
ROUTEUR_MAX_OCTETS = 20_000
ROUTEUR_CORPS_2_MAX_LIGNES = 12


def forme_du_routeur(texte: str) -> list[str]:
    """Les violations de la forme du routeur ; [] si elle tient : sections 1 à 7
    dans l'ordre (numéros FIGÉS par S-00003374 — sept renvois « § 4 » les citent),
    corps du § 2 d'au plus `ROUTEUR_CORPS_2_MAX_LIGNES` lignes significatives, au
    plus `ROUTEUR_MAX_OCTETS` octets."""
    violations = []
    titres = re.findall(r"^## (\d+)\.", texte, re.M)
    if titres != [str(n) for n in range(1, 8)]:
        violations.append(f"sections {titres} : attendu 1 à 7, dans l'ordre (S-00003374)")
    corps = [l for l in section(texte, "2.").splitlines() if l.strip() and l.strip() != "---"]
    if len(corps) > ROUTEUR_CORPS_2_MAX_LIGNES:
        violations.append(f"corps du § 2 : {len(corps)} lignes, au plus {ROUTEUR_CORPS_2_MAX_LIGNES}")
    taille = len(texte.encode("utf-8"))
    if taille > ROUTEUR_MAX_OCTETS:
        violations.append(f"{taille} octets, au plus {ROUTEUR_MAX_OCTETS}")
    return violations


@unittest.skipUnless(PLAN.is_file(), "PLAN-ETAT.md ne voyage pas jusqu'ici")
class DecisionsPorteesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.texte = PLAN.read_text(encoding="utf-8")
        if DETAIL.is_file():
            self.texte += "\n" + DETAIL.read_text(encoding="utf-8")

    def test_chaque_decision_appliquee_nomme_sa_tache_ou_se_dit_appliquee(self) -> None:
        corps = section(self.texte, "Décisions du pilote, appliquées")
        puces = re.findall(r"^- \*\*(.+?)\*\*(.*?)(?=^- \*\*|\Z)", corps, re.S | re.M)
        self.assertTrue(
            puces,
            "VACUITÉ : la section « Décisions du pilote, appliquées » est absente "
            "ou ne porte aucune puce — ce filet serait vert sans rien mesurer",
        )
        orphelines = [
            titre.strip()[:70]
            for titre, reste in puces
            if not PORTEE.search(titre + reste)
        ]
        self.assertEqual(
            orphelines,
            [],
            "DÉCISION SANS TÂCHE — elle se relira comme une question ouverte, et "
            "quelqu'un la reposera au pilote. Ouvre le ticket qui l'APPLIQUE, ou "
            "écris où elle l'est déjà. Règle permanente n° 3 de PLAN-ETAT.md.\n  "
            + "\n  ".join(orphelines),
        )

    def test_aucun_point_ouvert_non_barre_ne_reste_sans_tache(self) -> None:
        """UN POINT OUVERT NON BARRÉ EST UNE QUESTION AU PILOTE. S'il en porte
        déjà la réponse, il doit être barré ; s'il attend vraiment, il doit au
        moins nommer ce qui le débloquera. Entre les deux, il fait reposer une
        question déjà tranchée — le défaut exact du 2026-09-13."""
        corps = section(self.texte, "Points ouverts pour le pilote")
        self.assertTrue(corps.strip(), "VACUITÉ : section des points ouverts absente")
        lignes = [
            l for l in corps.splitlines()
            if l.startswith("| ") and not l.startswith("| #") and "---" not in l
        ]
        self.assertTrue(lignes, "VACUITÉ : aucun point ouvert listé")
        ouverts = [l for l in lignes if "~~" not in l.split("|")[1]]
        muets = [l.split("|")[1].strip() for l in ouverts if not PORTEE.search(l)]
        self.assertEqual(
            muets,
            [],
            "POINT OUVERT QUI NE NOMME NI TÂCHE NI APPLICATION — soit il est "
            "tranché et doit être barré, soit il doit dire ce qui le débloque.\n  "
            + "\n  ".join(muets),
        )

    def test_la_regle_qui_justifie_ce_filet_existe_toujours(self) -> None:
        """Le jour où la règle n° 3 disparaît, ce filet devient un caprice. Il
        doit alors rougir et forcer la question, pas continuer en silence."""
        self.assertIn(
            "Une décision déjà prise ne se repose pas",
            self.texte,
            "la règle permanente n° 3 a disparu : ce filet n'a plus de fondement, "
            "décide de le retirer ou de la réécrire",
        )

    def test_la_tete_tient_dans_la_fenetre_d_injection(self) -> None:
        """`PLAN-ETAT.md` doit tenir dans `_PE_MAX`, la borne de TAILLE du pilote.

        CE QUE CE BANC NE GARANTIT PLUS (T-00000834, 2026-09-29) : que le
        fichier ARRIVE en entier au modèle. Claude Code réduit tout
        additionalContext de plus d'environ 10 000 caractères à un aperçu de
        2 ko, et c'est ce qui arrivait à chaque injection depuis le 2026-09-24.
        `session-start.sh` injecte désormais sous un budget total (`SS_BUDGET`)
        où l'état de chantier passe en dernier, avec une coupe TOUJOURS dite
        (« lis PLAN-ETAT.md en entier »). Ce banc tient la discipline de taille ;
        `test_session_start_budget.py` tient le budget.

        La borne est LUE dans `session-start.sh` (`_PE_MAX`) et jamais recopiée
        ici — un nombre écrit en dur dans une docstring se périme sans faire
        rougir personne. Cette docstring portait « 12 000 depuis le 2026-09-14 »
        et l'a prouvé : le 2026-09-19 la borne est passée à 20 000 et la phrase
        est devenue fausse sans qu'aucun banc ne rougisse. Le chiffre est retiré
        plutôt que corrigé — c'est `_PE_MAX` qui fait foi, ici comme ailleurs.

        C'EST LE MÉCANISME QUI REMPLACE UN ARBITRAGE RÉPÉTÉ. Tant que ce fichier
        pesait 91 Ko, `session-start.sh` en coupait 94 % et chaque ajout en tête
        expulsait autre chose EN SILENCE — mesuré trois fois : la table des six
        décisions est sortie de la fenêtre, y est rentrée, puis a été coupée au
        milieu d'une ligne. Le protocole de re-mesure qui gardait ce budget
        comptait des MOTIFS NOMMÉS, donc il restait vert pendant que du contenu
        non nommé se faisait expulser. Ceci compte le BUDGET, ce qu'aucun grep
        ne fait, et c'est pour ça que le split du 14/09 tient.

        Le remède quand ça rougit n'est JAMAIS de rogner ce qui est déjà là :
        c'est de pousser vers `PLAN-ETAT-DETAIL.md`.
        """
        taille = len(PLAN.read_bytes())
        self.assertLessEqual(
            taille, FENETRE,
            f"PLAN-ETAT.md pèse {taille} octets, {taille - FENETRE} au-delà de "
            "la borne de taille du pilote (_PE_MAX), et session-start.sh ne lit "
            "pas au-delà. Déplace vers PLAN-ETAT-DETAIL.md — ne rogne pas la tête.",
        )

    def test_le_routeur_garde_sa_forme(self) -> None:
        """LA TÊTE RESTE UN ROUTEUR (S-00003374, T-00001064). Elle a pesé 45 Ko,
        dont 26 Ko d'état au § 2 : chaque session y empilait son bloc, et la borne
        de taille a été relevée trois fois avant qu'on admette que relever n'est
        pas un remède. L'état vit au board, dans `specs.py` et dans la reprise du
        lot ; l'histoire, au DÉTAIL. Ce banc tient la FORME — il ne juge pas le
        contenu. CONTRÔLE NÉGATIF INTERNE : un § 2 gonflé de 40 lignes doit violer
        la forme, sinon ce banc serait vert sans rien mesurer."""
        routeur = PLAN.read_text(encoding="utf-8")
        self.assertTrue(section(routeur, "2.").strip(),
                        "VACUITÉ : § 2 absent du routeur — la forme ne mesurerait rien")
        violations = forme_du_routeur(routeur)
        self.assertEqual(
            violations, [],
            "LE ROUTEUR A PERDU SA FORME : " + " ; ".join(violations)
            + ". Déplace vers la reprise du lot ou vers le DÉTAIL — ne relève pas la borne.")
        gonfle = re.sub(r"^(## 2\..*)$", lambda m: m.group(1) + "\n" + "\n".join(
            f"- état empilé {i}" for i in range(40)), routeur, count=1, flags=re.M)
        self.assertTrue(forme_du_routeur(gonfle),
                        "CONTRÔLE NÉGATIF : un § 2 gonflé de 40 lignes doit violer la forme")

    def test_le_detail_existe_et_porte_ce_que_la_tete_promet(self) -> None:
        """La tête RENVOIE au détail ; si le détail manque, elle ment.

        Contrôle de non-vacuité du split : sans lui, vider le fichier de détail
        rendrait `section()` vide partout et TOUTES les assertions de ce banc
        vertes sans objet — un filet qui survit à la perte de sa cible.
        """
        self.assertTrue(
            DETAIL.is_file(),
            "PLAN-ETAT.md renvoie à PLAN-ETAT-DETAIL.md, qui n'existe pas",
        )
        for titre in ("La file du chantier", "Décisions déjà prises",
                      "Points ouverts pour le pilote"):
            self.assertIn(
                titre, DETAIL.read_text(encoding="utf-8"),
                f"le détail ne porte plus « {titre} » — le split a perdu une "
                "section que la tête annonce encore",
            )


class PorteeGrammaireTests(unittest.TestCase):
    """LA GRAMMAIRE DE `PORTEE`, sans le fichier d'état : elle voyage avec le banc
    (T-00000726, C1e). Une décision portée par une tâche `T-<ULID>` — la seule forme
    que `tasks.py new` émettra après la bascule — doit compter, sinon le filet la
    lirait ORPHELINE. Le ULID est jugé SANS `re.IGNORECASE` (`(?-i:…)`) : un
    `t-<ulid>` en minuscules n'est pas un id. MUTANT : `PORTEE` laissé à
    `T-\\d{6,8}` ⇒ le premier témoin rougit."""

    ULID = "01M3250V003HCPQKTZ8ENYF4VM"

    def test_un_id_de_tache_ulid_porte_la_decision(self) -> None:
        self.assertIsNotNone(PORTEE.search(f"option A retenue — T-{self.ULID}"))

    def test_l_ancienne_forme_et_l_application_portent_toujours(self) -> None:
        for texte in ("option A — T-00001042", "option B, appliquée", "APPLIQUÉ le 2026-10-08"):
            with self.subTest(texte=texte):
                self.assertIsNotNone(PORTEE.search(texte))

    def test_un_ulid_en_minuscules_ou_tronque_ne_porte_pas(self) -> None:
        for texte in (f"option A — t-{self.ULID.lower()}", f"option A — T-{self.ULID[:-1]}x"):
            with self.subTest(texte=texte):
                self.assertIsNone(PORTEE.search(texte))


if __name__ == "__main__":
    unittest.main()
