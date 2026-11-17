# EMS Simulation v1.2: Offline-Modellvalidierung

Stand: Entwicklungszweig auf PR #30. Keine Aktivierung, kein produktiver
30-Tage-Betrieb und keine belastbare Aussage zur realen Modellgenauigkeit allein
aus bestandenem synthetischem Replay.

## Bestandsprüfung vor der Implementierung

| Grundlage | Bereits vorhanden und wiederverwendet | Verbleibende Grenze |
|---|---|---|
| PR #15 | `economics.project/compare/account`, native EOS-Referenz, identische Geräteparameter und gespeicherte Endwertkurve | Referenz ist PV-Eigenverbrauch mit Netzladung aus; kein vollständiger proprietärer E3/DC-Regler |
| PR #22–#23 | Quellenbindung, ursprüngliche Request-/Solver-Eingaben, sichere Belegprüfung | Belegt keine tatsächliche Ausführung von Stellbefehlen |
| PR #24–#26 | Statisches EMS-Dashboard, UTC/Berlin, Historie, letzte gültige Anzeige | Anzeige löst keine Simulation aus |
| PR #27 | Native Feststeuerungs-Replays, Flussnachweis, idempotenter Worker/Katalog | Noch keine automatische Verbindung zu vollständigen Ist-Fenstern |
| PR #28 | Automatische Archivbelege und Integritätsprüfung | Fehlende historische Belege lassen sich nicht rückwirkend herstellen |
| PR #30 | Gemeinsame Messdatenaufbereitung, kumulative Zähler, Original-5-Minuten-Mittel, Messgrenzen, Bilanz-/SoC-Prüfung | Strenge Abnahme ist eine zusätzliche Voraussetzung; abgeleitete Werte bleiben gekennzeichnet |
| Issue #16 | `plan_actual.Actuals`, gemessene Intervalle, Endkundenpreise, Original-SoC-Zeitpunkte | Vollständige passende Ist-Daten müssen lokal vorliegen |
| Issue #17 | Parameter-/Wirkungsgradvertrag und unveränderliche native Quellenprüfung | Nutzkapazität, Messpunkte und tatsächlicher Betriebsmodus müssen unabhängig bestätigt werden |

Lokal nachgewiesene Daten werden im **privaten** Ergebnisbericht mit Dateihashes
inventarisiert. Haushaltsmessungen, Finanzdaten und Netzadressen werden nicht in
dieser Dokumentation oder in Testfixtures veröffentlicht. Vorhandene
November-Messungen und ältere Originalpläne allein ergeben keinen zeitgleichen,
vollständig belegten Vergleich und keinen realen 30-Tage-Datensatz.

## Ergänzungen

`python -m eos_pv_helper.ems_shadow` verbindet bestehende Funktionen:

1. Vorhandene lokale Archivkopie über `replay_worker.snapshot` prüfen. Nur
   erfolgreiche Claims mit Originalarchiv und vollständiger Bindung zulassen.
   Ablehnungen bleiben mit Grund sichtbar. Alternativ vorhandene Originaldateien
   ausdrücklich mit eingeschränkter Modell-Provenienz untersuchen.
2. Den ursprünglichen GENETIC-Lauf mit `economics.compare` exakt reproduzieren
   und die vorhandene native Eigenverbrauchsreferenz berechnen. Keine Suche,
   kein POST, keine neuen Prognosen und keine Skalierung der Last.
3. Ist-Fenster mit `plan_actual` und gegebenenfalls dem unveränderten
   PR30-Adapter prüfen. Fehlende Intervalle, unbekannte Grenzen, veralteter SoC,
   unbestätigte Anfangsbedingungen oder Bilanzverletzungen bleiben
   `NOT_COMPARABLE`. Ein unvollständiges PR30-Export bleibt als Audit sichtbar;
   es wird nicht an dessen strenger Exportprüfung vorbeigeführt.
4. Nur bei vollständigen Ist-Eingängen dieselbe native Engine zweimal mit
   gemessener Last, gemessener DC-PV und finalen Originalpreisen ausführen:
   Referenz B und unveränderte archivierte Steuerfolge C. Letzteres ist eine
   Sensitivität auf tatsächlich eingetretenes Wetter/Last, keine rückwirkende
   Optimierung und kein nachgewiesener Regelbetrieb.
5. Unveränderliche Ergebnisse unter `records/<Eingangshash>.json`, atomarer
   Bericht `report.json`. Schlüssel bindet Originalbytes, Archivbelege,
   Ist-Daten, Kalibrierungsnachweise, Code, native Quellen und Abhängigkeiten.
   Wiederholungen verwenden vorhandene Ergebnisse. Defekte Einträge werden
   abgelehnt; native Fehler werden beim nächsten Aufruf erneut versucht.

Es gibt keine zweite Physik-Engine, keinen neuen Datenabruf, keine neu installierte
Zeitsteuerung und keine Änderung des produktiven Compose-Stacks. Der vorhandene
Audit-Guard des Replay-Workers blockiert Netzwerk- und Unterprozessaktionen im
CLI vor dem nativen Import. Für den regulären Offline-Betrieb ist zusätzlich
die vorhandene isolierte Entwicklungsumgebung mit schreibgeschützten Quellen,
ohne Netzwerk und mit separatem privatem Ausgabeverzeichnis zu verwenden.

## Messgrenzen und Kalibrierungsnachweise

Die native EOS-PV-Reihe liegt am **DC-Eingang des Wechselrichters**. Der bisherige
Ist-Vertrag enthält `pv_wh` als AC-Messung. Diese Größen dürfen nicht ungeprüft
verglichen werden. Der bestehende Ist-Vertrag unterstützt ergänzend
`pv_dc_wh` mit `origin.pv_dc_basis="inverter_input_dc"`, ausschließlich wenn diese
Größe aus einem belegten vorhandenen Export stammt. Es wird keine DC-Reihe aus
AC-PV mit einem angenommenen Wirkungsgrad erzeugt. Fehlt diese Eingangsgröße,
bleiben Modellvalidierung und Ist-basierter Strategievergleich gesperrt.

`battery_charge_dc_wh` und `battery_discharge_dc_wh` liegen am DC-Bus vor den
Zellverlusten bzw. nach den Entladeverlusten. Die AC-Standortbilanz berücksichtigt
die ausdrücklich bestätigten Wechselrichterwirkungsgrade. Die Grenze bleibt
50 Wh pro Stunde; feinere Originalintervalle erhalten nur das anteilige Budget.
Keine Verrechnung schlechter Stunden mit guten Stunden.

SoC wird nur an seinem Originalzeitpunkt verwendet, höchstens 60 Sekunden alt,
nie aus der Zukunft. Anfangs-SoC muss zum archivierten Start passen (0,1
Prozentpunkte numerische Vergleichstoleranz). Kapazität, Reserve, maximale
Lade-/Entladeleistung (im nativen Vertrag gemeinsame Batteriegrenze), Lade- und
Entladewirkungsgrad sowie AC-Grenzen werden im Ergebnis unverändert ausgewiesen.
Die nutzbare Energie folgt dem vorhandenen Kapazitäts-/Reservevertrag; keine
automatische Anpassung an gemessene Kostensummen.

Ein privater `--conditions`-Beleg bindet folgende Felder:

```json
{
  "actuals_sha256": "<SHA256 der Original-Ist-JSON-Bytes>",
  "model_parameters_sha256": "<ems_shadow.model_parameters(project(original))>",
  "evidence_sha256": "<SHA256 des unabhängigen Kalibrierungsbelegs>",
  "meter_boundaries_confirmed": true,
  "usable_capacity_confirmed": true,
  "standard_mode_confirmed": true
}
```

Zusätzlich muss der Ist-Export den Hersteller-Standardbetrieb bestätigen. Diese
Operator-Angaben sind dokumentierte Voraussetzungen, kein automatisch erzeugter
physikalischer Nachweis. Historische Archivbindung kommt separat aus dem
bestehenden Archivprüfer. Netzladung im Ist-Betrieb kann die Eigenverbrauchsreferenz
ungeeignet machen; die Bestätigung des passenden Betriebsmodus darf dann nicht
gesetzt werden. Es werden keine Parameter an Vergleichssummen angepasst.

Für laufend ergänzte Exporte darf der Beleg statt der einzelnen
`actuals_sha256` die stabile `measurement_mapping_sha256` des bereits geprüften
Messvertrags binden. Der Ist-Export muss dieselbe Mapping-ID in
`origin.measurement_mapping_sha256` oder im vorhandenen
`measurement_preparation.mapping_sha256` tragen. Neue Messwerte benötigen dann
keine erneute Bestätigung unveränderter Hardware/Messgrenzen. Geänderte Mappings
oder Modellparameter verlieren die Freigabe; die Originalbytes jedes Exports
bleiben trotzdem separat im Cache-Schlüssel gebunden.

Batterieverluste im Ist-Betrieb werden nur mit bestätigter Kapazität und frischen
SoC-Endpunkten aus `DC-Ladung − DC-Entladung − ΔSpeicherinhalt` abgeleitet und als
solche bezeichnet. Native Batterie- und Wechselrichterverluste sind unterschiedliche
Größen; die vorhandene Gesamtsystem-Verlustreihe bleibt unverändert. Fehlende
Nachweise ergeben keinen künstlichen gemessenen Verlustwert.

## Kosten und Fehlerzuordnung

* A: Gemessene Bezugskosten nur aus optionalen originalen `costs`-Intervallen mit
  `grid_cost_eur` und `origin.cost_basis="measured_grid_purchase_eur"`. Separat:
  gemessener Import × passender finaler Originalpreis. Letzteres wird ausdrücklich
  als berechnet bezeichnet. Abweichungen beider Größen sind pro Stunde sichtbar;
  über 1 Cent bleibt die Vergleichsfreigabe gesperrt.
* B/C: Bezug, Einspeiseerlös, Verschleiß, Betriebskosten und dieselbe historische
  Batterie-Endwertkurve separat. Die Einspeisevergütung stammt aus dem Originalplan
  und gilt nicht als bestätigter tatsächlicher Erlös. Ein wirtschaftlicher
  Gesamtkostenvergleich A gegen B/C braucht zusätzlich die bestätigte
  Einspeisevergütung (`feed_in_tariff_confirmed` im gebundenen Beleg), sofern
  tatsächlich eingespeist wurde. A erhält denselben gespeicherten Batterie-Endwert
  und denselben Verschleißansatz wie B/C; diese Bewertung ist ausdrücklich keine
  gemessene Gesamtrechnung. Ohne bestätigte Vergütung bleibt der Gesamtkostenvergleich
  A gegen C gesperrt. Bei null Einspeisung ist der Erlös unabhängig vom Tarif null.
* LUOX-Vertrag: `(Nettobörsenpreis + 0,03 × abs(Nettobörsenpreis) + fixe
  Nettobestandteile) × 1,19`. Die bestehende Funktion
  `tariff_audit.luox_end_price_audit` prüft belegte Komponenten. Finale historische
  Endkundenpreise werden unverändert verwendet. Keine zweite Preisquelle und
  kein erneuter Aufschlag. Fehlen die Nettobestandteile, bleibt die Vertragsprüfung
  offen, statt sie aus einer Kostensumme zu rekonstruieren.
* Keine importgewichtete Preisaggregation für andere Strategien: Ein nativer Slot
  braucht einen ihn vollständig abdeckenden Originaltarif. Feinere Tarife erfordern
  bereits passend archivierte native Steuerintervalle; es wird nichts umgerastert.
  Der gemeinsame Ist-Export erhält die ursprünglichen Qualitätsmethoden und
  Kosten-Zählerdifferenzen. Aus tatsächlichen Kosten/Import abgeleitete effektive
  Preise bleiben für Ist-Kosten lesbar, werden für hypothetische Strategien aber
  ausdrücklich gesperrt (`import_weighted_tariff_not_strategy_price`).
* Damalige PV-/Lastprognose minus passende Messung: **Prognosefehler**.
  Ursprünglicher Plan gegen Ist-Netz-/Batteriefluss: **Szenarioabweichung**, kein
  nachgewiesener Modellfehler. Referenz mit Ist-Eingängen gegen belegten tatsächlichen
  Standardbetrieb: **Modellabweichung unter den dokumentierten Annahmen**.
  Nicht gemessene AC-PV-Ausgabe der nativen Simulation wird nicht erfunden.

## Reproduzierbarer Offline-Ablauf

In einer vorbereiteten nativen EOS-Testumgebung auf der bereits gepinnten
Revision aus `economics_native.EOS_REVISION`:

```sh
mkdir -m 700 /tmp/ems-shadow-output
python -m eos_pv_helper.ems_shadow \
  --source /input/existing-helper-archive-copy \
  --actuals /input/existing-plan-actual.json \
  --conditions /input/calibration-evidence-binding.json \
  --as-of 2026-11-17T00:00:00Z --output /tmp/ems-shadow-output
# Alternativ: --solution /input/original.json (Modell-Provenienz eingeschränkt)
# Alternativ zu --actuals: --prepared /input/existing-prepared.json

python -m eos_pv_helper.dashboard \
  --source /input/existing-helper-archive-copy \
  --ems-shadow /tmp/ems-shadow-output/report.json \
  --destination /tmp/existing-private-dashboard

pytest -q -m 'not genetic_execution' \
  tests/test_ems_shadow.py tests/test_plan_actual.py \
  tests/integration/test_ems_shadow_native.py tests/integration/test_economics_native.py
```

Exit 0: alle untersuchten realen Horizonte vergleichbar; Exit 2: sichtbare
`NOT_COMPARABLE`- oder synthetische Ergebnisse; Exit 1: Job-/Eingangsfehler.
Ein externer Aufrufer kann denselben Befehl regelmäßig auf einer lokalen,
schreibgeschützten Archivkopie ausführen; es wird hier kein Scheduler aktiviert.
Dashboards lesen nur fertige Berichte und starten niemals Replays. Fehlerhafte neue
Berichte erhalten die letzte gültige Anzeige mit sichtbarem Fehlerstatus.

24 h / 7 / 30 Tage sind exakt 24 / 168 / 720 UTC-Stunden, auch über Berlin-DST.
Nur ganze Kontrollhorizonte innerhalb des Fensters werden mit maximaler
überschneidungsfreier Abdeckung ausgewählt. Teilhorizonte, Tail und überlappende
Kosten werden nicht addiert. Lücken führen zu `NOT_COMPARABLE`, nicht zu einer
hochgerechneten Ersparnis. Synthetische und reale Horizonte werden nicht gemischt.
Auch vollständige Abdeckung ist eine Summe unabhängiger Startzustände und **kein
nachgewiesener kontinuierlicher 30-Tage-Regelbetrieb**. Jahresrenditen aus kurzen
historischen Zeiträumen werden nicht berechnet.

## Nächste Datenarbeit (keine Feature-Implementierung)

1. Zeitgleiche Originalarchive, Ist-Intervalle und finale LUOX-Tarife für mindestens
   einen vollständigen Tag, danach 7/30 Tage lokal verfügbar machen.
2. Originale SoC-Beobachtungszeiten und gemessene AC/DC-Grenzen bestätigen;
   DC-PV-Eingang bzw. einen unabhängig validierten Messgrenzenvertrag klären.
3. Nutzkapazität/Reserve, Lade-/Entladeleistung, Wirkungsgrade und Eigentümer der
   Netzladung unabhängig belegen. Standardbetrieb von zeitweisen Netzladevorgängen
   unterscheiden.
4. Erst danach reale Modellgenauigkeit und hypothetische EOS-Vorteile beurteilen.
   Ein positiver synthetischer 30-Tage-Test belegt nur Softwarefunktion und
   Wiederholbarkeit. Produktiven Shadow-Mode, Gerätebetrieb und Deployment separat
   freigeben lassen.
