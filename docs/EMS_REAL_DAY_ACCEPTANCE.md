# Erste reale 24-Stunden-Abnahme: Datenprüfung vor Modelländerungen

Fortsetzung von PR #31. Es wird kein neuer Collector, kein Scheduler und keine
zweite Datenpipeline eingeführt. Die Datenprüfung verwendet den bestehenden
PR30-Adapter, `Actuals`, die native Feststeuerungs-Wiedergabe und die bestehenden
Abnahmegrenzen. Private Zeitreihen, Kosten und Dateizugänge verbleiben im lokalen
Datenqualitätsbericht.

## Ergebnis und Reihenfolge

Die technische Datenprüfung ist durchgeführt; die erste vollständige reale
Tagesabnahme bleibt **BLOCKED / NOT_COMPARABLE**. Vorhandene Originaldaten können
mehr enthalten als ein früherer stündlicher CSV-Export. Deshalb zuerst die
autoritativ gespeicherten Reihen auf Abdeckung und Semantik prüfen, bevor eine
neue Messquelle oder eine Modellanpassung erwogen wird.

1. **Originale erhalten:** SHA256, Abfrageparameter, UTC-Bereich und Abrufzeit
   festhalten. Aktuelle Zustandswerte ersetzen keine historischen Beobachtungen.
2. **Zählerherkunft prüfen:** Ein kumulativer HA-Sensor kann ein Softwareintegral
   von Leistungswerten sein. Die Intervall-Differenz bleibt `derived_counter`;
   die vorgelagerte Leistungsintegration ist eine zusätzliche Herkunftsstufe.
   Der Quellcode des erzeugenden Sensors muss mit dokumentiert werden. Das gilt
   auch für einen Kostenzähler aus Leistung × Endkundentarif.
3. **Stundengrenzen untersuchen:** Benachbarte Residuen mit entgegengesetztem
   Vorzeichen sind ein Hinweis auf zeitliche Zuordnung, keine Erlaubnis zur
   Verschiebung. Nur ursprüngliche Beobachtungszeiten und Zählerstände können
   eine Neuaufbereitung belegen. Stunden werden nicht gegeneinander verrechnet.
4. **SoC-Zeitbezug erhalten:** Letzte Zustandsänderung, erfolgreicher Poll und
   Intervallbeginn sind verschiedene Zeitpunkte. Ein Slotwert ohne ursprüngliche
   Beobachtungszeit wird nicht auf die Slotgrenze umgestempelt. 60 Sekunden bleiben
   die bestehende Altersgrenze; keine Fortschreibung über Lücken.
   Auch den vorhandenen EOS-Messspeicher über dessen lesende API mit
   `processing=raw` prüfen: Ursprüngliche Zeitstempel bewahren, SoC-Faktor nur
   durch Einheitenumrechnung in Prozent übertragen und Quellen-/Gerätezuordnung
   separat bestätigen. Die bestehenden `Actuals.soc_at`-Regeln gelten weiter;
   ein anderer gespeicherter Zeitstempel ist nicht automatisch ein Nachweis für
   den physikalischen Erfassungszeitpunkt.
5. **Messgrenzen unabhängig klären:** Gleichheit einer Haus-/Standortbilanz
   bestätigt keine Wirkungsgrade, wenn die Hauslast selbst aus Netz, PV und
   Batterie berechnet wurde. E3/DC-PV-DC-Eingang, Batterie-DC-Bus und AC-Netzseite
   brauchen einen passenden Messstellenvertrag. Keine DC-Reihe aus AC-Werten mit
   angenommenem Wirkungsgrad erzeugen.
6. **Bestehende evcc-Historie verwenden:** Dokumentierte lesende Endpunkte
   `/api/history/energy` und `/api/history/tariffs` können Original-Slots liefern.
   Konkrete Installation, Version, Einheiten, Richtungen, Lücken, Rundung und
   SoC-Semantik müssen geprüft werden. Vollständige Slots sind noch keine
   validierte Energiebilanz; Restart-/Nachtragsintervalle können problematisch sein.
7. **Originale GENETIC-Belege:** Dateinamen und Änderungszeiten belegen nicht den
   damaligen Solver-Request. Nur lesbare Originalantworten plus passende Belege
   durch den vorhandenen Archivprüfer zulassen. Fehlende historische Belege werden
   nicht mit heutigen Preisen, Prognosen oder Konfigurationen nachgebaut.

## Kleine Offline-Korrektur der Kostenkennzeichnung

`energy_data.as_actuals` bezeichnet vorhandene Kosten-Zählerdifferenzen jetzt als
`recorded_grid_purchase_counter_eur`. Bisher wurde automatisch
`measured_grid_purchase_eur` gesetzt. Das war für einen durch Softwareintegration
gebildeten Zähler zu stark: Beobachtete Ist-Kosten sind keine unabhängig gemessene
Rechnungssumme. Beträge, Intervalle und `source_method` bleiben unverändert in
`costs` erhalten; Energie × Originalpreis bleibt ausdrücklich berechnet.

Der bestehende `Actuals`-Vertrag für ausdrücklich belegte gemessene Kosten
(`measured_grid_purchase_eur`) bleibt unterstützt. Eine automatische Höherstufung
des gemeinsamen Exports entfällt. Die Regression prüft erhaltene Gegenwerte und
Herkunft sowie die fehlende falsche Messkostenfreigabe.

## Minimales Datenpaket für genau einen Tag

* Vollständige Originalantwort und Archivbelege eines bereits vorhandenen
  24-Stunden-GENETIC-Laufs mit eindeutiger Startzeit und Steuerauflösung.
* Dieselben 24 Stunden Netzimport/-export, PV, Standortlast und Batterieflüsse;
  keine doppelte Zählung einer als Ladepunkt geführten Wärmepumpe.
* Ursprüngliche SoC-Beobachtungen an allen benötigten Grenzen, inklusive
  Anfang und Ende; Messzeit und Zustandsänderungszeit getrennt dokumentieren.
* Bestätigte AC/DC-Messstellen, Kapazität/Reserve und tatsächlicher Betriebsmodus.
  SoC unter dem archivierten Modell-Minimum oder ein abweichender Anfangszustand
  werden untersucht, nicht automatisch angepasst.
* Finale historische Endkundenpreise in ursprünglicher Auflösung. Vier
  Viertelstunden dürfen nicht durch einen importgewichteten oder einfachen
  Stundenpreis ersetzt werden, um andere Strategien zu bewerten. Gespeicherte
  Stundenpläne und Viertelstundenpreise sind ein offenes Bewertungsproblem;
  es werden keine feineren simulierten Flüsse erfunden.

Kein erneuter LUOX-Aufschlag auf Endkundenpreise. Kein Hochrechnen eines
Kurzzeitraums. Erst wenn alle Bedingungen gemeinsam erfüllt sind, darf derselbe
native Vergleich als vollständig abgenommen ausgewiesen werden.
