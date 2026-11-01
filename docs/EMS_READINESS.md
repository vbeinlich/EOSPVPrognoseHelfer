# EMS-Abschlussbericht: Review vorbereitet, Produktivsteuerung gesperrt

Stand 01.11.2026. Alle Änderungen liegen ausschließlich auf dem separaten
Integrationsbranch. Keine Original-PRs/Main gemergt, kein Release/Tag, kein öffentliches
Image, keine Unraid-/Geräteänderung und kein zusätzlicher produktiver GENETIC-Lauf.
Einzelne lokale Vorwärtsreplays und alle neuen End-to-End-Daten sind synthetisch.

## Technischer Status und Unterlagen

- [PR-Abhängigkeiten, Konflikte und konkreter alternativer Mergeplan](EMS_INTEGRATION.md).
- [Quellheads und unveränderte Release-/Freigabekontrollen](EMS_SOURCE_MANIFEST.json).
- [Historische Ist-Bestände und tatsächliche Zugriffsgrenzen](HISTORICAL_ACTUALS_INVENTORY.md).
- [Strikter Plan-Ist-Datenvertrag, Kosten-/Einheitenregeln und private Ausführung](PLAN_ACTUAL.md).
- [Wirtschaftlichkeitsbefund, Referenzgrenzen und Jahreslastbewertung](EMS_ECONOMICS_REVIEW.md).
- [Zielarchitektur und priorisierte Implementierungs-Issues](EMS_ARCHITECTURE.md).

Neu lesend bestätigt: EOS `PREDICTION`, GENETIC, keine aktiven Adapter/Notify;
`LoadAkkudoktor=11251`; evcc weiterhin 0.318.1. Die tatsächliche Zwei-EV-Zuordnung
ist noch zu bestätigen. Vorhandene native Guards gegen unvalidierte EVs,
geänderte Schnittstellen oder veralteten SoC bleiben bestehen.

## Phasen und tatsächlich erreichte Ergebnisse

| Phase | Erledigt | Verbleibende Nachweisgrenze |
| --- | --- | --- |
| 1 | Alle fünf geprüften PR-Heads kombiniert, sieben Konfliktdateien aufgelöst, CI-/Testmenge vereinigt | Kein Merge und keine Betreiberabnahme; Mergepfad bewusst offen |
| 2 | Einziger #13-Writer, sieben Originale, optionale Beobachtungs-/Request-/Parameterhashes, klare Provenienzqualität | Keine atomare Bestätigung globaler Solveroptionen; #21 offen; noch nicht produktiv aktiviert |
| 3 | Offline-Plan-Ist-Vergleich für PV/Last/Netz/SoC/Batterie/DC/Kosten, UI und strikte Datenlücken | Vollständiger normalisierter Realexport/Historienzugang noch offen; #16 |
| 4 | Bestehende private Modellvergleiche zerlegt, Endwert-/LCOS-/Lastsensitivität eingeordnet | Herstellerreferenz nicht empirisch kalibriert, keine realisierte EMS-Ersparnis; #17 |
| 5 | Quellen-/Ownerarchitektur, Prioritäten und Issues #16–#21 erstellt | Kein neuer Aktor-/Ausführungsadapter, keine Aktivierungsfreigabe |

Die reale Ledgerprüfung ist eine read-only Bestandsaufnahme, kein synthetischer
Beleg: Originaltabellen und Kategorien wurden in kurzer SQLite-Lesetransaktion
abgefragt. Ihre Proportional-/FIFO-Buchungen sind jedoch kein vollständiger
gemessener Standort-Datensatz und kein Beweis ausgeführter EOS-Steuerung.

## Qualitätsprüfungen

Die reine zusammengeführte Ausgangsbasis bestand 508 Tests bei 3 explizit
ausgenommenen echten Optimierer-Tests. Der erweiterte lokale Integrationsstand
bestand **544 Tests, 3 deselected** in 52,77 s, einschließlich der neuen gemeinsamen
Pipeline. **83 ausgewählte Tests** bestanden zusätzlich als UID 10001 mit
schreibgeschütztem Root-Dateisystem und ohne Netzwerk. Ruff (ohne Cache), Actionlint,
Compose-Validierung, JavaScript-Syntax und `git diff --check` bestanden.
Die Head-CI wird im Review-PR nachgewiesen; keine laufende oder synthetische
Prüfung ersetzt die private reale Abnahme.

Doctor (je 6 Szenarien), tatsächlicher Archiv-Writer/Altimage-Consumer (je 5 Szenarien)
und Inspector wurden im unveränderten Produktionsdigest `7e957da…` und im
eingefrorenen lokalen Kandidatenimage geprüft: UID 10001, read-only, kein Netzwerk,
keine Projektquellcode-Mounts, Quelldateien unverändert. Die separate historische
Engine bleibt SHA256 `d4d713cd53c3a94621032ea7aeb2c76b5787b96e53ec8658544ab248c896a564`.
Das integrierte Inspector-Codebundle hat SHA256
`cfec2cf17c8654c0a511042ae1aae6dc0ac875d947bb7cdb493649e1c2103d2f`;
dies ist kein Image-Digest und keine Distributionsfreigabe.
Statische Browserprüfungen kontrollieren Raster, Slotdetails, Wirtschaftlichkeit
und Plan-Ist-Anzeige ohne externe Seitenabrufe.

Neue gemeinsame Prüfung: realer #13-Writer mit gemocktem Dispatch → ursprüngliche
sieben Artefakte → historischer Doctor → nachfolgendes Waiting ohne Archivänderung →
Inspector mit belegtem Archiv → native feste Freigaben/Referenzkosten → normalisierte
synthetische Ist-Werte. Native Optimierer und HTTP werden dabei per Fail-Hook gesperrt.

Zusätzlich: Kontext-/Originalhashfehler, fehlende Angaben ohne Defaults, LUOX mit
positiven/negativen Nettopreisen, gemessene Energien statt W, negative Endpreise,
Tariflücken, grobe Intervalle ohne Verteilung, Messpunkt-/Hauslastscope, AC/DC,
SoC-Alter/Originalzeit, DST, Zukunftswerte, Privacy und niemals behauptete reale
Einsparung. Vorhandene Archive und ursprünglicher standalone Doctor bleiben kompatibel.

## Reihenfolge bis zur kontrollierten produktiven Ausführung

1. **G0 – unabhängiger Review und Mergeentscheidung:** exakten Head/CI und Weg A
   oder B freigeben. Keine Original-PRs automatisch schließen, keine doppelten Patches.
2. **G1 – Administration:** Main schützen, Required Checks/Review, unabhängiger
   Reviewer, geschütztes `public-image-release`, Bypässe begrenzen und GHCR-Rechte
   prüfen. Aktuell fehlen Main-Schutz/Rulesets/Environment. `PUBLICATION_ENABLED`
   ist nicht gesetzt; diese Sperre bleibt bestehen. Keine automatischen Freigaben.
3. **G2 – neuer privater Kandidat und Deploymentfreigabe:** neues Image mit eigener
   Digest-/Inventar-/Quellen-/Lizenzprüfung. Der eingefrorene Kandidat `47bd424`
   bleibt unverändert, enthält aber nicht diesen gesamten neuen Anwendungscode.
   Vor jedem Helfer-Neustart bestehende manuelle Ledger-/HA-Bridge-Worker beachten
   (#11); ein Imagewechsel könnte sie beenden. Keine stille Migration oder Neuinitialisierung.
4. **G3 – Archivaktivierung separat:** vorhandene privaten Backups/Originale sichern,
   keine Claims löschen. Hardlink/fsync/Private-Rechte ausschließlich in einem
   neuen privaten Testverzeichnis nach Freigabe prüfen. Dann erst Opt-in für den
   bestehenden einzigen Writer. Keine zweite laufende Helferinstanz.
5. **G4 – echte private Evidenz:** nächsten ohnehin regulären Erfolg abwarten;
   sieben Originale, Price-/PV-/SoC-/Parameterbindung, ZIP-/Manifesthash und Herkunft
   bestätigen. Waiting und Restart ohne Überschreiben prüfen; keine neue Optimierung
   erzwingen oder alte Claims zurücksetzen. Fehlende historische Belege bleiben fehlend.
6. **G5 – Mess-/Wirtschaftlichkeitsvalidierung:** #16 → #17. Endpreisvertrag,
   vollständige Standortlast, Referenzmode und AC/DC belegen. Solveroptionen/No-Device-
   Vertrag #21 schließen, bevor eine vollständige Ausführungsfreigabe behauptet wird.
7. **G6 – Geräteverträge:** #18/#19/#20, exakt ein bestätigter Owner je Gerät,
   begrenzte Intents, Rücklese-/Messbestätigung und getesteter Ausfall-/Rollbackpfad.
   Erst gesonderte Freigabe für Aktorcode, dann für einen begrenzten Gerätetest,
   anschließend gegebenenfalls für Produktivaktivierung. Kein solcher Schritt heute.

Prioritäten: P0 #12/#16/#21 plus Integrations-/Adminreview; P1 #17/#18/#19;
P2 #20 und gemeinsame Oberfläche #5. #7/#11 bleiben optionale eigene Betriebs-/
Historienarbeiten; sie werden nicht ungefragt als Worker in diesen Helfer eingebaut.

## Entscheidung

**Vorbereitet für unabhängigen Integrationsreview. Kontrollierte Produktivsteuerung:
BLOCKED bis zu den dokumentierten Daten-, Vertrags- und Betreiberfreigaben.**
Es wurde keine dafür erforderliche Produktivfreigabe angenommen oder umgesetzt.
Die bestehende Anlage und deren Dry-Run-Ablauf bleiben unverändert.
