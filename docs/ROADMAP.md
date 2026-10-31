# Nächste Entwicklungsphase: Nutzen nachvollziehbar machen

**Phase 2 im separaten Review:** [nativer Offline-Wirtschaftlichkeitsvergleich](ECONOMICS_COMPARISON.md)
auf PR #14. Gespeicherte GENETIC-Freigaben werden ohne neue Optimierung gegen
PV-Eigenverbrauch verglichen. Identische historische Endwertkurve, sichtbare
Kostenzerlegung und explizite Datenlücken. Kein produktives Deployment und keine
realisierte Ersparnisbehauptung; private Abnahme aller drei Oktober-Pläne bleibt offen.

**Betreiberpriorität 31.10.2026:** [Issue #6 Phase 1 – statischer Plan-Inspector](PLAN_INSPECTOR.md)
darf jetzt unabhängig von Wizard #5 und stabilem Release in einem eigenen Review-PR
vorbereitet werden. Keine Phase-2-Simulation, kein Dauer-Webserver und keine
Produktionsänderung. Die folgende Reihenfolge gilt weiter für die vollständige
integrierte Savings-GUI und die gesonderten Releasefreigaben.

Verbindliche Betreiberreihenfolge vom 29.10.2026:

1. **Issue #1:** endgültige Abnahme und Abschluss. Reales automatisches GENETIC-
   Ergebnis liegt vor; [Belege und Doctor-Abgleich](GENETIC_ABNAHME.md).
2. **PR #3 ist gemergt** (`55e1bd8`). Nächster Schritt ist ausschließlich die
   [v0.1.0-Release-Vorbereitung](RELEASE_0_1_0_READINESS.md) in eigenem Branch/PR,
   danach gesonderte Betreiberfreigabe und erster stabiler MIT-Projektrelease.
   [Gates](RELEASE_CHECKLIST.md) bleiben erhalten;
   weder ein grüner Test noch Issue-Abschluss ersetzt eine Releasefreigabe.
3. **Issue #5:** gemeinsame deterministische Engine/JSON-CLI, abgesicherter lokaler
   Web-Wizard und plattformneutrale KI-Skill. [Konkreter Plan](ISSUE_5_PLAN.md).
4. **Issue #6:** [Savings Dashboard](https://github.com/vbeinlich/EOSPVPrognoseHelfer/issues/6),
   eigener PR nach #5, auf derselben Weboberfläche und Doctor-/Status-Engine.

Bis dahin keine vorgezogene Wizard- oder vollständige Savings-Dashboard-Implementierung.
Ausgenommen ist die ausdrücklich freigegebene statische Phase-1-Planübersicht. Der produktive
Helfer bleibt unverändert; vorhandene Pläne werden lesend ausgewertet, keine
neuen Produktionsoptimierungen für Benchmarks ausgelöst.

## Was Issue #6 tatsächlich nachweisen soll

Eine erzeugte Lösung ist der technische Ausgangspunkt. Entscheidend wird der
verständliche Vergleich: Was hätte der normale PV-Eigenverbrauchsbetrieb gekostet,
was kostet GENETIC im selben Modell, und wie groß ist die zusätzliche Nettoersparnis?
`result.total_costs=2.687513895312027` € der jetzigen Lösung ist **kein Sparbetrag**.
Bis ein gültiger Referenzlauf existiert, zeigt die Oberfläche „nicht berechnet“.

Zuerst prüfen, wie die bestehende EOS-Simulationsengine einen reproduzierbaren
Referenzlauf unterstützt. Keine zweite vollständige Batterieengine entwickeln.
Default-Referenz: PV-Überschuss lädt die Batterie, Hausbedarf wird daraus gedeckt,
keine preisabhängige Netzladung. Das ist ein transparentes Modell des normalen
E3/DC-Betriebs, keine Behauptung über identische proprietäre Firmwarelogik.
Ein Szenario ohne Batterie darf den Hauptvergleich nicht ersetzen.

Beide Szenarien brauchen identische versionierte Eingaben: Start-SoC, nutzbare
Kapazität/SoC- und Leistungsgrenzen, Wirkungsgrade, PV, Hauslast, Preise,
Einspeisevergütung, Zeitraster und Modellversion. Vorhandene gespeicherte Lösung
und deren Parameter bevorzugt wiederverwenden; Herkunft/Vollständigkeit prüfen,
keine heutigen Daten still in einen älteren Benchmark mischen.

Endenergie fair behandeln: entweder denselben End-SoC herstellen oder denselben
nachvollziehbaren Endwertansatz für beide Szenarien benutzen. 24-h-Kosten und den
zusätzlichen Tail getrennt ausweisen; Verluste, Verschleiß und Terminalwert nicht
doppelt verrechnen. Gleiche Eingaben erzeugen denselben Referenzlauf; GENETIC ist
heuristisch und wird nicht als global optimal bezeichnet.

## Gemeinsame Oberfläche und Abnahme

Die Oberfläche aus #5 erhält einen Vergleichsbereich mit Referenzkosten,
GENETIC-Kosten und zusätzlicher Nettoersparnis in € und %. Zeitachsen beginnen am
tatsächlichen Planstart (hier 13:00 MEZ), mit Europe/Berlin und korrektem DST.
Diagramme zeigen Preise, PV, Last, Netzbezug, SoC und Batterieflüsse; Kostenzerlegung
und fehlende Daten/Modellunsicherheiten bleiben sichtbar. Kein separates zweites UI.

Tests prüfen bekannte synthetische Fälle, gleiche Anfangs-/Endbedingungen,
Zeitachsen/DST, Einheiten, negative Preise, Verluste/Verschleiß/Terminalwert,
fehlende Inputs sowie unveränderten Sync-/GENETIC-Idempotenzzustand. Ergebnisse
und Annahmen werden unabhängig von `sync-state.json` versioniert gespeichert.
Anzeigen dürfen nie einen POST, Gerätebefehl oder impliziten neuen Lauf auslösen.

„Prognostizierte Mehrersparnis“ bleibt klar getrennt von „realisierter Ersparnis“.
Letztere benötigt reale Messdaten und eine tragfähige kontrafaktische Referenz.
7-/30-/90-Tage-Backtests erst mit vollständiger Historie; ohne Referenz keine
erfundenen Sparwerte. Produktive Änderungen benötigen weiterhin ausdrückliche Freigabe.
