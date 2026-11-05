# EMS v1.1: regulärer Archivwriter und Replay-Admission

Dieser Folgeauftrag baut auf PR #27, Head
`3f47313e3f95b16aff55d4499768c4e00422a570`, auf. Der v2-Writer existierte dort
bereits als Opt-in im regulären `sync_once`. Im unveränderten Produktionsimage
`ghcr.io/vbeinlich/eospvprognosehelfer@sha256:7e957da3e2fdb67456a46e5538ad3c74b43fa21892d2998e93bca9de83d9daf7`
fehlen seine Module. Laut Betreiber gibt es bis Output-Tiefe 5 keine passenden
ZIPs oder Evidenzmanifeste. Dies wird nicht durch historische Rekonstruktion gelöst.

Es bleibt **ein** Writer im vorhandenen Sync, kein zusätzlicher Dienst, HTTP-Job
oder Optimierer. Nach einem später separat freigegebenen Imagewechsel und
`[evidence] enabled = true` archiviert er neue reguläre Erfolge automatisch.
Ohne diese Freigabe bleiben Beispielkonfiguration, `DRY_RUN=true`, Standard-CMD,
EOS-/Import-/Trigger-Gates und Produktivbetrieb unverändert.

## Originale und Prüfgrenzen

Unverändert gilt [event-evidence-v2](INPUT_BINDING_CONTRACT.md), Schema 2:
`snapshot.json` plus genau sieben Originalartefakte in
`genetic-evidence/<event-version>.zip`:

| Original | Inhalt und Herkunft |
|---|---|
| `prices.json` | Tatsächlich verwendeter Preisframe in Originalbytes |
| `soc.json` | Tatsächliche Messung und ursprünglicher Frischenachweis |
| `forecast.json` | Tatsächlich importierte PV-Daten in Originalbytes |
| `report.json` | Der zu diesen PV-Daten gehörige Prüfbericht |
| `sync-state.json` | Dauerhaft gespeicherter erfolgreicher Claim des Zyklus |
| `sync-report.json` | Dauerhaft gespeicherter Original-Erfolgsbericht vor Archivstatus |
| `solution-<version>.json` | Unveränderte Speicherung der Antwort mit Parametern, Freigaben und Ergebnissen |

Die vier Eingabeartefakte werden vor Claim und dem ohnehin regulären Dispatch
eingefroren. Das Request-Receipt bindet exakt den vorhandenen POST-Body, den
quantisierten SoC und die Mitternachts-/Laufzeitbasis. Die Rückgabe enthält die
tatsächlichen run-relativen Last-/PV-/Preis-/Vergütungsreihen, Batterie- und
Wechselrichterparameter, GENETIC-Freigaben, Ergebnisreihen und Endwertkurve.
Sie werden nicht aus einer Konfigurationsdatei oder späteren Prognosen ergänzt.

Zusätzlich speichert der neue Writer `producer.dispatch_series_binding`:

- `contract = eos-pv-helper/replay-ready-archive-v1`
- `start_utc`, `interval_seconds`
- `series`: vor Dispatch aus den bereits gelesenen Serien integrierte Werte für
  `pv_forecast_wh`, `total_load`, `electricity_price_per_wh`, `feed_in_tariff_per_wh`
- `series_sha256`: kanonischer Hash dieser vier Reihen

Diese privaten Werte sind Teil des Manifests, keine zusätzlichen Archivdateien
oder Logdaten. Sie müssen zur ursprünglichen Claim-Zeitachse und zu sämtlichen
gespeicherten Modellintervallen im Control-/Tail-Fenster passen. Die bestehende
numerische v2-Toleranz bleibt erhalten (Energie 1e-6 Wh, Preis 1e-12 EUR/Wh,
relative Toleranz 1e-9). Ein abweichender Last- oder Tarifcache während der
regulären Optimierung führt zu `evidence_missing`, niemals zu Ersatzwerten.

Ein Jahreslastwert und vollständige atomare Suchoptionsprovenienz werden vom
ursprünglichen EOS-Antwortvertrag nicht geliefert. Die bereits vorhandenen
`observed_options` bleiben eine sichere Beobachtung der gelesenen Einstellungen;
`exact_solver_options_proven=false` bleibt wahr. Modellreplay erfordert die
gespeicherten Modellparameter und Freigaben, keine neue Suchentscheidung.

## Erfolg, Commit und Wiederaufnahme

1. Unverändert exklusiver `sync.lock`, unveränderte Versionsbildung und Eingabe-/
   Frische-/Slot-Gates. Der ursprüngliche Claim wird vor dem POST `uncertain`.
2. Nach bestätigter Antwort wird die Lösung wie bisher dauerhaft gespeichert.
   Nur dann werden erfolgreicher State und Originalreport geschrieben. Ein
   Archivfehler ändert diesen ursprünglichen Ausführungsclaim nicht.
3. Vor jeder finalen Veröffentlichung: sieben Bytehashes, originaler Claim,
   Original-Lösung, Chronologie, v2-Request-/Eingabebindung, alle Doctor-Checks,
   automatischer Producer und konsistenter Runtime-Kontext werden geprüft.
   Die unveränderte `economics.project` prüft außerdem die strukturelle
   Kompatibilität mit der Admission aus PR #27. Dabei läuft **kein** Modell.
4. Das vollständige ZIP wird privat geschrieben, erneut gelesen/validiert,
   dateiseitig `fsync`-gesichert, Modus 0400. Exklusive Hardlinks publizieren
   zuerst `.pending/<version>.ready`, danach atomar `<version>.zip`.
   Die jeweiligen Verzeichnisse werden synchronisiert. Vorhandene finale
   Dateien werden niemals ersetzt. Bei einem Konflikt wird nun das vollständige
   validierte Manifest verglichen, nicht nur die Liste der Artefakthashes.
5. Erst dann erhält der aktuelle Report `evidence.status=archived` mit ZIP-Hash,
   Vertragskennung und `replay_admission.status=ready_for_native_replay`.
   `native_result_verified=false`: Erst der getrennte Worker beweist mit seinen
   zwei festen nativen Rechnungen die numerische Reproduzierbarkeit.

Der Worker aus PR #27 bleibt bytegleich. Er liest nur finale ZIPs, hält den
Original-Lock kurz shared/nonblocking, prüft seine eigenen Herkunftsbindungen
und veröffentlicht erst danach Sidecar und Katalog. Sein nativer Exporter,
seine Hash-/Energiebasis und der Dashboard-Reader bleiben unverändert.

Spätere Sync-Ticks derselben Version übernehmen die Planidentität aus dem
ursprünglichen persistierten Claim in den aktuellen Report. Sonst fehlten dort
Start/Horizont/Intervall und der Worker erkannte einen Report-/Claim-Konflikt.
Es werden dabei keine heutigen Eingaben und kein fehlendes altes Request-Receipt
übernommen; der archivierte Originalreport bleibt unverändert.

Bei Neustart darf ausschließlich ein vollständig vorhandenes, erneut geprüftes
`.ready` publiziert werden. Abbruch vor diesem Punkt kann einen fehlenden
Nachweis hinterlassen. Ein unbekanntes `.writing-*` ist kein Erfolg; keine
Rekonstruktion, kein weiterer POST, kein Reset von `uncertain` oder `succeeded`.
Diese Grenze gilt auch für Festplattenausfall/Platzmangel. Ein Prozessabbruchtest
ist kein Versprechen über Stromausfallkonsistenz des NAS-Dateisystems.

## Status- und Fehlervertrag

| Status | Aussage |
|---|---|
| kein `evidence` | Kein erfolgreicher ausgewählter Lauf oder Archivierung nicht freigegeben |
| `evidence_missing` | Originaler Erfolg kann bestehen; vollständiger Archivreplay-Nachweis fehlt |
| `archived` / `ready_for_native_replay` | Vollständiger geprüfter Commit; strukturelle Worker-Admission erfüllt |
| Worker `verified` | Zwei feste native Replays stimmen einschließlich Flussbilanz mit dem Original überein |

Neue feste Ablehnungsgründe sind `archive_saved_model_not_replay_compatible`,
`archive_replay_binding_not_proven`, `archive_dispatch_solver_series_differ` und
`archive_dispatch_series_binding_invalid`. Die bisherigen sicheren Diagnosen
bleiben erhalten. Archivefehler verschlechtern Health, erzeugen aber weder
erneute Dispatches noch Geräteaktionen. Die Logs enthalten keine Reihen,
Parameter, Tokens oder Rohkonfigurationen.

Vollständige historische Archive ohne neue optionale Serienbindung werden nur
nach ihren bereits vorhandenen Verträgen gelesen. Ihre Bytes werden nicht
angepasst. Lösungen ohne damaliges finales Archiv bleiben ohne Archivnachweis.
Bestehende historische Sidecar-Importe ändern niemals damalige Erfolgsclaims.

## Paketnachweis

Der separate Docker-Buildtarget `evidence-candidate` erbt `eos-source` mit
unverändertem Non-root-Benutzer, Standard-CMD, DRY_RUN und Healthcheck. Er enthält
einen code-only Fähigkeitsnachweis unter
`/usr/share/eos-pv-helper/licenses/evidence-writer.json` mit SHA256 der tatsächlich
installierten Writer-/Sync-/Doctor-/Validierungs-/Speichermodule. Das ist keine
Produktivfreigabe und ersetzt die bestehende Lizenz-/Quelleninventur nicht.

Der Container-Smoke prüft diese installierten Dateien gegen die Checkoutbytes,
ohne `/app/src` oder `site-packages` zu übermounten. Nur der öffentliche
synthetische Transport und die öffentliche Modellfixture werden read-only
eingebunden. Ein separater Worker bekommt ausschließlich die erzeugten
Originale read-only und sein privates Replay-Volume read-write.
