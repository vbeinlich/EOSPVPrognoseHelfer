# Native Batteriefluss-Sidecars – privater Offline-Workflow

Dieser Vertrag ergänzt das statische EMS-Dashboard nach dem Gegenreview
`5ccacd98644c167da245b42ea043cb2be29080f1`. Er wird ausschließlich auf einem
separaten Review-Rechner erzeugt. Der HTML-Reader und der laufende Helfer erzeugen
keinen Replay. Ursprüngliche JSON-Dateien und Claims bleiben unverändert.

## Energiebasis und Nachweis

Vertrag: `eos-pv-helper/native-flow-replay-v1`, Schema-Version 1.
Die farbigen Replay-Balken zeigen **interne Speicherenergie**:

- Grün: PV-Ladung nach internem Ladewirkungsgrad.
- Blau: Netzladung nach internem Ladewirkungsgrad.
- Orange: interne Speicherentnahme vor internem Entladeverlust.
- Violett: Original-SoC am Intervallanfang.

Zusätzlich speichert der Sidecar PV-/Netz-DC-Eingang vor internem Ladeverlust und
DC-Ausgang nach internem Entladeverlust. Beide Messpunkte bleiben im Intervall-
Detail nachvollziehbar. Wirkungsgrade werden nicht doppelt angewendet.

```
interne PV-/Netzladung = jeweiliger DC-Eingang * charging_efficiency
interne Speicherentnahme = DC-Ausgang / discharging_efficiency
nutzbare interne Kapazität = capacity_wh * (max_soc_percentage - min_soc_percentage) / 100
äquivalente Vollzyklen = Summe(interne Speicherentnahme) / nutzbare interne Kapazität
```

Fenster sind zusammenhängende Originalintervalle mit positiver interner Ladung
bzw. Entnahme. Gleichzeitiges Laden und Entladen bleibt getrennt erhalten.
Eine Nettodifferenz des SoC ersetzt diese Bruttoenergien nicht.

Jeder Plan enthält Originalbytehash, Hash der vollständigen gespeicherten
Parameter, Hash der numerischen Solverprojektion, ursprünglichen UTC-Start und
Originalintervall, native EOS-Revision, gehashte Engine-/Interpolationsquellen,
Dependency-Versionen, Ergebnisvergleich, Herkunftsreihen, Fenster und Vollzyklen.
Plan und Gesamtkatalog besitzen kanonische SHA-256-Prüfsummen. Die Datei wird neu
und exklusiv angelegt; vorhandene Sidecars werden nicht überschrieben.

Die native Vorwärtswiedergabe läuft zweimal mit festen gespeicherten Freigaben,
identischen Eingaben und ohne Baseline oder Optimierersuche. Der zweite Lauf
beobachtet ausschließlich die nativen PV- und Netzladepfade. Beide Ergebnisse
müssen gleich sein und die gespeicherten Ergebnisreihen, Gesamtsummen sowie
Endenergie/-wert reproduzieren. Auch vorhandene Last-/EV-/Gerätereihen werden
geprüft. Negative, unvollständige, verschobene oder inkonsistente Daten werden
abgelehnt. Der Reader prüft zusätzlich die Herkunftssumme und die SoC-Energiebilanz.

**Nachweisstatus:** `posthoc_native_model_replay` – nachträglich berechnete
Modellflüsse. Keine damaligen Messwerte, keine ausgeführten Geräteaktionen und
kein nachträglicher historischer Request-/Optionsbeweis.
`exact_solver_options_proven=false` bleibt erhalten. Hashes belegen Konsistenz;
der private Exporter und die übertragenen Dateien müssen vertrauenswürdig sein.
Ein absichtlich vollständig neu konstruierter und neu gehashter Fremdexport wird
durch Selbstprüfsummen nicht kryptographisch authentisiert.

## Sidecar auf dem Review-Rechner erzeugen

Benötigt werden der geprüfte Helfer-Checkout, die gepinnte native EOS-Revision
`8a8cd43a1915668927eda5504b7de039c2e762b4` samt Überlappungstabelle und passende
Dependencies. Bestehende isolierte lokale Testumgebung verwenden: Originaldateien
read-only, kein Netzwerk, keine Geräte-/Live-Konfigurations-Mounts, eigene
schreibbare temporäre Verzeichnisse und ein eigenes privates Ergebnisverzeichnis.

Innerhalb dieser lokalen Umgebung, mit den privaten Originalen als Eingabe:

```bash
python -m eos_pv_helper.replay_export \
  --solution /original29.json --solution /original31.json \
  --output /private/replays-v1.json
```

Das ist ein gesonderter Vorwärts-Replay, kein GENETIC-Suchlauf. Der Exporter sperrt
Optimierersuche und HTTP; sein CLI sperrt zusätzlich Socket-Verbindungen. Native
EOS-Konfigurationsinitialisierung erfolgt in einem eigenen temporären Ordner.
Keine Originalkonfiguration wird geladen oder geändert. Bei fehlenden Eingaben,
abweichenden Ergebnissen oder vorhandener Zieldatei: Abbruch, kein freigegebener
Sidecar. Originalbytes und Änderungszeiten werden vor/nachher verglichen.

Für spätere Ergebnisse einen neuen versionierten Dateinamen verwenden und nur
vorliegende Originale aufnehmen. Der 30.10. bleibt bis zur Verfügbarkeit seiner
Originaldaten offen. Keine Daten aus Nachbartagen oder heutigen Forecasts ergänzen.

## Statische Vorschau ohne erfundene Claims

Auf dem privaten Review-Rechner kann der stdlib-Reader Originalantworten direkt
öffnen; dafür ist keine synthetische `sync-state.json` nötig:

```bash
python -m eos_pv_helper.dashboard \
  --solution /original29.json --solution /original31.json \
  --replays /private/replays-v1.json --destination /private/site
```

Der Zielordner muss bereits existieren und privat sein. Ohne belegte Claims
zeigt der Kopf ausdrücklich **Letzter geprüfter Modell-Replay**, nicht erfolgreicher
produktiver Dry-Run. Die Qualitätsanzeige behält die fehlende historische Bindung.
Ein Modellvorteil bleibt ohne gesonderten Referenzvergleich `Nicht belegt`.

24 h zeigt den ausgewählten Originalplan. Bei 7/30 Tagen kann die ausdrücklich
beschriftete **Replay-Modellabdeckung ohne historische Claimbestätigung** betrachtet
werden. Sie ordnet überlappende Modellintervalle nach dem Originalplanstart ohne
Doppelzählung zu. Das ist eine rechnerische Modellabdeckung, keine nachträglich
behauptete Verfügbarkeit oder Ausführung des damaligen Plans. Die normale
Claim-Historie bleibt getrennt auswählbar und verwendet nur erfolgreiche Claims.

Fehlstellen bleiben sichtbar. Energie-Teilsummen werden als teilweise markiert;
bei leerer oder lückenhafter Abdeckung sind Lade-/Entladefenster und Vollzyklen
`Nicht belegt`. Ein gemischter DC-/interner Energiebestand wird nicht still addiert.
Vorhandene alte DC-Flüsse allein belegen keine internen Vollzyklen.

## Geprüften Reader für einen späteren privaten Unraid-Test vorbereiten

Die [Codehash-Datei](DASHBOARD_CODE_HASHES.json) enthält ausschließlich öffentliche
Codehashes; keine privaten Sidecar- oder Lösungsdaten. Auf dem Review-Rechner:

```bash
python scripts/check_dashboard_hashes.py
python scripts/build_ems_dashboard.py --output /PRIVATE/ems-dashboard-final.pyz
sha256sum /PRIVATE/ems-dashboard-final.pyz scripts/unraid-ems-dashboard.sh
```

Das Dashboard-Zipapp enthält den reinen Sidecar-Validator, **nicht** den
Replay-Exporter. Nach den nötigen Reviews und gesonderter privater Testfreigabe
nur Readerbundle, Wrapper und bereits fertigen privaten Sidecar über einen
bestehenden privaten Dateizugang übertragen. Keine produktive Konfiguration oder
Container-/Port-/Scheduler-Einstellung ändern.

Der bekannte einmalige Wrapperaufruf erhält den Sidecar als zusätzlichen Parameter:

```bash
/bin/bash /PRIVATE/tools/unraid-ems-dashboard.sh \
  /PRIVATE/tools/ems-dashboard-final.pyz \
  GEPRUEFTER_DASHBOARD_BUNDLE_SHA256 /PRIVATE/site \
  --replays /PRIVATE/replays-v1.json
```

Das Bundlehash ist der feste überprüfte Wert aus `DASHBOARD_CODE_HASHES.json`.
Auch Wrapper und privater Sidecar müssen nach Übertragung den lokal geprüften
Hashes entsprechen. Optional kann vor `--replays` weiterhin ein vorhandener
Economics-Report angegeben werden; er ersetzt keinen Fluss-Sidecar.

Der kurze Leser nutzt Python im einen bereits laufenden Helfer. Er liest vorhandene
Originale und den bereitgestellten Sidecar, ohne EOS-Import zur Simulation und ohne
Replay. Nicht passende neue reguläre Pläne erhalten keine erfundenen Flüsse;
sie benötigen später einen gesonderten neuen Offline-Export. Beschädigte passende
Sidecars erhalten die letzte gültige HTML-Anzeige mit sichtbarem Fehler.

Die Schutzvorkehrungen aus [EMS_DASHBOARD.md](EMS_DASHBOARD.md) bleiben bestehen:
separates privates Ziel, Hashprüfung, Quellen nur lesend, atomarer HTML-Ersatz,
keine zweite Helferinstanz. Der Leser hält kurz das gemeinsame SH-Lock und kann
einen anschließend beginnenden Sync verzögern. Für den ersten privaten Test abseits
des nächsten regulären Triggers genau einmal exportieren; keinen Scheduler aktivieren.
Ein minütlicher Dauerbetrieb bedarf weiterhin der gesonderten Betreiberabnahme.
