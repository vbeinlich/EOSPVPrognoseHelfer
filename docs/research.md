# Recherche und Entscheidung — 28.10.2026

## Ausgangsbefunde vor Implementierung

Das Live-OpenAPI-Schema der Installation wurde per GET gelesen und bestätigt
`v0.3.0.dev2602241646141478`. Aktiv sind `PVForecastImport` und Wetteranbieter BrightSky.
PV-Importdatei und Import-JSON sind ungesetzt, die rohe PV-Reihe ist leer. Wetterwerte
sind vorhanden. Im aktuellen evcc-Status gibt es Preis-, aber keine Solarprognosen.

Der Betreiber hat Forecast.Solar als frühere Quelle bestätigt: 26 Stundenwerte ab
28.10.2026 11:00, nach Ergänzung von Nachtwerten erfolgreicher EOS-Test. Dieser historische
Erfolg ist berichtet; die Originalreihe ist noch nicht als Rohdatenfixture verfügbar.
Die Geometrie wurde aus EOS gelesen. Standortdaten und Zugangsdaten bleiben privat.

EOS-Cachemetadaten sind lesbar. Die Cachedateien selbst sind über die vorhandene
Dateifreigabe nicht lesbar. Es wurden keine Rechte verändert, keine unkontrollierten
Pickles geladen und kein zusätzlicher externer Abruf als Ersatz gestartet.

## Geprüfte bestehende Lösungen

EOS-Quellstand:
[`8a8cd43a1915668927eda5504b7de039c2e762b4`](https://github.com/Akkudoktor-EOS/EOS/tree/8a8cd43a1915668927eda5504b7de039c2e762b4).
Der Versionsstring ist kein Beweis für den Commit des installierten Images; deshalb wurde
das Live-Schema unabhängig geprüft.

| Implementierung | Befund |
|---|---|
| `PVForecastImport._update_data()` | Importiert Datei/JSON; keine Beschaffung oder Nachtklassifikation. |
| `DataSequence._key_to_series()` | Interpolation und ffill/bfill sind allgemein; können Tageslücken verdecken. |
| `bounded_forecast_array()` in `optimization/genetic/forecast.py` | Strenge Abdeckung, Lücken/Tail bleiben NaN, auch nachts. Keine automatische Nachtfüllung. |
| `PVForecastHomeAssistant` | Vorhandener Adapter für HA-Listen, aber keine entsprechende strenge Nacht-/Tagesprüfung. |
| `PVForecastForecastSolar` | Bestehende gewünschte Quelle. Übernimmt Standort/PV-Flächen, Azimutumrechnung, API-Aufruf, Flächensumme und Zeitzone. Dieser Code wird wiederverwendet. |
| PVNode/Solcast | Andere externe Quellen; kein Grund zum Wechsel oder zusätzlichen Abrufen. |
| `PVForecastPVLib` | Berechnet lokal aus Wetter eine neue Prognose; würde bestehende Tageswerte ersetzen. Deshalb hier nicht gewählt. |

Eine vollständige interpolierte Anzeige belegt keine vollständige rohe Optimiererreihe.
Eine Tageslichtliste, kurze Horizonte, stündliche Auflösung, Intervallende und falsche
Offsets können unterschiedliche Lückenbilder erzeugen. Das konkrete historische Fehlerbild
ist ohne Rohantwort nicht bewiesen. EOS-Issue
[#779](https://github.com/Akkudoktor-EOS/EOS/issues/779) behandelt Azimut, nicht Nachtlücken.

## Entscheidung / Wiederverwendung

Keine neue Forecast.Solar-Implementierung und kein neues Prognosemodell. Ein kleiner
Normalizer ergänzt den fehlenden Qualitätsvertrag. Astral berechnet Sonnenzeiten, `zoneinfo`
verarbeitet Zeitzonen. Der volle EOS-Code wird nur für den optionalen Quellenabruf geladen.

Die bestehende API hat keinen Providerselektor für rohe Reihen eines inaktiven Providers.
Der Forecast.Solar-Provider prüft außerdem intern `enabled()`, sodass ein erzwungenes
Update bei aktivem PVForecastImport nicht ohne Weiteres diese Pipeline ersetzt. Wiederholtes
Umschalten der produktiven Konfiguration wäre unzulässig und wird nicht implementiert.

Stattdessen läuft die unveränderte native `_request_forecast()`-Methode in einem lokalen
Helferprozess mit aus EOS gelesenen Parametern. Nur dort ist Forecast.Solar konfiguriert;
das Server-EOS bleibt auf PVForecastImport. Gemeinsamer JSON-Cache, Parameterfingerprint,
Cachefrist und Dateilock verhindern Abrufe pro Verbraucher. EMHASS kann später dieselben
zentralen Dateien lesen. Der Preis dafür ist ein größeres optionales `eos-source`-Image.
Das reine `normalizer`-Image bleibt klein und führt keine Quellenabrufe aus.

Wenn die vorhandene Quelle bereits eine vollständige geprüfte Zeitreihe exportiert, ist
deren direkter Import/nativer HA-Adapter vorzuziehen; dann kein unnötiger Dauerhelfer.

## Zeit-/Einheitenvertrag

Forecast.Solar liefert Leistungs-Stützstellen. Bei deklarierter Stundenkadenz werden
Viertelstunden linear innerhalb benachbarter gültiger Stützstellen erzeugt. Ein fehlender
Stundenpunkt führt zu einer größeren Lücke und damit tagsüber zum Fehler. Das ist keine
pauschale Reparatur fehlender Tagespunkte. Originale liegen unverändert im Rohcache;
vorhandene Punkte auf dem Zielraster behalten ihre Werte. Eine andere Interpretation
als Stundenmittelwerte müsste fachlich separat vereinbart werden.

Nacht bedeutet ein vollständig außerhalb der astronomisch berechneten Sonnenaufgangs- und
Untergangszeiten liegendes Intervall, nicht ausschließlich Dunkelheit unter -18 Grad.
Keine festen Uhrzeiten. Polare/unklare Sonnenereignisse werden abgelehnt. Naive mehrdeutige
oder nicht existente Zeiten werden nicht geraten. 48 verstrichene Stunden sind 192 Slots,
lokale DST-Kalendertage dagegen 92 bzw. 100 Slots.

26 Stundenwerte ergeben nicht 48 Stunden Abdeckung. Kurze Quellenhorizonte bleiben Fehler;
die bestehende EOS-Konfiguration wird nicht eigenmächtig angepasst.

## Tatsächlich geprüfter Importvertrag

`PUT /v1/prediction/import/{provider_id}` akzeptiert live `PydanticDateTimeDataFrame`,
`PydanticDateTimeData` sowie ein generisches Objekt. Verwendet wird ausschließlich
`PVForecastImport`, ohne `force_enable`:

```json
{"data":{"2026-06-20T00:00:00+00:00":{"pvforecast_ac_power":0}},"tz":"UTC"}
```

Der Import enthält W. Ein Optimierer-Slot von 900 Sekunden benötigt dagegen Wh:
`E_Wh = P_W * 0.25`, genau einmal. Importdatei/Import-JSON dürfen HTTP-Importe nicht später
überschreiben; der Helfer verweigert diesen Konflikt statt Konfigurationen zu ändern.
Die Fixture enthält nur den öffentlichen relevanten Schemaausschnitt, keine Betriebsdaten.

## Validierung und offene Punkte

Lokale Tests umfassen Lücken, Nullwerte, DST, Hourly-to-quarter-hour, Importformat,
Schreibsperren, Cache-Wiederverwendung, native EOS-Quelle mit abgefangenem HTTP sowie einen
echten 48-h-EOS-Import-/Optimierungslauf mit synthetischen Daten ohne Netzwerkzugang.
Die konkrete Installation benötigt weiterhin einen echten Quellen-/Unraid-Dry-run,
explizite EOS-Schreibfreigabe und einen erfolgreichen Optimierungslauf mit diesen Daten.

## Erweiterungen aus Issue #1: Prüfung der installierten Verträge

Am 28.10.2026 erneut ausschließlich per GET geprüft: installiertes OpenAPI
`v0.3.0.dev2602241646141478`, `ems.mode=PREDICTION`, `ems.interval=3600`,
`optimization.algorithm=GENETIC`, `interval_sec=3600`, Kontrollhorizont 24 h,
Prognose 48 h, `tail_horizon_hours=48`. Preisprovider bleibt `ElecPriceEnergyCharts`;
keine automatische Umstellung. Konkrete Adressen, HA-Zugangsdaten, Standortparameter und
vollständige Anlagenkonfiguration werden nicht im Repository gespeichert.

Die neuen Module verwenden folgende bestehende EOS-Implementierungen des bereits oben
gepinnten Quellstands:

- [`server/eos.py`](https://github.com/Akkudoktor-EOS/EOS/blob/8a8cd43a1915668927eda5504b7de039c2e762b4/src/akkudoktoreos/server/eos.py):
  `fastapi_measurement_value_put()` bestätigt Query-Parameter statt Samples-Payload;
  `fastapi_optimize_config()` akzeptiert `ConfigOptimizationRequest` und liefert einen
  neuen `GeneticSolution`, bei fehlendem neuen Ergebnis HTTP 503.
- [`prediction/elecpriceimport.py`](https://github.com/Akkudoktor-EOS/EOS/blob/8a8cd43a1915668927eda5504b7de039c2e762b4/src/akkudoktoreos/prediction/elecpriceimport.py):
  `ElecPriceImport._update_data()` importiert ausschließlich konfigurierte Datei/JSON;
  es führt kein `_store_gross_series()` oder `_apply_fees()` aus.
- [`prediction/elecpriceabc.py`](https://github.com/Akkudoktor-EOS/EOS/blob/8a8cd43a1915668927eda5504b7de039c2e762b4/src/akkudoktoreos/prediction/elecpriceabc.py)
  und `priceabc.py`: `elecprice_marketprice_wh` enthält Gebühren, das Feld mit `_raw_`
  nicht. Nur die Raw→Gross-Berechnung addiert Betrag und Prozent. Ein Import bereits
  vollständiger evcc-Endkundenpreise muss das Gross-Feld verwenden.
- [`optimization/genetic/configrequest.py`](https://github.com/Akkudoktor-EOS/EOS/blob/8a8cd43a1915668927eda5504b7de039c2e762b4/src/akkudoktoreos/optimization/genetic/configrequest.py):
  `ConfigOptimizationRequest.resolve()` liest frische SoC-Messwerte, quantisiert Prozent
  auf Integer und fällt bei fehlenden Werten auf angenommene 0 % zurück. Der Helfer
  blockiert fehlenden/veralteten SoC und übergibt den bestätigten Integer explizit.
  Native Forecastarrays beginnen an lokaler Mitternacht; der Helfer baut keine
  verschobenen Runtime-Arrays und verwendet die EOS-eigenen Reihen.
- [`optimization/genetic/genetic.py`](https://github.com/Akkudoktor-EOS/EOS/blob/8a8cd43a1915668927eda5504b7de039c2e762b4/src/akkudoktoreos/optimization/genetic/genetic.py):
  Tail-Slots werden auf den nach dem Kontrollhorizont verbleibenden Prognoseumfang
  begrenzt und bei Lücken verkürzt. Aktuell maximal 24 h Tail, keine 72-h-Pflicht.
- [`optimization/genetic/forecast.py`](https://github.com/Akkudoktor-EOS/EOS/blob/8a8cd43a1915668927eda5504b7de039c2e762b4/src/akkudoktoreos/optimization/genetic/forecast.py):
  `bounded_forecast_array()` integriert vollständig gedeckte Intervalle ohne Füllung;
  dieselbe strikte Semantik dient der lesenden Vorprüfung.
- [`core/ems.py`](https://github.com/Akkudoktor-EOS/EOS/blob/8a8cd43a1915668927eda5504b7de039c2e762b4/src/akkudoktoreos/core/ems.py):
  `EnergyManagement.run()` kann einmalig im Optimierungsmodus aufgerufen werden, ohne
  den gespeicherten EMS-Modus zu ändern. Es aktualisiert dabei nativ Prognosen und
  Adapter und kann einen Abschluss-Webhook senden. Deshalb sperrt der Helfer bei
  konfigurierten aktiven Adaptern oder Webhook; er schaltet sie nicht selbst ab.

**Entscheidung:** EOS bleibt Prognose- und Optimierungsdienst. Der Helfer ergänzt nur
validierte externe Eingaben, gemeinsame Cachedateien und eine persistente Verarbeitung
neuer vollständiger Preisveröffentlichungen. Ein neuer Scheduler, Preisclient,
Tarifmodell oder Hardwareadapter ist nicht erforderlich. Abläufe und bewusste
Grenzen der Idempotenz stehen in [synchronisation.md](synchronisation.md).
Issue #1 bleibt offen; keine automatische Schließreferenz im PR.

## Quellen

- [EOS-Dokumentation](https://akkudoktor-eos.readthedocs.io/en/latest/akkudoktoreos/prediction.html)
- [Nativer Forecast.Solar-Provider](https://github.com/Akkudoktor-EOS/EOS/blob/8a8cd43a1915668927eda5504b7de039c2e762b4/src/akkudoktoreos/prediction/pvforecastforecastsolar.py)
- [Importprovider](https://github.com/Akkudoktor-EOS/EOS/blob/8a8cd43a1915668927eda5504b7de039c2e762b4/src/akkudoktoreos/prediction/pvforecastimport.py)
- [Zeitreihenfunktionen](https://github.com/Akkudoktor-EOS/EOS/blob/8a8cd43a1915668927eda5504b7de039c2e762b4/src/akkudoktoreos/core/dataabc.py)
- [Strenge Prognoseabdeckung](https://github.com/Akkudoktor-EOS/EOS/blob/8a8cd43a1915668927eda5504b7de039c2e762b4/src/akkudoktoreos/optimization/genetic/forecast.py)
- [Import-API](https://github.com/Akkudoktor-EOS/EOS/blob/8a8cd43a1915668927eda5504b7de039c2e762b4/src/akkudoktoreos/server/eos.py)
- [Astral](https://astral.readthedocs.io/en/latest/), [PVLib als größere Alternative](https://pvlib-python.readthedocs.io/en/stable/reference/solarposition.html)
