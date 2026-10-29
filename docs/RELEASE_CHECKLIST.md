# GENETIC-Abnahme und erster stabiler MIT-Release

Stand 29.10.2026. **Vorbereitet, nicht veröffentlicht oder produktiv installiert.**
Verbindliche Reihenfolge aus dem [neuesten Auftrag in PR #3](https://github.com/vbeinlich/EOSPVPrognoseHelfer/pull/3#issuecomment-6494748299):
reale automatische GENETIC-Abnahme → Issue #1 schließen → PR #3 prüfen/mergen →
stabiler Release → erst dann Implementierung von Issue #5. Bisherige lokale Tests
ersetzen die reale Abnahme nicht. Vorher entsteht kein Wizard-/Skill-Branch oder PR.

## Schon real bestätigt

Die [Betreiber-Abnahme in Issue #1](https://github.com/vbeinlich/EOSPVPrognoseHelfer/issues/1#issuecomment-6494689170)
belegt PV (175 Viertelstunden/43,75 h, 110 Nachtfüllungen, Import rückgelesen),
authentifizierten frischen evcc-e3dc-rscp-SoC und 96 korrekt rückgelesene Preise.
Regulärer Sync: `mode=write`, keine Fehler. Bestehendes EOS: `PREDICTION`, 3600 s,
`GENETIC`, 24 h, `adapter.provider=null`, `ems.notify_url=null`.
Letzter bestätigter Eventstatus: `waiting-publication`. **Noch kein automatisch
berechneter, inhaltlich geprüfter GENETIC-Plan belegt.** Issues #2/#4 sind nach
Betreiberabnahme geschlossen; #1 bleibt dafür offen.

## Abschließende Abnahme ausschließlich lesend

Der bereits vom Betreiber freigegebene reguläre Sync darf nach Veröffentlichung
des vollständigen morgigen Liefertags selbst reagieren. Nicht manuell nachhelfen:
kein `prediction/update`, kein zusätzlicher Optimierungs-POST, kein State-Löschen,
kein erzwungener zweiter Lauf bei `uncertain` und keine Änderung bestehender Freigaben.
Der Zeitpunkt der Veröffentlichung wird nicht als feste Uhrzeit angenommen.

Mit einer Version, die `doctor` enthält, in der Konsole des **bestehenden Helfers**:

```sh
python -m eos_pv_helper doctor --config /app/config.toml
```

Der Befehl benötigt weder `--write-eos` noch `--refresh-source`; beide Flags werden
abgewiesen. Er macht **keine Netzwerkzugriffe, Abrufe, Importe oder Optimierungen**,
erzeugt keine Dateien und verändert weder Health noch `sync-state.json`. Er nimmt
ein Shared-Lock auf die bestehende `sync.lock`; während eines Sync-Zyklus meldet er
„retry later“, statt inkonsistente Dateien als Erfolg auszuwerten.

Falls der installierte Helfer den neuen Befehl noch nicht enthält: **nicht durch
Codex aktualisieren lassen**. Auf einem freigegebenen separaten Diagnose-Rechner
einen konsistenten privaten Export der vorhandenen Dateien mit demselben Befehl
prüfen; die bisherigen Reports ohne neues Deployment bleiben ebenfalls gültige
Belege. Ein neues Helfer-Image benötigt eine gesonderte Betreiberfreigabe.

Exitcodes und JSON:

- `0`, `accepted=true`: aktueller fehlerfreier Write-Sync, bestätigte Importe,
  vollständiger Preis-Kontrollhorizont, unverändert strenger SoC-Frischenachweis;
  Liefertag-/Preishash und Plan stimmen mit einem **persistierten `succeeded`-Claim**
  überein. `solution-<version>.json` ist vorhanden, hat den richtigen Start und
  Stundenabstand, mindestens 24 vollständige Steuerintervalle und endliche Kosten.
- `2`, `waiting-publication`: Bericht und vorhandener Preissnapshot bestätigen
  gemeinsam den noch unvollständigen nächsten Liefertag. **Keine GENETIC-Abnahme.**
- `1`, `blocked`: fehlende/alte/inkonsistente Artefakte, laufender Sync, fehlender
  Zukunftspreis, fehlgeschlagener SoC-Nachweis, `uncertain` oder ungültige Lösung.
  Nicht durch Ändern des States „reparieren“. Ursache diagnostizieren.

Doctor prüft die lokalen Belege; er liest nicht die aktuelle EOS-Konfiguration aus.
Sichere EOS-Einstellungen werden vom Sync vor jedem Dispatch und direkt an der
POST-Grenze überprüft. Bei einem exportierten Snapshot bezieht sich die Frischeprüfung
auf dessen Erhebungszeit, nicht auf einen Tage später erneut ausgeführten Doctor.
SHA256-Werte im JSON identifizieren die Dateien. Niemals ganze Konfigurationen,
evcc-Snapshots oder Secrets in öffentliche Kommentare kopieren.

Für die reale Abnahme im Issue dokumentieren: UTC-Zeit, Laufzeit-Commit/Image-Digest,
Delivery-Day/Version, 24-h-Kontrollhorizont, effektiven Tail, Claim-Status,
Doctor-Ergebnis und Hash der gespeicherten Lösung. Sicherstellen, dass der Lauf
aus dem regulären Event stammt. Das ist eine beobachtete Abnahme, keine erneute
Freigabe zum Dispatch. Erst danach Issue #1 mit diesen Belegen schließen.

## Merge und Release-Gates

1. Aktuellen PR-Stand lokal und in CI prüfen: Ruff, Unit-/native EOS-Integration,
   Compose, sicheres Vollimage und netzloser Unraid-Smoke-Test. Review abschließen;
   kein `Closes #1`, solange der reale Nachweis fehlt.
2. Lizenzreview am **konkreten Kandidaten**: `LICENSE`/Paketmetadaten (MIT nur eigener
   Code), EOS Apache-NOTICE, Python-/Debian-/Vendor-Lizenzen und LGPL-Quellarchive.
   [Lizenzinventar und Grenzen](../THIRD_PARTY_NOTICES.md). CI stellt das tatsächlich
   installierte Inventar als Artefakt bereit. Ungeprüfte native Bibliotheken und
   deren Quellpflichten sind ein Release-Blocker, kein automatisch grüner Haken.
3. `GENETIC_ACCEPTANCE.json` erst mit echtem, anonymisiertem Doctor-Beleg,
   Abnahmekommentaren, akzeptiertem Runtime-Commit sowie expliziter Betreiber- und
   kandidatenspezifischer Lizenzfreigabe ergänzen. `pending` ist absichtlich rot.
   Den SHA256-Hash der **exakten `inventory.json`-Datei** übernehmen, nicht ihres
   neu serialisierten JSON-Inhalts. Keine privaten Daten/Secrets übernehmen.
4. Erst danach Draft entfernen und PR #3 nach `main` mergen. Angeforderte
   Merge-/Release-Freigabe auf den konkreten grünen Commit beziehen. Aktuell wird
   dieser Schritt nur vorbereitet, nicht ausgeführt.
5. SemVer: erster stabiler Stand `v0.1.0` (Projektversion 0.1.0); spätere Bugfixes
   PATCH, kompatible Funktionen MINOR, Vertragsbrüche MAJOR. Keine stabilen Tags auf
   Vorschau-Branches, keine Wiederverwendung einer Version mit anderem Digest.
6. Erst freigegebenen, gemergten Commit taggen. Die Pipeline prüft den realen
   Abnahmebeleg, die geschlossene #1 und Zugehörigkeit zu `main`. Sie baut zunächst
   **nur `sha-<commit>`**, prüft anonymen Pull, OCI-Revision, netzlosen Smoke-Test
   und den Lizenzinventar-Hash. Erst anschließend wird derselbe Digest auf
   `v0.1.0`/`latest` promotet. Ein fehlgeschlagener Kandidat bewegt kein `latest`.
7. GitHub-Release mit Digest, CI-/Abnahme-Links, Lizenzinventar und Änderungen
   veröffentlichen; Template auf verifizierten stabilen Stand umstellen. Ein
   erfolgreicher Image-Push allein ist noch kein abgeschlossener GitHub-Release.

Ein geändertes Abhängigkeitsinventar bei einem Neubau erfordert ein neues Review,
auch bei unverändertem Projektcode. Es gibt keine pauschale MIT-Freigabe aller
EOS-/Python-/OS-Abhängigkeiten. Noch kein `v0.1.0` oder `latest` wird hier behauptet.

## Unraid-Update und Rollback nach Freigabe

Der Betreiber aktualisiert ausschließlich den Helfer über Docker → Check for
Updates → Update/Apply. „Check for Updates“ installiert nicht automatisch. Bei
Digest-Pinning muss die Repository-Angabe bewusst angepasst werden; eine gepinnte
Vorschau wird nicht automatisch zu `latest`.

Vorher eigenen Repository-Digest, Startargumente/Mounts und konsistente private
Sicherung festhalten. `config.toml`, Secret-Dateien, Cache, **`sync-state.json` und
`solution-*.json`** bleiben erhalten; keine Appdata-Neuinitialisierung. Nach Update
Image-Revision, Modus, Health und Doctor kontrollieren. Rückweg: vorherigen
verifizierten Digest wieder im bestehenden Helfer eintragen und Apply. Keine
Rücksetzung von Claims und kein zweiter Helfer mit demselben Output. Ein Downgrade
darf niemals ein bereits ausgeführtes oder ungewisses Event erneut auslösen.
EOS, evcc, HA und E3/DC bleiben unverändert.

## Noch offen

- Reale automatische GENETIC-Lösung plus nachvollziehbarer Doctor-/Artefaktbeleg.
- Kandidatenspezifische Prüfung aller Fremdlizenz-/Quellpflichten und Betreiberfreigabe.
  Konkret offen: passende GCC-/libquadmath-Quellen der mit SciPy gebündelten
  Bibliothek; das SciPy-sdist allein genügt hierfür nicht.
- Danach Issue #1 schließen, Review/Draft/Merge und tatsächlicher stabiler Release.
- **Erst danach** Issue #5: [konkreter Umsetzungsplan](ISSUE_5_PLAN.md).
