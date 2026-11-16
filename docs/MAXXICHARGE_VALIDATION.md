# MaxxiCharge PoC – Validierung vom 15.11.2026

Arbeitszweig `feat/maxxicharge-simulator`, Ausgangspunkt
`546baa63ade70cab20c67a7410575c8d2b8dc667`. Implementierungsplan wurde vor dem
Simulator angelegt. **Isolierte Implementierung bestanden; vollständige Abnahme
mit realer Messhistorie und Hardwaremodell bleibt offen.** Kein Deploy, Registry-
Push, Neustart produktiver Container oder realer MQTT-/Gerätebefehl.

## Bestandsnachweis und Zugriffsgrenzen

Lesend sichtbar auf der bestehenden NAS-Freigabe: Verzeichnisse für
`akkudoktor-eos`, `eos-pv-helper`, `ems-dashboard-review`, `evcc`, Home Assistant
und Mosquitto. Das bestehende Dashboard antwortet per HTTP GET mit 200.
Das bestätigt Verzeichnisse/HTTP-Erreichbarkeit, nicht aktuelle Container-Images,
deren exakte Laufkonfiguration oder eine funktionierende neue Datenanbindung.

Aktuelle Helferkonfiguration, Quellen-Caches und Solver-Dateien sind auf der
Freigabe zwar auflistbar, ihr Inhalt ist durch bestehende Dateirechte gesperrt.
Eine lesende Wiederholung außerhalb der Sandbox ergab denselben Zugriffsschutz.
SSH lieferte keine Verbindung; der zuvor dokumentierte evcc-Endpunkt war nicht
erreichbar. Es wurden keine Rechte geändert, Dienste gestartet oder Zugangsdaten
neu angelegt. HA-Recorder-/WAL-Dateien wurden nicht geöffnet oder kopiert.

Für historische Replays wurden die bereits vorhandenen lokalen Originalantworten
vom 29. und 31.10. sowie eine bereits gesicherte EOS-Konfiguration verwendet.
Diese enthalten ursprüngliche Prognose-/Preis-/Last-Modelleingaben, **keine
vollständige gemessene Haushaltsgeschichte**. Eine aktuelle vollständige Messdatei
gemäß `PLAN_ACTUAL.md` lag im zugänglichen Bestand nicht vor.

## Ausgeführte Prüfungen

| Prüfung | Ergebnis |
| --- | --- |
| Gesamte vorhandene Testsuite einschließlich PoC | **825 bestanden**, 3 `genetic_execution`-Tests bewusst abgewählt; 71,81 s im vorhandenen isolierten Linux-Testimage |
| PoC-Tests nach ergänzter unabhängiger Bilanzrechnung | **63 bestanden**, 2,21 s |
| Ruff über `src`, `tests`, `scripts` | **PASS** |
| Vorhandene Historical-/Dashboard-/LAN-/Worker-Prüfsummen-Gates | **PASS** |
| `git diff --check` | **PASS** |
| Eigener Docker-Build ohne RUN-Netzwerk und zusätzliche Pakete | **PASS** |
| Compose-Konfiguration mit expliziten separaten Eingangs-/Ausgangspfaden | **PASS** |
| Tatsächlicher lokaler Docker-Lauf | **PASS**, Exit 0, kein OOM; UID 10001, Netzwerk `none`, RO-Root, Eingang RO, ausschließlich eigener Output RW |
| Änderungen der Testeingaben durch Container/CLI | **Keine**, SHA256 vorher/nachher identisch |
| Reale Browserprüfung | **PASS**, vier Szenarien, Slider, Werte, Diagramm; Desktop 1365 px, Mobil 390 px, keine JS-Fehler oder externen Requests |
| Standard-HTML ohne SIM gegen eingefrorenen Originalrenderer | **Bytegleich** bei identischem Prüfbericht |
| Zwei historische 24-h-Prognose-Replays | **PASS**, getrennte Horizonte, keine Addition über Lücken |
| Wiederholung desselben historischen Laufs | **Identische Artefakthashes**, einschließlich HTML und lokalem MQTT-Journal |
| Vollständige historische Messdatenabnahme | **OFFEN**, benötigter vollständiger Export fehlt |
| Validiertes MaxxiCharge-Hardware-/MQTT-Modell | **OFFEN**, interner Vertrag dokumentiert; kein realer Transport implementiert |
| Investitionsangebote und reale Amortisation | **OFFEN**, keine erfundenen Preise/Jahreshochrechnung |

Die drei ausgeschlossenen Tests führen reale genetische Optimierung aus. Für
diesen PoC wurde keine neue produktive Optimierung ausgelöst. Die übrigen Tests
umfassen vorhandene native Integrationsprüfungen innerhalb des isolierten
Testimages; sie sind kein Nachweis einer geänderten Unraid-Laufkonfiguration.

## Physikalische und fachliche Tests

- Analytisch: 1.000 Wh Ladung → 920 Wh interne Zunahme; Roundtrip 84,64 %;
  volle/leere Batterie, Reserve, SOC-Obergrenze, 15-Minuten-Leistungsbudget,
  variable Entladung einschließlich 0 W und Teilbedarf.
- Eigene PV lädt Maxxi, Bestands-PV E3/DC. Maxxi entlädt vor E3/DC für Restlast.
  Getrennte PV-/Netzherkunft; Quellenpools erhalten Energie und zählen initiale
  Energie nicht als PV-Erzeugung.
- Keine gleichzeitige Batterie-Ladung/-Entladung oder Standort-Einspeisung/-Bezug.
  Während Netzladung entlädt kein Speicher. Entladung ist durch Hausbedarf
  begrenzt; `battery_transfer_wh=0` folgt aus dieser Routingregel.
- Preisladung mit wirtschaftlichem Spread nach Verlusten, ohne Spread, bei
  negativen Preisen, späterer günstigerer Gelegenheit, gleich teuren Slots,
  deaktivierter Preisladung und fehlendem zukünftigen Bedarf.
- Acht deterministische Zufallsfolgen über jeweils fünf Tage; die Tests rechnen
  Standort- und Speicherbilanz unabhängig aus den Flüssen nach, statt nur dem
  vom Produzenten ausgegebenen Bilanzfehler zu vertrauen.
- PV: isotroper Himmel/Bodenreflexion, Südausrichtung, unterschiedliche Neigungen,
  Nacht, bifazialer Faktor; Proxy ohne Bestätigung und unpassende Flächen werden
  abgelehnt. Fehlende Strahlung wird nicht aus heutiger Wetter-API nachgeladen.
- Ungültige Werte, Bool/NaN/Infinity, fehlende Preise, doppelte JSON-Schlüssel,
  Zeitlücken, Überlappung und fehlende Zeitzonen sperren. UTC/DST-Wechsel wird
  anhand echter Offset-Wechsel geprüft.
- Herkunfts-/Einheitenadapter für EOS und bestehenden Messvertrag; keine
  Viertelstundenenergie versehentlich vervierfacht, EUR/Wh einmal umgerechnet,
  keine Aufteilung einer Messstunde auf wechselnde Viertelstundenpreise.
- Jahresrechnung nur an einer ausdrücklich **künstlichen analytischen
  Jahresfixture** getestet. Das ist kein vorhandener Realexport. Kurze Reihen
  können das Jahres-/Amortisationsgate nicht freischalten.
- CLI überschreibt keine vorhandenen Ergebnisverzeichnisse. Ungültige Daten
  erzeugen keinen fertigen Report. Manifest bindet die erzeugten Artefakte.
- MQTT-Journal ausschließlich `ems/sim/...`, `mode=SIM`, nicht retained;
  Leistungs-/Zeitkonflikte werden abgelehnt. Keine Netzwerkverbindung im Modell.
- Dashboard behandelt ungültige SIM-Dateien mit dem vorhandenen Last-Good-
  Verhalten. CSP deckt den tatsächlichen Scriptinhalt ab; Texte werden escaped.

## Reproduzierbare historische Nachweise

| Original | SHA256 der unveränderten lokalen Originalbytes | Nutzbarer Kontrollhorizont |
| --- | --- | --- |
| Antwort 29.10.2026 | `9d2acc2ca585f915784cbd891100fc551cab8b194b2b065a01e0bff1ba5fe284` | 24 h, originale Stundenintervalle |
| Antwort 31.10.2026 | `a0cfa244f08b63718a32afad2659fb9fe7a3926b129de6700526b909047d7b84` | 24 h, originale Stundenintervalle |

Zusatz-PV in diesen Replays: `geometry_proxy_assumption`, mit gespeicherter
Referenzgeometrie, angenommenem Diffusanteil und explizitem AC-Konversionsfaktor.
Lastscope bleibt als Modellannahme markiert. Es wird weder behauptet, dass dies
gemessene neue PV-Erzeugung sei, noch dass der E3/DC-Herstellerregler wiedergegeben
wurde. Maximaler **unabhängig nachgerechneter** Standortbilanzfehler über alle
vier Szenarien beider Läufe: `3,64e-12 Wh`. Toleranzen im Modell: 1e-6 Wh pro
Intervall, 1e-5 Wh über den vollständigen Horizont.

Private Eingaben, Kontext, Ergebniszahlen, HTML und Rohberichte befinden sich
nur im ignorierten `private/` des separaten Checkouts. Dort:
`historical-verification.json`, `container-report-final.json`,
`browser-report-final.json`, `default-html-verification.json` und die jeweiligen
Laufverzeichnisse. Sie werden nicht in Quellpakete oder Images aufgenommen.

Lokales finales Image: `ems-maxxicharge-simulator:poc-local`, Docker-Desktop-ID
`sha256:a8e926963860177b9a1ec71376db4662ef764e8c30cf8e7e2e4ac9f2891be61b`.
Das ist ein lokales Build-Artefakt, kein veröffentlichter Registry-Digest.
Die fünf vorher vorhandenen lokalen Anwendungscontainer blieben unverändert
laufend; der eigens erzeugte Smoke-Container wurde wieder entfernt.

## Unveränderte Steuerung und Packaging

Die eingefrorenen Hashes in `simulator/production-baseline.json` prüfen insbesondere
`app.py`, `sync.py`, `evcc_source.py`, produktives Compose/Beispielkonfiguration,
Nginx-Compose und bestehende Gerätefreigaben gegen den Ausgangsstand.
Kein neuer Aktorpfad wurde ergänzt.

Das erweiterte **Lesepaket** hat zwangsläufig neue Codebytes. Deshalb wurden
`DASHBOARD_CODE_HASHES.json`, der einzelne `bundle_sha`-Pin des lokalen Publisher-
Skripts und dessen LAN-Prüfsumme konsistent aktualisiert. Die Publisher-Logik,
der vorhandene Unraid-Wrapper, reale Jobs, Container, Mounts und Nginx bleiben
unverändert. Alle Aktivierungs-/Verteilungsfreigaben bleiben `false`.
Ohne diese reine Packaging-Aktualisierung verweigerten sechs bestehende
Regressionstests erwartungsgemäß das geänderte Lesepaket; nach Aktualisierung
bestand die gesamte Suite. Es wurde kein Unraid-Skript ausgeführt.

## Wiederholung

In einer isolierten Python-3.11+-Testumgebung mit den vorhandenen Testabhängigkeiten:

```sh
ruff check src tests scripts
pytest -q -m 'not genetic_execution'
pytest -q tests/maxxicharge
python scripts/check_dashboard_hashes.py
python scripts/check_dashboard_lan_hashes.py
python scripts/update_evidence_transports.py
python scripts/check_replay_worker_hashes.py
```

Fixtures, lokaler Start und historische Kontextbildung:
[Runbook](MAXXICHARGE_SIMULATOR.md). Browserprüfung:

```sh
node scripts/maxxicharge_ui_smoke.mjs --browser /PATH/TO/CHROME --html /PRIVATE/NEW-RUN/index.html --report /PRIVATE/new-browser-report.json
```

Docker-Smoke nach dem isolierten Build, mit neuen disjunkten Testverzeichnissen:

```sh
python scripts/maxxicharge_container_smoke.py --input-dir /PRIVATE/INPUT --output-parent /PRIVATE/NEW-OUTPUT --report /PRIVATE/new-container-report.json
```

Der Smoke prüft einen lokalen Docker-Daemon, erzeugt ausschließlich einen neuen
eindeutig benannten Testcontainer, prüft dessen Isolation vor Start und entfernt
anschließend ausschließlich diesen Container. Keine bestehenden Dienste werden
angesprochen. Ein vollständiger gemessener Standort-/Tarifexport und belastbare
Investitionswerte sind die verbleibenden Eingaben für die fachliche Realabnahme.
