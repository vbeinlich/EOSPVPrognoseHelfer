# MaxxiCharge: vorläufiger Abschluss und Übergabe

Die Entwicklungsphase endet nach der gezielten Diagnose. Die Datenaufbereitung
für historische und fortlaufende Messwerte bleibt erhalten. Es wird keine weitere
MaxxiCharge-Funktion und kein neuer produktiver Steuerpfad implementiert.

## Abschlussdiagnose reproduzieren

Die privaten Originale, der vorbereitete Datensatz und die bereits gerechneten
13 Szenarien bleiben eingefroren. Der folgende Diagnosebefehl liest sie und
schreibt ausschließlich in ein neues privates Verzeichnis:

```sh
python scripts/diagnose_ems_comparison.py \
  --prepared /PRIVATE/prepared/prepared.json \
  --simulation-dir /PRIVATE/simulation \
  --hourly-source /PRIVATE/joined/joined.csv \
  --output /PRIVATE/final-diagnosis-new
```

Ergebnisse: `baseline-hourly.csv`, `storage-comparison.csv`, `diagnosis.json`,
`report.md` und abschließendes Prüfmanifest. Die Messdaten und finanziellen
Detailergebnisse bleiben privat. Der Eingang wird mit seinen Quellhashes und
der gespeicherten Simulation abgeglichen. Zeitreihen müssen exakt zusammenpassen;
es gibt keine passende Zeitverschiebung, Summenkorrektur oder Parameterschätzung.

Die produktive Architektur wird separat ausschließlich lesend inventarisiert.
Ein fehlender Zugriff wird als Nachweisgrenze dokumentiert, nicht durch neue
Zugangsdaten, Rechteänderungen oder Containerneustarts behoben.

## Was die Kostendiagnose belegt

Pro Stunde wird die Kostenabweichung als Identität zerlegt:

```text
C_sim − C_ist
  = G_sim × (p_sim − p_eff_ist)
    + p_eff_ist × (G_sim − G_ist)

G_sim − G_ist
  = ΔLast − ΔPV + ΔEinspeisung + ΔBatterieladung − ΔBatterieentladung
    + Bilanzrest_sim − Bilanzrest_ist
```

Dabei sind G und alle Energien in kWh, Preise in EUR/kWh. Im CSV bleiben Energien
in Wh und die Umrechnung wird genau einmal vorgenommen. Die Summe der Beiträge
muss jede einzelne Kostenabweichung schließen. Diese Buchhaltungsidentität ist
kein Nachweis voneinander unabhängiger physischer Ursachen. Ein SoC-Effekt darf
nicht nochmals zu den Batterieflussbeiträgen addiert werden.

Zusätzlich werden der Mengeneffekt zum beobachteten Durchschnittspreis und die
Verteilung auf unterschiedlich teure Stunden getrennt. Ein Nullbeitrag für den
angewandten effektiven Stundenpreis beweist keine korrekte Viertelstundenbewertung
alternativer Bezugsprofile: dieser Preis stammt aus gemessenen Kosten/Bezug.
Die vorhandene alternative Stundenreihe wird nur als ausdrücklich benannte
Sensitivität gerechnet, niemals als Korrektur übernommen. Zeitliche Zuordnung
unterhalb des Originalrasters bleibt ohne feinere Quellen unbekannt.

Batteriezähler werden außerdem unter den unveränderten Kapazitäts-, Reserve-
und Wirkungsgradannahmen bilanziert. Eine unphysikalische rechnerische
Speicherenergie ist ein Konflikt zwischen Messgrenze, Zeitbasis und Modell,
keine Behauptung über den tatsächlichen Speicherinhalt. Keine Wirkungsgrade
werden an Kosten oder veraltete SoC-Werte angepasst.

## A/B und fairer Speichervergleich

Ein expliziter Diagnose-Vorwärtslauf schaltet nur die bestehende Preis-Halteregel
aus. Bei deaktivierter E3/DC-Koordination muss B damit A reproduzieren. Der
Versuch erklärt den Unterschied der gespeicherten Heuristiken und ist keine
Änderung ihrer produktiven oder ursprünglichen Konfiguration. Cash-Nachteil,
zusätzlicher Endenergiewert und Abregelung werden getrennt ausgewiesen.

Der ursprüngliche Paketmehrwert wird unverändert übernommen. Die ursprüngliche
PV-only-Konfiguration besitzt jedoch ein anderes AC-Limit als das Speicherpaket.
Ein zweiter, klar getrennter Diagnosevergleich setzt ausschließlich die bereits
existierende PV-only-AC-Grenze auf das Limit des Speicherpakets. Gleiche PV,
gleiche E3/DC-Steuerungsart, gleiche Anfangsbedingungen und dieselbe Endbewertung
erlauben dann eine besser kontrollierte Speicherzuordnung. Die realen
Wechselrichtertopologien sind damit weiterhin nicht nachgewiesen.

A/B nutzen die autonome PV-only-Referenz, C eine ebenfalls ideale PV-only-Referenz.
Der Optimierungsvorteil des E3/DC-Bestands wird nicht zusätzlich dem Speicher
zugeschlagen. Die 13 Originalfälle werden nicht ersetzt; Referenzexperimente
erhalten eigene Konfigurationshashes und den Status `diagnostic_only`.

## Wirtschaftliche Grenze

Paketpreis und isolierter Speicheraufpreis sind verschieden. Solange ein
vergleichbares PV-only-Angebot und die tatsächliche AC-Topologie fehlen, ist
der Speicher-CAPEX-Aufpreis unbekannt. Weitere PV-/Montage-/Gerätemehrkosten
dürfen nicht als null behandelt werden. Ein positiver Modellnutzen in fünf
Novembertagen ist kein Nachweis einer Jahresrendite oder Amortisation.

Ergebnisse bleiben vorläufig: SoC-Zeitstempel, die zwei Stunden über der
unveränderten 50-Wh-Bilanzgrenze, die E3/DC-Referenz und die hypothetische
Zusatz-PV sind getrennte offene Punkte. Keine künstliche Kalibrierung.

## Übergabe an die laufende Optimierung

Die private Bestandsaufnahme unterscheidet aktuelle GET-/Dateibelege,
historisch bestätigten Betrieb und vorhandenen, noch nicht aktivierten Code.
Folgende Reihenfolge bereitet die reale Optimierung vor, ohne sie hier umzusetzen:

1. **P0 – E3/DC-Vertrag und Messgrenzen:** tatsächlichen Netzlade-Owner,
   Kapazitäts-/SoC-Skala, Reserve, AC/DC-Grenzen und ungecachte Originalzeitpunkte
   bestätigen. Keine parallelen Writer starten. Vorhandene Netzladung von einer
   erst geplanten EOS-Gerätesteuerung unterscheiden.
2. **P0 – Beobachtbarkeit:** Health-/Sync-Status, veraltete Dashboardansichten,
   letzte reguläre Lösung und vollständige Ereignisarchive lesend abgleichen.
   Ein erreichbarer Webserver beweist keine frische oder vollständige Auswertung.
3. **P1 – Preis-/Plan-/Ist-Kette:** bestehende LUOX-Quelle weiterverwenden;
   Preisversion, Last/PV, SoC und Plan eindeutig binden. Prognosefehler von
   Modellabweichungen und tatsächlichen Ausführungsabweichungen trennen.
4. **P1 – Fahrzeuge:** beide Fahrzeugidentitäten und Ladepunkte bestätigen;
   einen WP-Lastpunkt nicht als zweites Fahrzeug zählen. SoC, Abfahrt und
   verfügbare Ladezeit ohne angenommene Kapazitäten nachweisen.
5. **P1 – M-TEC:** bestehende Anforderung, elektrische Aufnahme, Verdichter,
   Temperaturen und Komfortgrenzen getrennt beobachten. Potenzial für günstige
   Wärmebereitstellung anhand dieser Daten prüfen, ohne Sollwerte zu ändern.
6. **P2 – Entscheidung absichern:** repräsentative längere Historie, vergleichbare
   Angebote und robuste Szenarien liefern den späteren Investitionsvergleich.

Home Assistant bleibt Integrations-/Historienebene. Bestehende Datenpfade und
Owner werden zuerst inventarisiert; es entstehen hier keine neuen Automationen,
Provider oder Features. Freigaben für Installation, Neustarts, Merge und
Geräteaktionen sind nicht Bestandteil dieses Abschlussauftrags.
