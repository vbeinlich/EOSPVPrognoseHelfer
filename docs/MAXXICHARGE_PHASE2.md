# Phase 2 – Herstellergrenzen und historische Wirtschaftlichkeit

Arbeitsstand 16.11.2026. Grundlage ist Phase 1, jetzt separat als Commit
`a4251a6` erhalten (825 bestandene Tests laut damaligem Abnahmebericht).
Bestandsergebnis: vier Szenarien, kein 2-kWp-PV-ohne-Speicher-Fall, nur zwei
24-h-Prognose-Replays vom Oktober. Die 120-stündige HA-Auswertung war in diesem
Checkout nicht umgesetzt. Batteriephysik, PV-Modell, Validatoren und Renderer
werden weiterverwendet, keine neue produktive Steuerung.

## Vom Betreiber weitergegebene Herstellerbestätigung

Quelle: ausdrückliche Angaben des Betreibers im Auftrag vom 16.11.2026 über die
Antwort von Maxxisun. Keine unabhängige Prüfung einer konkreten Firmware und
kein Ersatz für ein gerätespezifisches MQTT-Register-/Topic-Verzeichnis.

| Bestätigt | Konsequenz im PoC |
| --- | --- |
| Parallelbetrieb mit E3/DC grundsätzlich möglich | Kein generelles Ausschlusskriterium; Wechselwirkungen zweier Regler bleiben zu untersuchen |
| Lokale MQTT-Telemetrie | Abstrakte lokale Telemetrieschnittstelle; weiterhin kein Hardwaretransport |
| Lade-/Entlade- und SOC-Grenzen firmwareabhängig veränderbar | Modell B verwendet Grenzen, keine exakten Leistungsbefehle; konkrete Firmwarebereiche offen |
| Keine direkte Vorgabe exakter Entladeleistung | Exakte Dispatchwerte ausschließlich interne Modellgrößen / theoretisches Idealmodell |
| Automatische Regelung über kompatiblen Smart Meter am Hausanschluss | A/B setzen im Modell einen solchen Zähler voraus; kein bestätigtes reales kompatibles Meter vorhanden |
| AC-Netzladung grundsätzlich möglich, externer Start/Stopp nicht verbindlich bestätigt | Aus Standardvergleichen ausgeschlossen; nur eigene optionale Annahmevarianten |
| Keine offiziell unterstützte virtuelle Smart-Meter-Quelle aus E3/DC | Kein E3/DC→virtueller-Meter-Adapter; internes Simulationsmodell ist kein unterstützter Hardware-Messpfad |
| Bis 3 kWp Süd-PV je M-5.0 V2+ | 2-/3-kWp-Fälle ein Eingangsgerät; 6-kWp-Fälle benötigen mindestens zwei geeignete Eingänge/Geräte |
| 5 kWh je Block, modular erweiterbar | 5-/10-kWh-Szenarien explizit als ein/zwei Blöcke |

## Weiterhin Modellannahmen

800 W gemeinsames AC-Ausgangslimit für PV und Batterie, 92 % Wirkungsgrade,
SOC-Reserve, Ladegrenzen, Leistungsreaktion, Mess-/Regelverzögerung, Aufteilung der
zusätzlichen PV auf Südhütte/Südzaun und deren Ertrag sind keine neuen
Herstellerbestätigungen. Ein 6-kWp-System mit zwei 5-kWh-Blöcken beweist noch
nicht die konkrete AC-/MPPT-Topologie. Einstellwerte werden im Report ausgewiesen.
Der tatsächlich vorhandene inexogy-Zähler ist nicht als kompatibler
MaxxiCharge-Regelzähler nachgewiesen.

## Umsetzung

- A: zwei unabhängige, begrenzte Rückkopplungsregler am gemeinsamen simulierten
  Netzpunkt. Reaktionsparameter sind Sensitivitätsannahmen. Überschwingen und
  unbeabsichtigte Batterieeinspeisung werden ausgewiesen; kein garantiertes
  Hersteller-Regelverhalten behauptet.
- B: EMS setzt SOC-/Leistungsgrenzen; Leistung entsteht im internen Regler.
  E3/DC-Koordination ist eine gesonderte konfigurierbare Modellfähigkeit.
- C: ideale freie Steuerbarkeit mit gleichen Energie-/Leistungsgrenzen und
  perfekter Kenntnis der Eingangsreihe, ausschließlich theoretischer Vergleich.
  Optimierungsstatus und Schranke werden getrennt vom ausführbaren Modellwert
  dokumentiert. Kein Hardwarebefehl folgt aus einem Optimierungsergebnis.
- 2/3 kWp jeweils mit und ohne 5-kWh-Maxxi, 6-kWp-Fälle beibehalten. Netzladung
  nur optionale separate Varianten. Speichermehrwert immer gegen identische
  PV-Leistung und passend abgegrenzte Vergleichssteuerung.
- Historischer Import prüft Originalraster, Zeitzone, Einheit, Scope, Preisbasis,
  Batterie-/SOC-Grenzen und den 120-h-Zeitraum. 8./9.11. werden nicht aufgefüllt.
- 2.500 EUR PoC-Annahme; PV-only und Mehrkosten der 3-kWp-Variante separat.
  Keine Jahresamortisation aus fünf Novembertagen.

## Historischer Zugang zu Beginn

Die CSV wurde im Checkout, den vorhandenen privaten Projektordnern,
Downloads/Dokumenten/Desktop und dem früheren HA-Dashboard-Verzeichnis nicht
gefunden. Bestehende HA-API auf dem NAS antwortet 401; der vorhandene Tokenpfad
ist durch Dateirechte gesperrt. Keine Rechteänderung, kein Recorder-/WAL-SQL,
keine neue Authentisierungskonfiguration. Die vom Betreiber genannten Summen
werden bis zum Originalimport als **mitgeteilte Referenz**, nicht als gelesene
120 Messintervalle behandelt. Der genaue Importvertrag und die noch nötige
Datei werden im Runbook dokumentiert, falls der bestehende Export nicht zugänglich wird.
