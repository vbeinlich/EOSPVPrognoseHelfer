# Phase 2: E3/DC-Eigenverbrauch und gespeicherter GENETIC-Plan

Review-Erweiterung zu PR #14 / Issue #6. Kein Merge, Deployment, Release oder
Gerätebetrieb wird dadurch freigegeben. Reine **prognostizierte Modellkosten**,
keine gemessene Rechnung und kein Nachweis realisierter Einsparungen.

## Modell und Datenvertrag

Wiederverwendet werden `GeneticSimulation.prepare()` und `.simulate()` sowie
`Battery` und `Inverter` aus EOS-Revision
`8a8cd43a1915668927eda5504b7de039c2e762b4`. **Kein** `optimize_ems()`, HTTP,
Provider-Refresh oder Trigger. Quellhashes der Simulations-/Geräteklassen und der
probabilistischen PV-/Last-Überlappungstabelle werden geprüft und im Ergebnis
ausgegeben; nicht geprüfte Dateien sperren die Berechnung. NumPy-/SciPy-/Pydantic-
Versionen stehen im privaten Ergebnis. Das ist eine kontrollierte native EOS-
Wiedergabe, kein zweiter selbst entwickelter Batteriesimulator.

Referenz: PV-Überschuss laden, Restlast aus Batterie decken, jeweils soweit SoC,
Wirkungsgrad und Leistung es erlauben. Kein Netzladen und kein Batterie-Netzexport.
Technisch `ac_charge=0`, `dc_charge=1`, `discharge_allowed=1`, Direct Marketing aus.
GENETIC: exakt die bereits gespeicherten Freigaben auf denselben Eingaben ausführen.
Beide Läufe beginnen frisch mit denselben Parametern und demselben Anfangs-SoC.
Der bestehende Sync-/Preis-/PV-/Claim-Ablauf wird nicht verändert oder importiert.

Nur explizite, vollständige, zeitzonenbehaftete `controls_start_at_now=true`-Lösungen
mit 900-/3600-s-Raster und im Plan gespeicherten EMS-Eingaben sind berechenbar.
Keine aktuellen `prices.json`, `forecast.json`, `soc.json`, keine Konfigurations-
Defaults, keine Auffüllung oder Rekonstruktion historischer Intervalle.
PV-/Lastenergien sind Wh je Originalslot; Preise EUR/Wh, Anzeige EUR/kWh.
Nullwerte sind gültig, negative Preise möglich, NaN und negative PV/Last nicht.

Vor einem Sparwert muss die native Wiedergabe die Originalreihen von Netzbezug,
Einspeisung, SoC, Kosten, Erlösen, Verlusten und Preisen sowie Kostensummen,
Endenergie und ursprünglichen Endwert reproduzieren. Toleranz: relativ 1e-9,
absolut 1e-5 in der jeweiligen Einheit. Widersprüchliche Aliase, fehlende Daten,
Zeitbasisfehler und fremde Gerätezuordnung sperren. Das bindet den Vergleich an
die gespeicherten Laufeingaben, ersetzt aber keine vollständige historische
Doctor-Abnahme mit unabhängig belegter Quellfrische.

Der alte Container muss EOS nicht importieren können: Reader und Bundle bleiben
stdlib-kompatibel. Der NAS-Reader initialisiert und verwendet die native Engine
grundsätzlich nicht, auch nicht unter Shared-Lock. Stattdessen verweist er auf
den getrennten Offline-Vergleich. Dadurch erzeugt er auch keine temporäre EOS-Konfiguration.
Der gesonderte numerische Export enthält keine Tokens, URLs, IPs, Gerätenamen,
Standorte oder privaten Konfigurationen. Er enthält **private Prognose-/Planwerte**
und bleibt ausschließlich beim Betreiber. Hashes authentifizieren keinen Absender.

## Kosten und unterschiedliche End-SoCs

Je Szenario:

```
Betriebskosten = Netzbezugskosten - Einspeiseerlös + Batterieverschleiß
Bewertete Kosten = Betriebskosten - gespeicherte gemeinsame Endwertkurve(Endenergie)
Prognostizierte Mehrersparnis = bewertete Referenzkosten - bewertete GENETIC-Kosten
```

Die Endenergie ist tatsächlich **nach dem letzten Kontrollslot** vorhandene,
oberhalb des Minimums nutzbare AC-Energie; der letzte `battery_soc_per_hour`-Wert
ist dagegen ein Slot-Anfangswert. Für beide Endzustände gilt exakt dieselbe
historische AUTO-/TAIL-Kurve. Keine Extrapolation, kein neu erfundener Endpreis.
Ein negativer Kurvenwert kann zukünftige Betriebskosten enthalten: sein konstanter
Anteil hebt sich in der Differenz auf. `credited_euro` wird nicht noch einmal
zusätzlich gutgeschrieben. Tail-Kosten sind nicht zusätzlich in den Kontrollkosten.

LCOS wird wie in EOS einmal auf aus der Batterie gelieferte DC-Energie berechnet,
nicht auf eingespeicherte Energie und nicht nochmals auf Wirkungsgradverluste.
Verluste bleiben als kWh sichtbar; sie stecken bereits in den Energieflüssen und
werden nicht nochmals als Kosten addiert. Negative Mehrersparnis wird nicht auf
null begrenzt. Prozentwerte nur bei positiven bewerteten Referenzkosten; sonst
„—“, damit negative/nahe null Kosten keine irreführenden Prozente erzeugen.

## Lastannahme 11.251 statt 8.000 kWh

Optional `--scaled-load-sensitivity`: ausschließlich die **gespeicherte** Lastreihe
mit `11251/8000 = 1,406375` multiplizieren und beide Betriebsweisen nochmals
vorwärts simulieren. Gleiche Preise, PV, Startbedingungen, Freigaben und dieselbe
historische Endwertkurve. Kein GENETIC-Neulauf, keine neue Forecastabfrage.

Dies ist ausdrücklich ein isolierter **linearer Annahmetest** mit festgehaltenem
Endwertmodell. Es beweist weder, dass damals 8.000 kWh konfiguriert waren, noch
entspricht es einem neu optimierten 11.251-kWh-Plan oder einer neu geschätzten
Tail-Kurve. Eine belastbare Aussage über die neue Jahreslast braucht deren
nachgewiesenes Profil bzw. einen gesondert freigegebenen Offline-Vergleich.
Ohne vollständiges historisches Profil und Basisvergleich: Nicht berechenbar.

## Synthetischer, von Hand prüfbarer Beispielvergleich

Zwei Stunden, Startenergie 1 kWh, perfekte Wirkungsgrade, keine PV, je 1 kWh Hauslast,
Preise 0,10 / 0,50 EUR/kWh, keine Verschleißkosten. Referenz entlädt sofort; ein
bereits gespeicherter GENETIC-Plan hält zuerst und entlädt in Stunde 2.

| Kosten / Energie | Referenz | GENETIC |
| --- | ---: | ---: |
| Netzbezug | 1 kWh | 1 kWh |
| Netzbezugskosten | 0,50 EUR | 0,10 EUR |
| Endenergie | 0 kWh | 0 kWh |
| Mehrersparnis | | **0,40 EUR** |

Vertauschte Preise ergeben **−0,40 EUR**, nicht einen verschwiegenen Nachteil.
Ein weiterer Test hält 3,9 kWh bis zum Ende zurück: bei konstant 0,30 EUR/kWh und
identischer Endbewertung verschwindet der scheinbare Vorteil der leereren Referenz
vollständig. Das sind synthetische Benchmarks, keine Anlagenergebnisse.

## Modellgrenzen

- EOS' probabilistische PV-/Last-Überlappung pro Originalslot gilt für beide
  Betriebsweisen. Eine Stundenbilanz kann gleichzeitig PV-Laden und Netzbezug
  zeigen; sie ist keine hochaufgelöste Messung realer Schaltvorgänge.
- Vereinfachter E3/DC-Eigenverbrauch, kein kalibriertes Modell der herstellereigenen
  Wetterreserve, Prognoseladung, Notstromreserve, Regelverzögerung oder Sperren.
- Derzeit keine EVs, flexiblen Verbraucher, Batterie-Netzexport, lastabhängigen
  Wechselrichterkurven, FIXED-Endwerte oder unklaren Legacy-Zeitachsen. Statt
  stiller Näherungen jeweils „Nicht berechenbar“.
- Eine hohe AUTO-Fortsetzungsbewertung kann Ergebnisse dominieren. Sie ist eine
  Modellannahme, keine garantierte Einnahme und keine gemessene Energieersparnis.
- Keine neue Optimierung: ein größerer Last-Annahmetest verwendet unveränderte
  GENETIC-Freigaben; GENETIC selbst ist außerdem heuristisch.
- Kein Plan-vs-Ist, keine realisierten Einsparungen, keine automatische Gerätesteuerung.
- Fehlender privater 30.10.-Datensatz darf nicht aus 29./31.10. abgeleitet werden.

## Private Operator-Abnahme: Quelle unverändert, Berechnung offline

### 1. Review-Code auf dem Diagnose-Rechner vorbereiten

Nach Review den exakten PR-Commit auschecken. Bundle erzeugen (neuer Dateiname):

Geprüftes deterministisches Code-Bundle:
`ca3d2d8543ca9923b9024c3b1ad5d683fcd8cb5b01d84d13a180cdc47662a8a8`.
Wrapper-SHA256 (UTF-8, LF):
`aeb5a12796adf8a940c18ac289643e8fd4f54a2cd2e6ec2b1e1861bb4c31c1fd`.
Die Hashes gelten ausschließlich für diesen Code-Stand, nicht für private Reports
und nicht für ältere Phase-1-Bundles. Bei einer Codeänderung neu prüfen.

```sh
python scripts/build_plan_inspector.py --output /PRIVATE/plan-economics.pyz
sha256sum /PRIVATE/plan-economics.pyz scripts/unraid-plan-inspector.sh
```

Hashes unabhängig gegen die Review-Unterlagen prüfen. Nur Code-Bundle und Wrapper
über den vorhandenen privaten Transferweg nach Unraid übertragen. Keine Images
veröffentlichen und keinen produktiven Container ersetzen.

### 2. Auf Unraid rein lesend numerische Originaleingaben exportieren

Der bekannte Wrapper prüft Bundlehash, vollständige Container-Image-Identität und
Output-Mount; der Reader liest unter vorhandenem nicht blockierendem Shared-Lock.
Nur der Operator legt einen **neuen privaten Export außerhalb `/output`** an:

```sh
umask 077
set -o noclobber
PRIVATE_EXPORT=$(mktemp -d /tmp/eos-economics-private.XXXXXX)
bash /PRIVATE/unraid-plan-inspector.sh /PRIVATE/plan-economics.pyz REVIEWED_BUNDLE_SHA256 \
  --comparison-inputs > "$PRIVATE_EXPORT/comparison-inputs.json"
rc=$?
printf 'Exitcode: %s\n' "$rc"
if [ "$rc" -eq 0 ]; then sha256sum "$PRIVATE_EXPORT/comparison-inputs.json"; fi
```

Bei Fehler keinen Teilreport verwenden; erneut in einem neuen privaten Ordner
versuchen. Bei belegtem Lock warten, niemals den produktiven Helfer stoppen oder
ein Lock/Claim reparieren. Keine EOS-Aufrufe. Export privat herunterladen, niemals
als Issue-Anhang oder CI-Artefakt veröffentlichen. Vollständigkeit je Plandatum prüfen.

### 3. Auf dem Diagnose-Rechner native EOS-Simulation ausführen

Die vorhandene gepinnte Integrationstest-Umgebung verwenden. Ein lokaler Build
liest einmalig die festgelegten Quell-/Paketabhängigkeiten; er ruft keine Wetter-,
Preis-, Geräte- oder Produktions-APIs ab und publiziert kein Image:

```sh
docker build -f tests/integration/Dockerfile -t eos-economics:review .
set -o noclobber
docker run --rm --pull=never --network none --read-only --cap-drop=ALL \
  --security-opt=no-new-privileges --tmpfs /tmp:rw,nosuid,nodev \
  --tmpfs /tmp/eos-test:rw,nosuid,nodev \
  --mount type=bind,source=/ABSOLUTE/PRIVATE/comparison-inputs.json,target=/private/inputs.json,readonly \
  --entrypoint python eos-economics:review \
  -m eos_pv_helper.economics_report --input-report /private/inputs.json --format html \
  --scaled-load-sensitivity > /PRIVATE/economics-review.html
rc=$?
printf 'Exitcode: %s\n' "$rc"
```

EOS darf im lokalen Wegwerfcontainer minimale temporäre Konfigurationsdateien
anlegen, ausschließlich im tmpfs `/tmp/eos-test`. Keine produktive Konfiguration
mounten, keine Netzwerkfreigabe und keinen Docker-Socket einbinden. Bei bereits
vorhandenem geprüftem Image kein unnötiger Neubau. Docker-Kontext vorher als lokal
prüfen. Docker Desktop auf Windows: absolute Hostpfade entsprechend ersetzen.

Exitcode **0**: alle exportierten Pläne berechnet; **2**: Report vollständig, aber
mindestens ein Plan ausdrücklich nicht berechenbar; **1**: ungültiger Eingang,
keinen Teilreport verwenden. HTML lokal im Browser öffnen, kein Server/Port nötig.
Mit `--format json` einen zusätzlichen neuen privaten Prüfbericht erzeugen.
Direkte unveränderte private Originaldateien können alternativ mittels wiederholtem
`--solution /private/solution-<version>.json` als JSON verglichen werden.

### 4. Abnahmekriterien

Für **jeden** 29.–31.10.-Plan Original-Bytehash und Projektionshash prüfen,
Start/Offset/Raster bestätigen und `replay_verified=true` verlangen. Herkunft und
Originalität des privaten Exports vom Betreiber bestätigen lassen. Keine heutigen
Preise oder SoC-Dateien nachladen. Bei einer Datenlücke „Nicht berechenbar“ belassen.

Kostenzerlegung, beide tatsächlichen End-SoCs, identische Endwertmethode und
negative Ergebnisse sichtbar prüfen. Skalierung gesondert als Annahmetest lesen.
Der historische Doctor-Nachweis bleibt ein eigener Gate; dieser Vergleich gibt
weder einen Produktivbetrieb noch einen finanziellen Erfolg frei.
