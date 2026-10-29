# plan-critic — T-01M63K36QN0S5WJE7VETZR5GX3 — itération 2/2 — NO_GO

Plan jugé : docs/tasks/T-01M63K36QN0S5WJE7VETZR5GX3-plan.md (r2) sha256=b668a0dfe96b58ce810c0d8fe1b52b3eaa9d0937b9b52e850b887ee34a5d9a5b

VERDICT: NO_GO
ITERATION: 2/2
CHECKLIST
  scope-fit GO (check 37/45 rejoué) ; index-fidelity GO ; blast-radius GO (contrat aligné api et web ; `npm install --no-package-lock --offline` avec un workspace absent => rc 0, aucun lockfile : C4 tient) ; test-adequacy NO_GO (check-ignore rejoué, mutant rougit ; témoin (iii) par Ctrl+C aveugle à l'orphelin C8) ; rollback-viability GO (C6 fermé) ; constraint-compliance GO (C2 fermé) ; cost-realism GO_AVEC_RESERVES (FORECAST non relayé).
FINDINGS
  C8 blocking step 4 — `process.exit` juste après `spawn("taskkill")` sans attendre laisse l'enfant de l'autre workspace vivant. Reproduit deux fois (/tmp/cadre-gdtr47, a = dev long, b = sort 3) : `npm run dev` => rc=3, puis un node.exe survit (PID 13716, puis 26204). En attendant l'`exit` de taskkill : aucun survivant.
    → Étape 4, remplacer « et dev.mjs sort avec le code du premier enfant sorti » par : « et dev.mjs ne sort, avec le code du premier enfant sorti, qu'à l'`exit` (ou à l'`error`) du taskkill sous win32, jamais dans le même tick que son spawn (orphelin mesuré sinon) ».
    → Tests : « (iv) dans un clone jetable, workspaces stub a=`node -e "setInterval(()=>{},1000)"` et b=`node -e "setTimeout(()=>process.exit(3),3000)"` : `npm run dev; echo $?` => `3`, puis `powershell "(Get-CimInstance Win32_Process -Filter \"Name='node.exe'\" | ? CommandLine -like '*setInterval*').Count"` => `0` ; mutant `process.exit` sans attente => `1` ».
  C9 concern Tests l.38 — mutant `child.kill()` sous win32 non mesuré contre (iii). → le rattacher à (iv) ; garder (iii) comme contrôle manuel du Ctrl+C.
  C10 concern cost-realism — FORECAST non relayé. → l'exécuteur l'émet avant la porte humaine.
BILAN: C1 rouvert sous C8 (correction incomplète) ; C2–C7 fermés ; C3 fermé par mesure ; C5 fermé sur (i)/(ii).
STRONGEST OBJECTION: l'orphelin qui garde le port reste joignable et aucun témoin prévu ne le voit.
UNKNOWNS: Ctrl+C sous mintty et `node --watch` ; cause exacte (job libuv) inférée ; TS 7 vs options de la base non mesuré ; FORECAST.
CAUSE_RACINE: PAS_DE_VERIFICATION
LECON_CANDIDATE: Un arrêt de processus asynchrone se termine AVANT la sortie du parent : on attend son `exit`.
NEXT: planner-revise — plafond atteint (SOURCE=adoptant) : escalade au pilote.
