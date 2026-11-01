# Wirtschaftlichkeit: was bereits belegt ist und was noch fehlt

Bezug: PR #15, gespeicherte Lösungen vom 29.–31.10.2026. Keine neue Suche,
keine Produktionsoptimierung und keine Veränderung der Lösungen. Die vorhandenen
privaten Ergebnisse wurden für die Zerlegung wiederverwendet, nicht neu passend gemacht.

## Kleiner Modellvorteil am 31.10.

Die Zerlegung lautet exakt:

```
Mehrersparnis = (Referenz-Betriebskosten - GENETIC-Betriebskosten)
             + (GENETIC-Endwert - Referenz-Endwert)
```

Am 31.10. liegen die GENETIC-Betriebskosten höher. Die größere verbleibende
Batterieenergie erhält aber einen höheren gemeinsamen Endwert, der diese
Mehrkosten knapp übersteigt. Der kleinere modellierte Batterieverschleiß liefert
ebenfalls einen wesentlichen Teil der Differenz. Das ist eine Zerlegung des
vorliegenden Modells, kein unabhängig gemessener finanzieller Erfolg.

Die gespeicherte AUTO-/TAIL-Kurve ist die entscheidende Annahme. Der Tail ist
kürzer als angefordert; danach folgt ein aus vorhandenen Fenstern abgeleiteter
Fortsetzungswert. Dieser ist keine garantierte zukünftige Einnahme. Die einzelne
Entladestunde lag nur knapp über der lokalen Restwert-/LCOS-Schwelle. Kleine
Forecast-, Wirkungsgrad- oder Wertabweichungen können solche Entscheidungen ändern.

Fehlende Netzladung ist unter den gespeicherten Wirkungsgraden und der vorliegenden
Preisspanne plausibel: vier Wirkungsgrade werden im AC-Rundlauf berücksichtigt,
zusätzlich LCOS. Wenig PV allein macht Netz-Arbitrage nicht profitabel. Aus einer
kleinen Mehrersparnis folgt weder ein Modbusfehler noch globale Optimalität von GENETIC.

Der 29.10.-Vergleich endet mit gleichem Batterie-SoC und zeigt einen kleinen
operativen Vorteil. Für 30.10. fehlt die lesbare Originaldatei; keine Zahlen
geschätzt. Private Beträge, Originalhashes und Zerlegung bleiben lokal.

## 11.251 kWh: aktiv konfiguriert, historisch nicht rückwirkend bewiesen

Der lesende Config-GET am 01.11. bestätigt `LoadAkkudoktor=11251`. Das beweist
nicht den Jahreslastwert eines älteren Laufs. Dessen tatsächlich benutzte Lastreihe
liegt in den zurückgegebenen Parametern und bleibt maßgeblich.

Der bestehende isolierte Test multipliziert die gespeicherte Last mit `11251/8000`,
verwendet feste alte Freigaben und dieselbe Endwertkurve. Er zeigt eine Sensitivität
dieser Annahme, **keinen neuen optimierten 11.251-kWh-Plan**. Neue tatsächliche Pläne
nur beim nächsten ohnehin regulären Ereignis untersuchen. Keine historischen
Zeitreihen aus einer neu beobachteten Jahreskonfiguration rekonstruieren.

Vor Kalibrierung klären: Bedeutet der Jahreswert vollständigen Hausverbrauch
einschließlich PV-Eigenverbrauch, WP und EVs oder nur fakturierten Netzbezug?
Diese Größen sind nicht austauschbar. Gleiches gilt für evcc-Home-Power gegenüber
separaten Loadpoints. Ein Standardprofil kann WP-/EV-Zeiten nur grob abbilden.

## Referenz und Batterieparameter validieren

Die Referenz ist ein nachvollziehbarer vereinfachter PV-Eigenverbrauch, keine
bereits bestätigte Emulation der E3/DC-Firmware. Die
[Herstellerbeschreibung](https://www.e3dc.com/en/energy-management/) nennt auch
wetter-/prognoseabhängiges Laden. Tatsächlicher Modus, Reserve, Messpunkt und
weitere vorhandene Writer müssen deshalb privat bestätigt werden.

Nötig sind zusammenhängende gemessene Intervallenergien am bestätigten AC-/DC-
Messpunkt, korrespondierender SoC und nutzbare Kapazität. Kleine Kurzintervalle
bei ganzzahligem SoC eignen sich nicht, um Wirkungsgrade exakt zu bestimmen.
Längere saubere Lade-/Entladeabschnitte und Mess-/Kapazitätsunsicherheit ausweisen.
Keine Mischung einer AC-Rundlaufeffizienz mit bereits darin enthaltenen
Einzelwirkungsgraden, keine zusätzlichen Verlustkosten im Zielwert.

LCOS ist eine Verschleißannahme, keine unmittelbar gemessene Stromrechnung.
FIFO-Energieeinstandskosten im Ledger sind wiederum etwas anderes. Besonders
PV-Opportunitätskosten nicht zusätzlich verbuchen, wenn die Zielfunktion bereits
entgangene Einspeiseerlöse berücksichtigt. Unbekannte Energieherkunft nicht als
kostenlos bewerten. Die vorhandenen Ledger-Anteile sind teilweise proportional
geschätzt und ersetzen keine getrennte Batterie-Netzflussmessung.

## Empfohlene nächste Schritte

1. Originaleingaben/Modelle regelmäßig über den bestehenden Writer sichern;
   genaue globale Solveroptionen als eigenes offenes Provenienzgate behandeln.
2. Vollständigen read-only Mess-/Tarifexport prüfen. Messfehler und Forecastfehler
   getrennt von nicht ausgeführten Planabweichungen darstellen.
3. Einfaches Referenzmodell gegen bestätigte Herstellerautomatik auf **gemessenen**
   Eingaben validieren, bevor dessen Counterfactual für Einsparungen benutzt wird.
4. Danach ausschließlich freigegebene Offline-Sensitivitäten für Wirkungsgrade,
   LCOS und Endwert auswerten. Nicht Parameter ändern, um einen größeren Sparwert
   zu erzwingen; keine zusätzlichen Seeds/GENETIC-Läufe ohne Auftrag.
5. Mehrgerätepotenzial erst mit echten EV-/WP-Bedarfs- und Komfortrestriktionen
   modellieren. Die heutige reine Batteriesimulation kann deren Nutzen nicht belegen.

Aktueller Status: Modellvorteile reproduzierbar, keine nachgewiesene realisierte
EMS-Mehrersparnis. Die neue Plan-Ist-Anzeige lässt diesen Wert deshalb ausdrücklich offen.
