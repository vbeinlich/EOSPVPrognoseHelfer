# Issue #5 – freigabebereiter Plan, noch keine Implementierung

Aktualisierung: Die reale automatische GENETIC-Abnahme von #1 ist nun belegt und
lesend abgeglichen ([Beleg](GENETIC_ABNAHME.md)). Weiterhin zuerst PR #3 mergen und
stabil veröffentlichen, dann #5 implementieren, anschließend #6. Die gemeinsame
Weboberfläche/Doctor-Engine ist auch Grundlage des [Savings Dashboard](ROADMAP.md);
kein paralleles zweites UI und keine vorgezogene Implementierung.

Grundlage: alle zum 29.10.2026 vorhandenen Kommentare in Issues #1, #4, #5 und
PR #3, insbesondere die [verbindliche Reihenfolge](https://github.com/vbeinlich/EOSPVPrognoseHelfer/pull/3#issuecomment-6494748299).
Vor realer GENETIC-Abnahme, Abschluss #1, Merge #3 und stabilem Release entstehen
**keine Wizard-/Skill-Implementierung und kein separater Entwicklungs-PR**.
Der vorhandene rein lesende Abnahme-Doctor gehört zum Abschluss #1.

## Architektur danach

Eigener Branch `feat/issue-5-setup-wizard-skill` vom stabilen `main`; eigener PR mit
Bezug auf #5. Zuerst gemeinsame deterministische Setup-/Doctor-Engine mit
versioniertem JSON-Vertrag und CLI, dann lokaler Wizard als Client, dann versionierte
plattformneutrale Skill unter `skills/eos-pv-helper-setup/SKILL.md`. Codex, Claude
und OpenCode verwenden dieselben Entscheidungen und Freigabeobjekte. Kein LLM im
Container und keine duplizierte Mutationslogik in UI oder Skill.

EOS und evcc sind Voraussetzungen; HA bleibt optional. Kein Installieren fremder
Stacks, keine Geräteinventur, keine direkten E3/DC-Abfragen/-Befehle, keine
Wärmepumpen-/Wallboxsteuerung. Bereits vorhandene Datenquellen und Helferdaten
werden wiederverwendet. Keine zweite Forecast.Solar-Implementierung.

## Fünf Schritte

1. EOS lesend prüfen: origin, Version, `/openapi.json`, vorhandene Provider,
   Geometrie, bestehende Sicherheitskonfiguration; unbekanntes Schema sperrt.
2. evcc prüfen: vorhandenen privaten Key verwenden; öffentliche `/api/state`-200
   beweist keine Berechtigung für geschützte Config-/Status-GETs. 401 getrennt
   erklären. Nur explizit ausgewähltes Batterie-Gerät; bestehende Freshness-Regeln.
3. Vorhandene PV-/Batterie-/Preisparameter vergleichen, native PV-TTL und
   mindestens 24-h-Präfix zeigen; historische Preisschnitte von Zukunftslücken
   unterscheiden. SoC-Mismatch maximal mit einem State-GET, niemals Timer umgehen.
4. Dry-run und einzeln nachvollziehbare Freigaben für externe Aktualisierung,
   PV-, SoC-, Preisimport und GENETIC. Jeder geänderte Plan verlangt neue passende
   Freigabe. `waiting-publication` ist normal; `uncertain` niemals automatisch retryen.
5. Dauerstatus, Diagnose-Export ohne Secrets, stabile Updates und Digest-Rollback.
   Claims und Planhistorie über Update und Migration hinweg unverändert erhalten.

## Sichere Installation und Migration

Ein bestehender Helfer genügt. Unraid-Startmodus muss in der tatsächlichen GUI
auswählbar sein; das dort unsichtbare PostArgs-Feld darf keine Hand-XML-Voraussetzung
bleiben. Dry-run-Defaults, UID/GID 10001, minimale Rechte, read-only Mounts; kein
Docker-Socket, privileged oder erzwungenes Host-Netzwerk. Die lokale Weboberfläche
muss authentifiziert sein und Host-/Origin-, CSRF- und SSRF-Schutz erhalten.
Discovery nur begrenzt und lesend mit manueller Fallback-Adresse. Gemäß bestehender
Workspace-Vorgabe ist die Bindung im Container `0.0.0.0:3000` vorgesehen; die
Veröffentlichung am Host bleibt begrenzt und die Oberfläche authentifiziert.

Secret-Dateien sicher anlegen/vorbereiten, 0600/UID 10001, read-only einbinden;
keine Schlüssel im Chat, Log, Diff, Diagnose-JSON oder UI anzeigen. Kein Key-Rotieren
oder -Erzeugen ohne ausdrücklichen Auftrag. Fehlendes `[evcc]` per strukturiertem
TOML-Plan ergänzen, mit Vorschau, privatem Backup, atomarem Austausch und
Rechteerhalt; keine sed-/Regex-Migration. Änderungen fremder Konfigurationen sind
nie Teil eines stillen Setups. Jede Mutation benutzt denselben validierten Plan
und denselben expliziten Freigabenachweis wie CLI/Skill.

## Tests und spätere Abnahme

Contract-/Parity-Tests Engine↔CLI↔Wizard↔Skill; Erstinstallation und bestehendes
Unraid-Setup, fehlende Tabelle, 401, fehlende/ungültige Secrets, Rechtefehler,
Cache-TTL/Lock, Tageslücke/DST, historischer Preisbeschnitt, veralteter/abweichender
SoC, `waiting-publication`, `uncertain` und Update/Rollback ohne Event-Wiederholung.
UI-Tests für Auth/CSRF/Origin/SSRF und Secret-Redaktion; keine Live-Gerätebefehle.
Skill enthält Voraussetzungskontrolle, strukturierte Diagnose, konkrete sichere
Kommandos, Freigabeschritte und Stop-Bedingungen, keine generischen Heuristiken.
Abschließend reale neue und bestehende Unraid-Installation nur nach gesonderter
Betreiberfreigabe. #5 bleibt bis zu dieser Abnahme offen.
