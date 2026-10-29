"""Les moitiés scindées par T-01M55Z3W38 recopient des blocs de leur tête ;
ce banc rougit dès qu'une ligne recopiée n'existe plus telle quelle dans la tête."""
import pathlib
import unittest

SEC = pathlib.Path(__file__).resolve().parents[2] / ".agents" / "security"
PAIRES = {  # queue -> (tête, 1re ligne des bras propres, plages recopiées)
    "semgrep-scan-git.test.sh": ("semgrep-scan.test.sh", "# (sgc*) (sgl*)", 7),
    "gitleaks-scan-index.test.sh": ("gitleaks-scan.test.sh", "# ==== T-01M4X7Q1RR7WPF1GWYFEFHDDM9", 5),
}


def preambule(queue, fin):
    q = (SEC / queue).read_text(encoding="utf-8").splitlines()
    debut = q.index("set -u")
    arret = next(i for i, l in enumerate(q) if l.startswith(fin))
    if q[arret - 1].startswith("# ===="):
        arret -= 1
    return q[debut:arret]


def segments(pre, tete):
    index = {}
    for i, ligne in enumerate(tete):
        index.setdefault(ligne, []).append(i)
    k = n = 0
    absentes = []
    while k < len(pre):
        meilleur = 0
        for s in index.get(pre[k], ()):
            m = 0
            while k + m < len(pre) and s + m < len(tete) and tete[s + m] == pre[k + m]:
                m += 1
            meilleur = max(meilleur, m)
        if meilleur == 0:
            absentes.append(pre[k])
            meilleur = 1
        n += 1
        k += meilleur
    return n, absentes


class PreambuleRecopie(unittest.TestCase):
    def test_chaque_preambule_recopie_est_identique_a_sa_tete(self):
        for queue, (tete, fin, plages) in PAIRES.items():
            with self.subTest(queue=queue):
                t = (SEC / tete).read_text(encoding="utf-8").splitlines()
                n, absentes = segments(preambule(queue, fin), t)
                self.assertEqual(absentes, [], f"{queue} : lignes absentes de {tete}")
                self.assertLessEqual(n, plages, f"{queue} : {n} blocs, attendu <= {plages}")

    def test_le_banc_rougit_sur_une_tete_mutee(self):
        tete, fin, _ = PAIRES["semgrep-scan-git.test.sh"]
        t = (SEC / tete).read_text(encoding="utf-8").splitlines()
        mut = [l.replace("advice.detachedHead=false", "advice.detachedHead=true")
               if l.startswith("GIT_ISO=") else l for l in t]
        pre = preambule("semgrep-scan-git.test.sh", fin)
        self.assertEqual(segments(pre, t)[1], [])
        self.assertEqual(len(segments(pre, mut)[1]), 1, "le mutant GIT_ISO doit laisser une ligne absente")


if __name__ == "__main__":
    unittest.main()
