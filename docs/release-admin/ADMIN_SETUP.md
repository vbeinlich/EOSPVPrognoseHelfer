# GitHub-Sicherheitskonfiguration zur Betreiberfreigabe

**Vorbereitet, nicht angewendet.** Keine Adminänderung ist für diesen Auftrag
freigegeben. [Konkreter Vorschlag](security-plan.json) und rein lokaler Validator:

```sh
python scripts/admin_plan_check.py
```

Dieser Befehl verwendet kein Netzwerk und hat keine Apply-Funktion. Ein positives
Ergebnis bewertet den Vorschlag, nicht den tatsächlichen GitHub-Zustand.
`id=null` ist bewusst kein verwendbarer API-Reviewer. Erst den autorisierten
Reviewer auswählen, dessen Identität/Berechtigung prüfen und eine ausdrückliche
Betreiberfreigabe für die Adminänderungen einholen.

## Tatsächlich gelesen am 30.10.2026

- Main `5688084...`: `protected=false`, keine Repository-Rulesets einschließlich
  übergeordneter Rulesets. PR #8 ist gemergt, Main-CI erfolgreich.
- Keine Environments, insbesondere kein `public-image-release` und damit keine
  dort konfigurierten Required Reviewers oder Deployment-Beschränkungen.
- Actions-Variablenliste lesbar und leer; `PUBLICATION_ENABLED` fehlt.
- Default-Workflowrechte `read`, Actions dürfen keine PR-Reviews selbst genehmigen.
- Beide tatsächlichen Main-Checks kommen von GitHub Actions, App-ID **15368**.
- GHCR-Package-Administration nicht lesbar: vorhandenes Token ohne `read:packages`,
  HTTP 403. Daraus folgt weder „keine weiteren Writer“ noch eine Freigabe.

## Main: genau eine wirksame Schutzkonfiguration

Vorgeschlagen ist klassischer Branch Protection für das exakte Muster `main`.
Settings → Branches/Rules → Branch protection. Inhalt unter `main_protection`
entspricht dem vorgesehenen Update-Body; die gesamte Plan-JSON ist **kein**
REST-Request und wird hier niemals an GitHub gesendet.

Erforderlich: PR vor Merge, mindestens ein unabhängiges aktuelles Review,
stale Reviews verwerfen, letzte Änderung durch andere Person bestätigen lassen,
Gespräche auflösen, aktueller Branch und beide App-gebundenen Checks `unit` und
`eos-integration`. Admins einbeziehen, keine Bypass-Ausnahmen, Force-Push/Delete aus.
`required_linear_history=false` erhält normale Merge-Commits und damit den
geprüften Kandidaten-Vorfahren; keine nachträgliche Umschreibung von `47bd424`.
Push-Restriktionen sind `null` für dieses persönliche Repository; sie ersetzen
keine PR-/Reviewpflicht. Ein alternativ gewähltes Ruleset muss dieselben
Eigenschaften erfüllen und darf normale Merge-Commits nicht ausschließen.

Bei nur einem Maintainer muss ein zweiter berechtigter Reviewer bestimmt werden;
die unabhängige Reviewpflicht wird nicht durch Bypass oder Selbstfreigabe ersetzt.
Primärquelle: [Branch-Protection-API](https://docs.github.com/en/rest/branches/branch-protection).

## Environment und Deployment-Ziel

Nach gesonderter Freigabe: Settings → Environments → New environment →
`public-image-release`. Required Reviewer mit bestätigter numerischer User-ID,
mindestens Leserecht und ausdrücklicher Verantwortung auswählen. GitHub verlangt
eine Zustimmung aus der Reviewer-Liste, kein Mehrheitsquorum.
`prevent_self_review=true`. Ein Dispatcher darf seine eigene Deployment-Anforderung
nicht selbst genehmigen. Rollen entsprechend auf zwei Personen verteilen.

Deployment branches/tags: Selected branches and tags, **Branch `main`**, keine
Wildcard und keine gleichnamige Tag-Freigabe. Dafür enthält der Plan getrennt
`environment.deployment_branch_policy` und den exakten `deployment_branch`-Body.

In der Oberfläche **Allow administrators to bypass configured protection rules
deaktivieren**. Der aktuelle dokumentierte Environment-REST-Update-Body bietet
diesen Schalter nicht als zugesichertes Feld an; kein erfundenes
`can_admins_bypass`-Feld verwenden und keine Wirkung unterstellen. Einstellung
nachher in der UI prüfen und privat belegen. Ein erstmals per Workflow erzeugtes
ungeschütztes Environment ist keine zulässige Vorbereitung.

Primärquellen: [Environment-API](https://docs.github.com/en/rest/deployments/environments),
[Deployment-Schutz und Admin-Bypass](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments).

## GHCR: noch notwendige Einsicht

Unter Package settings → Manage Actions access / Manage access kontrollieren:

1. Welche Repositories und Benutzer haben Write/Admin? Welche Rechte werden vom
   verbundenen Repository geerbt? Nur dieses Repository und erforderliche
   Verantwortliche beibehalten. Ohne Einsicht keine konkreten Konten erfinden.
2. Andere Workflows, nicht mehr benötigte Repository-Zugriffe und alte manuelle
   PAT-/CI-Schreibwege erfassen. Entzug erst nach ausdrücklicher Adminfreigabe.
3. Im versionierten Workflowbestand hat nur `promote.yaml`/Job `promote`
   `packages: write`; automatische CI nicht. Dies wurde geprüft und getestet.
4. Ein später separat genehmigter Initialupload braucht eventuell temporär einen
   manuellen Writer. Vor Promotion dessen konkurrierende Nutzung ausschließen
   oder Berechtigung wieder entziehen. Der globale Workflow-Lock schützt keine
   unabhängigen manuellen Schreiber.

Ein berechtigter Administrator kann die Einsicht über die UI vornehmen; kein
zusätzlicher Token muss dafür im Repository gespeichert werden. Falls API-Audit
gewünscht, benötigt der verwendete Zugang passende Package-Leserechte. Token-
Werte niemals in Befehlszeilen, Exporten oder Git ablegen.
[GitHub-Package-Zugriff](https://docs.github.com/en/packages/learn-github-packages/configuring-a-packages-access-control-and-visibility).

## Nach genehmigter Einrichtung nur lesend nachprüfen

```sh
gh api repos/vbeinlich/EOSPVPrognoseHelfer/branches/main --jq .protected
gh api repos/vbeinlich/EOSPVPrognoseHelfer/branches/main/protection
gh api repos/vbeinlich/EOSPVPrognoseHelfer/environments/public-image-release
gh api repos/vbeinlich/EOSPVPrognoseHelfer/environments/public-image-release/deployment-branch-policies
gh api repos/vbeinlich/EOSPVPrognoseHelfer/actions/permissions/workflow
```

404/403 sind kein erfolgreicher Schutz-Nachweis. Danach UI-Bypass-Schalter und
Package-Writer-Liste separat bestätigen. `PUBLICATION_ENABLED` bleibt auch nach
Sicherheitseinrichtung aus, bis sämtliche übrigen Release-Gates und die konkrete
Veröffentlichung ausdrücklich freigegeben sind. Dieser Auftrag aktiviert nichts.
