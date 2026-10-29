#!/usr/bin/env python3
"""Banc de `check_socle_integrity` (T-00000901), implementation de l'entree du
meme nom de `checks.manifest.json`.

Clause « socle inviolable » de la spec : la configuration adoptant ne fait
qu'INSERER des gates ; retirer, desactiver, reordonner ou rendre non bloquant un
gate du socle est un ECHEC NOMME. C'est le TEST NEGATIF de la clause : chaque
mutation d'un noeud du socle REEL (`socle.charger()`) rend UNE atteinte qui nomme
ce noeud ; une insertion, ou qu'elle soit et quoi qu'elle porte, n'en rend aucune.
Un noeud deplace est nomme LUI, jamais son voisin (plus longue sous-suite
ordonnee, C4c), et son message l'ancre a son predecesseur REEL dans la chaine
jugee, gate insere ou doublon compris (C4d) ; un drapeau `actif`/`bloquant` non
booleen ne vaut jamais vrai (C2b). Volet checksums : la def d'un agent du socle
modifiee depuis la pose de son checksum, absente, a marqueur illisible, ou
ETRANGERE (son `name` n'est pas celui de l'agent, D7 ; le `name` se lit nu,
entre guillemets simples ou doubles appaires, suivi d'un commentaire, apres un
BOM), est une atteinte ; une def etrangere est refusee AVANT la lecture de son
marqueur, rien d'elle n'est rendu. Une def non marquee ou reprise est RENDUE
(`non_verifiees`), jamais tue, et ne rend pas le socle incomplet. Chaque
atteinte de chaque temoin porte une nature de `ATTEINTES` (`paires`). Les defs
des temoins D sont FABRIQUEES ici par `managed.poser`.

BORNES, celles du module rappelees : la chaine jugee est la chaine EFFECTIVE
qu'un appelant passe. Aucun fichier de configuration n'est lu (sa forme, la cle
`gates`, est celle de T-00000878) et aucun run n'appelle le check (T-00000902 :
echec franc et trace au ledger). Le temoin R1 juge l'arbre REEL du kit ; il
JOURNALISE le nombre de defs non verifiees, sans l'epingler.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Le paquet `cadre` où qu'il vive, chargé par chemin par `vendor_paths` (S-01M5BXT85VP4JBBMXVXR9STP5F).
_SPEC_VENDOR = importlib.util.spec_from_file_location(
    "_check_socle_integrity_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
assert _SPEC_VENDOR is not None and _SPEC_VENDOR.loader is not None
_VENDOR = importlib.util.module_from_spec(_SPEC_VENDOR)
sys.modules[_SPEC_VENDOR.name] = _VENDOR
_SPEC_VENDOR.loader.exec_module(_VENDOR)
_VENDOR.charger_paquet(ROOT, "cadre")

from cadre import managed, socle  # noqa: E402

# R1 lit les defs `.claude/agents/` du KIT ; ailleurs il SAUTE en l'annoncant.
# adopting-tree: le marqueur d'identite du kit ne voyage pas (strip: .agents/IS_THE_KIT) ;
# son absence EST le signal « projet adoptant ».
EST_LE_KIT = (ROOT / ".agents" / "IS_THE_KIT").is_file()

INSERE = "gate-maison"
#: U+FEFF ecrit par `chr`, jamais brut : un caractere invisible dans un banc est aussi faux que dans le module.
BOM = chr(0xFEFF)


def def_posee(agent: str) -> socle.DefLue:
    """Une def Markdown a frontmatter, MARQUEE par `managed.poser` : son checksum est juste."""
    texte = f"---\nname: {agent}\ndescription: def fabriquee par le banc\n---\n\nCorps de {agent}.\n"
    return socle.DefLue(f".claude/agents/{agent}.md", managed.poser(texte, managed.Forme.MARKDOWN))


def paires(r: socle.Releve) -> list[tuple[str, str]]:
    assert all(x.nature in socle.ATTEINTES for x in r.atteintes), [str(x) for x in r.atteintes]
    return [(a.nature, a.cible) for a in r.atteintes]


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        self.socle = socle.charger()
        self.ids = self.socle.ids()
        self.defs = {a: def_posee(a) for a in self.socle.agents()}

    def juger(self, chaine, defs=None) -> socle.Releve:
        return socle.check_socle_integrity(self.socle, tuple(chaine),
                                           self.defs if defs is None else defs)

    def chaine(self) -> list[socle.Gate]:
        return list(socle.chaine_du_socle(self.socle))


# --------------------------------------------------------------------------- C
class ChaineTests(_Base):
    def test_C0_la_chaine_du_socle_et_des_defs_posees_sont_intactes(self):
        r = self.juger(self.chaine())
        self.assertEqual(paires(r), [])
        self.assertEqual(r.non_verifiees, ())
        self.assertTrue(r.intact)
        self.assertEqual([g.id for g in self.chaine()], list(self.ids))

    def test_C1_le_retrait_de_chaque_noeud_est_nomme(self):
        for ident in self.ids:
            with self.subTest(retire=ident):
                r = self.juger(g for g in self.chaine() if g.id != ident)
                self.assertEqual(paires(r), [("retrait", ident)])
                self.assertFalse(r.intact)

    def test_C2_la_desactivation_de_chaque_noeud_est_nommee(self):
        for k, ident in enumerate(self.ids):
            with self.subTest(desactive=ident):
                c = self.chaine()
                c[k] = socle.Gate(ident, actif=False)
                self.assertEqual(paires(self.juger(c)), [("desactivation", ident)])

    def test_C3_l_abaissement_de_chaque_noeud_est_nomme_le_bloquant_declare_passe(self):
        for k, ident in enumerate(self.ids):
            with self.subTest(abaisse=ident):
                c = self.chaine()
                c[k] = socle.Gate(ident, bloquant=False)
                self.assertEqual(paires(self.juger(c)), [("non-bloquant", ident)])
                c[k] = socle.Gate(ident, bloquant=True)
                self.assertEqual(paires(self.juger(c)), [])

    def test_C2b_un_drapeau_non_booleen_ne_vaut_ni_actif_ni_bloquant(self):
        # Drapeaux TYPES : `actif` n'est tenu que par le booleen True, `bloquant` par None ou True.
        # Une chaine « "false" », venue d'une configuration mal lue, est vraie en Python.
        ident = self.ids[6]
        for gate, nature in ((socle.Gate(ident, actif="false"), "desactivation"),
                             (socle.Gate(ident, actif=0), "desactivation"),
                             (socle.Gate(ident, actif=None), "desactivation"),
                             (socle.Gate(ident, bloquant="false"), "non-bloquant"),
                             (socle.Gate(ident, bloquant=0), "non-bloquant")):
            with self.subTest(gate=gate):
                c = self.chaine()
                c[6] = gate
                self.assertEqual(paires(self.juger(c)), [(nature, ident)])

    def test_C4_l_echange_de_chaque_paire_voisine_est_nomme(self):
        for k in range(len(self.ids) - 1):
            avant, apres = self.ids[k], self.ids[k + 1]
            with self.subTest(echange=(avant, apres)):
                c = self.chaine()
                c[k], c[k + 1] = c[k + 1], c[k]
                r = self.juger(c)
                self.assertEqual(paires(r), [("reordonnancement", avant)])
                self.assertIn(apres, str(r.atteintes[0]))

    def test_C4b_un_noeud_deplace_loin_est_nomme(self):
        premier, dernier = self.ids[0], self.ids[-1]
        c = self.chaine()
        c.append(c.pop(0))  # le premier noeud passe en queue
        r = self.juger(c)
        self.assertEqual(paires(r), [("reordonnancement", premier)])
        self.assertIn(dernier, str(r.atteintes[0]))
        c = self.chaine()
        c.insert(0, c.pop())  # le dernier noeud passe en tete
        r = self.juger(c)
        self.assertEqual([n for n, _ in paires(r)], ["reordonnancement"])
        self.assertIn(dernier, str(r.atteintes[0]))

    def test_C4c_le_noeud_deplace_est_celui_qui_est_nomme_jamais_son_voisin(self):
        # Plus longue sous-suite ordonnee : seul le noeud HORS d'elle est nomme.
        self.assertGreater(len(self.ids), 12, "le temoin deplace le noeud de rang 12")
        c = self.chaine()
        c.insert(0, c.pop())  # le dernier noeud passe en tete
        r = self.juger(c)
        self.assertEqual(paires(r), [("reordonnancement", self.ids[-1])])
        self.assertIn("en tete", str(r.atteintes[0]))
        c = self.chaine()
        c.insert(3, c.pop(12))  # le noeud de rang 12 remonte au rang 3
        r = self.juger(c)
        self.assertEqual(paires(r), [("reordonnancement", self.ids[12])])
        self.assertIn(f"apres {self.ids[2]}", str(r.atteintes[0]))

    def test_C4d_l_ancre_du_message_est_le_predecesseur_reel_dans_la_chaine(self):
        # L'ancre est lue dans la chaine JUGEE : un gate insere ou un doublon qui precede le
        # noeud deplace est son predecesseur ; « en tete » ne se dit que du rang 0 de la chaine.
        critique, cloture, dernier = self.ids[2], self.ids[12], self.ids[-1]
        c = self.chaine()
        c.insert(0, c.pop(12))  # revue-cloture en tete...
        c.insert(0, socle.Gate(critique))  # ...derriere un doublon de plan-critic place devant
        r = self.juger(c)
        self.assertEqual(paires(r), [("doublon", critique), ("reordonnancement", cloture)])
        self.assertIn(f"place apres {critique},", str(r.atteintes[1]))
        c = self.chaine()
        c.insert(0, c.pop())  # le dernier noeud en tete...
        c.insert(0, socle.Gate(INSERE))  # ...derriere le gate maison, lui en tete
        r = self.juger(c)
        self.assertEqual(paires(r), [("reordonnancement", dernier)])
        self.assertIn(f"place apres {INSERE},", str(r.atteintes[0]))
        self.assertNotIn("en tete", str(r.atteintes[0]))
        c = self.chaine()
        c.insert(3, c.pop(12))  # revue-cloture remonte au rang 3...
        c.insert(3, socle.Gate(INSERE))  # ...juste derriere un gate maison insere
        r = self.juger(c)
        self.assertEqual(paires(r), [("reordonnancement", cloture)])
        self.assertIn(f"place apres {INSERE},", str(r.atteintes[0]))

    def test_C5_l_insertion_est_acceptee_a_chaque_ancrage_et_quoi_qu_elle_porte(self):
        for k in range(len(self.ids) + 1):
            for gate in (socle.Gate(INSERE), socle.Gate(INSERE, bloquant=True),
                         socle.Gate(INSERE, bloquant=False), socle.Gate(INSERE, actif=False)):
                with self.subTest(position=k, gate=gate):
                    c = self.chaine()
                    c.insert(k, gate)
                    self.assertEqual(paires(self.juger(c)), [])
        c = self.chaine()
        for k in range(len(c), -1, -1):
            c.insert(k, socle.Gate(f"{INSERE}-{k}"))
        self.assertEqual(paires(self.juger(c)), [], "un gate insere a CHAQUE ancrage a la fois")

    def test_C6_un_noeud_du_socle_reinsere_est_un_doublon_nomme(self):
        for ident in self.ids:
            with self.subTest(double=ident):
                c = self.chaine()
                c.append(socle.Gate(ident))
                self.assertEqual(paires(self.juger(c)), [("doublon", ident)])

    def test_C7_chaque_atteinte_nomme_sa_nature_et_sa_cible(self):
        c = self.chaine()
        c[2] = socle.Gate(self.ids[2], actif=False, bloquant=False)
        c.pop(0)
        c.insert(4, socle.Gate(INSERE))
        r = self.juger(c)
        self.assertEqual(paires(r), [("retrait", self.ids[0]), ("desactivation", self.ids[2]),
                                     ("non-bloquant", self.ids[2])])
        for a in r.atteintes:
            with self.subTest(atteinte=a):
                self.assertIn(a.nature, socle.ATTEINTES)
                self.assertTrue(str(a).startswith(f"{a.nature} : {a.cible} — "), str(a))

    def test_C8_agents_rend_chaque_agent_des_noeuds_une_fois_dans_l_ordre(self):
        attendus: list[str] = []
        for n in self.socle.chaine:
            attendus += [a for a in n.agents if a not in attendus]
        self.assertEqual(self.socle.agents(), tuple(attendus))
        self.assertTrue(attendus, "aucun agent au socle : temoins D vides")
        # Le socle reel ne partage aucun agent entre deux noeuds : un socle synthetique le fait.
        partage = socle._valider({"version_format": 1, "voie_directe_depuis": "a",
                                  "chaine": [{"id": "a", "nature": "agent", "agents": ["x", "y"]},
                                             {"id": "b", "nature": "agent", "agents": ["y", "z"]}]},
                                 "banc")
        self.assertEqual(partage.agents(), ("x", "y", "z"))


# --------------------------------------------------------------------------- D
class DefsTests(_Base):
    def test_D1_une_def_modifiee_depuis_son_checksum_est_nommee(self):
        for agent in self.socle.agents():
            with self.subTest(modifie=agent):
                defs = dict(self.defs)
                lue = defs[agent]
                defs[agent] = socle.DefLue(lue.relatif, lue.texte + "Une ligne ajoutee.\n")
                r = self.juger(self.chaine(), defs)
                self.assertEqual(paires(r), [("checksum", agent)])
                self.assertIn(lue.relatif, str(r.atteintes[0]))

    def test_D2_une_def_absente_est_nommee(self):
        for agent in self.socle.agents():
            with self.subTest(absente=agent):
                defs = {a: d for a, d in self.defs.items() if a != agent}
                self.assertEqual(paires(self.juger(self.chaine(), defs)), [("def-absente", agent)])

    def test_D3_un_marqueur_illisible_ou_une_forme_inconnue_sont_nommes(self):
        agent = self.socle.agents()[0]
        mutile = (f"---\nname: {agent}\n# cadre.managed: true\n# cadre.version: \"1\"\n"
                  f"# cadre.checksum: \"sha256:{'0' * 63}\"\n---\n\nCorps.\n")
        for lue in (socle.DefLue(f".claude/agents/{agent}.md", mutile),
                    socle.DefLue(f".claude/agents/{agent}.py", self.defs[agent].texte)):
            with self.subTest(relatif=lue.relatif):
                r = self.juger(self.chaine(), {**self.defs, agent: lue})
                self.assertEqual(paires(r), [("marqueur-illisible", agent)])

    def test_D4_une_def_non_marquee_ou_reprise_est_rendue_jamais_tue(self):
        agent = self.socle.agents()[-1]
        nue = f"---\nname: {agent}\n---\n\nCorps.\n"
        reprise = f"---\nname: {agent}\n# cadre.managed: false\n---\n\nCorps repris.\n"
        for texte, etat in ((nue, "non_marque"), (reprise, "repris")):
            with self.subTest(etat=etat):
                defs = {**self.defs, agent: socle.DefLue(f".claude/agents/{agent}.md", texte)}
                r = self.juger(self.chaine(), defs)
                self.assertEqual(paires(r), [])
                self.assertEqual(r.non_verifiees, ((agent, etat),))
                self.assertTrue(r.intact, "une def non verifiee est RENDUE, elle ne rend pas le socle incomplet")

    def test_D5_chaine_et_defs_sont_jugees_ensemble(self):
        agent = self.socle.agents()[0]
        defs = {a: d for a, d in self.defs.items() if a != agent}
        c = [g for g in self.chaine() if g.id != self.ids[-1]]
        self.assertEqual(paires(self.juger(c, defs)),
                         [("retrait", self.ids[-1]), ("def-absente", agent)])

    def test_D6_sans_aucune_def_chaque_agent_du_socle_est_nomme_absent(self):
        r = self.juger(self.chaine(), {})
        self.assertEqual(paires(r), [("def-absente", a) for a in self.socle.agents()])

    def test_D7_la_def_d_un_autre_agent_est_etrangere_et_nommee(self):
        agents = self.socle.agents()
        for a, b in zip(agents, agents[1:] + agents[:1]):
            with self.subTest(agent=a, def_de=b):
                r = self.juger(self.chaine(), {**self.defs, a: def_posee(b)})
                self.assertEqual(paires(r), [("def-etrangere", a)])
                self.assertIn(f"name {b}, attendu {a}", str(r.atteintes[0]))
        a, b = agents[0], agents[1]
        sans_nom = managed.poser("---\ndescription: def sans name\n---\n\nCorps.\n", managed.Forme.MARKDOWN)
        r = self.juger(self.chaine(), {**self.defs, a: socle.DefLue(f".claude/agents/{a}.md", sans_nom)})
        self.assertEqual(paires(r), [("def-etrangere", a)])
        self.assertIn("name absent", str(r.atteintes[0]))
        # La forme TOML (`name = "..."`) est lue par la meme regle : juste, elle passe ; d'un autre, elle est nommee.
        for nom, attendu in ((a, []), (b, [("def-etrangere", a)])):
            with self.subTest(toml=nom):
                texte = managed.poser(f'name = "{nom}"\ndescription = "def fabriquee"\n', managed.Forme.TOML)
                r = self.juger(self.chaine(), {**self.defs, a: socle.DefLue(f".codex/agents/{a}.toml", texte)})
                self.assertEqual(paires(r), attendu)
        # Formes LUES (sur ce85573d, chacune rendait « name absent ») : guillemets simples, commentaire de fin de ligne.
        md, toml = (f".claude/agents/{a}.md", managed.Forme.MARKDOWN), (f".codex/agents/{a}.toml", managed.Forme.TOML)
        for (relatif, forme), ligne in ((md, "name: '{n}'"), (md, "name: {n}  # c"), (md, "name: \"{n}\" # c"),
                                        (toml, "name = '{n}'"), (toml, "name = '{n}' # c")):
            corps = ("---\n{l}\ndescription: d\n---\n\nC\n" if forme is managed.Forme.MARKDOWN
                     else "{l}\ndescription = \"d\"\n")
            for nom, attendu in ((a, []), (b, [("def-etrangere", a)])):
                with self.subTest(forme=forme.value, ligne=ligne, nom=nom):
                    texte = managed.poser(corps.format(l=ligne.format(n=nom)), forme)
                    r = self.juger(self.chaine(), {**self.defs, a: socle.DefLue(relatif, texte)})
                    self.assertEqual(paires(r), attendu)
                    self.assertEqual(r.non_verifiees, ())
                    if attendu:
                        self.assertIn(f"name {b}, attendu {a}", str(r.atteintes[0]))
        # Le BOM initial ne gene que la PREMIERE ligne : celle d'une def TOML NON MARQUEE (une def posee
        # ouvre sur `# cadre.`). Sur ce85573d elle rendait « name absent » et taisait son etat `non_marque`.
        for ligne in ('name = "{n}"', "name = '{n}'"):
            for nom, attendu, rendu in ((a, [], ((a, "non_marque"),)), (b, [("def-etrangere", a)], ())):
                with self.subTest(bom=ligne, nom=nom):
                    texte = BOM + ligne.format(n=nom) + '\ndescription = "d"\n'
                    r = self.juger(self.chaine(), {**self.defs, a: socle.DefLue(toml[0], texte)})
                    self.assertEqual(paires(r), attendu)
                    self.assertEqual(r.non_verifiees, rendu)
        # Des guillemets NON appaires ne se lisent pas : le `name` reste absent.
        for ligne in (f"name: '{a}\"", f"name: \"{a}'"):
            with self.subTest(non_appaires=ligne):
                texte = managed.poser(f"---\n{ligne}\n---\n\nC\n", managed.Forme.MARKDOWN)
                r = self.juger(self.chaine(), {**self.defs, a: socle.DefLue(f".claude/agents/{a}.md", texte)})
                self.assertEqual(paires(r), [("def-etrangere", a)])
                self.assertIn("name absent", str(r.atteintes[0]))
        # Une def etrangere NON MARQUEE est refusee AVANT la lecture de son marqueur : rien n'en est rendu.
        nue = socle.DefLue(f".claude/agents/{a}.md", f"---\nname: {b}\n---\nC\n")
        r = self.juger(self.chaine(), {**self.defs, a: nue})
        self.assertEqual(paires(r), [("def-etrangere", a)])
        self.assertEqual(r.non_verifiees, ())


# --------------------------------------------------------------------------- R
class ArbreReelTests(unittest.TestCase):
    def test_R1_le_socle_du_kit_et_ses_defs_claude_sont_intacts(self):
        if not EST_LE_KIT:
            self.skipTest("arbre adoptant : les defs `.claude/agents/` du kit ne sont pas le sujet ici")
        s = socle.charger()
        defs = {}
        for agent in s.agents():
            chemin = ROOT / ".claude" / "agents" / f"{agent}.md"
            if chemin.is_file():
                defs[agent] = socle.DefLue(chemin.relative_to(ROOT).as_posix(),
                                           chemin.read_text(encoding="utf-8"))
        r = socle.check_socle_integrity(s, socle.chaine_du_socle(s), defs)
        self.assertEqual([str(a) for a in r.atteintes], [])
        etats = sorted({e for _, e in r.non_verifiees})
        print(f"check_socle_integrity : {len(r.non_verifiees)} def(s) sur {len(s.agents())} "
              f"non verifiee(s), etats {etats} — borne journalisee, jamais epinglee", file=sys.stderr)


if __name__ == "__main__":
    unittest.main()
