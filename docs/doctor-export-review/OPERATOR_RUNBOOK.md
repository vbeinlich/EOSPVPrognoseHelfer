# Doctor: aktueller und historischer Nachweis

Stand 31.10.2026. Keine Befehle hier auf Unraid ausgeführt. Kein Export ist eine Releasefreigabe.

## Geprüften Wrapper bereitstellen

Quellcommit: `STANDALONE_SOURCE_COMMIT`.
Wrapper-SHA256: `5645bac00aa0f2d1c3480ce9e8b4c7dee5a4ebe2fbe68f80d195af695b9c63c3`.
Engine-SHA256 ohne abschließenden Zeilenumbruch:
`d4d713cd53c3a94621032ea7aeb2c76b5787b96e53ec8658544ab248c896a564`.

Die neue Engine wird bytegleich eingebettet, vor Ausführung hashgeprüft und mit
`python -I -S -B -c` im bestehenden Container ausgeführt. Ausschließlich Python-3.11-Standardbibliothek
und System-Zeitzonendaten, keine Projekt-/EOS-/Astral-Module vorausgesetzt.
Mit `-I -S` ist das installierte Helfer-Paket nicht importierbar. Tatsächliche
Kompatibilität siehe [Container-Nachweis](CONTAINER_COMPATIBILITY.md).
Kein Download, keine Installation
und kein Update bei Vorabtest oder Export. Der alte gepinnte Exporter
`scripts/doctor_snapshot.py` bleibt unverändert, wird aber nicht mehr verwendet:
Seinem Vier-Artefakt-Format fehlen die gespeicherten SoC-/PV-Eingaben.

Nach unabhängigem Review den Wrapper privat kopieren oder den festen Stand laden:

```sh
umask 077
wrapper_dir=$(mktemp -d /tmp/eos-doctor-reviewed.XXXXXXXX)
curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' --max-time 60 \
  https://raw.githubusercontent.com/vbeinlich/EOSPVPrognoseHelfer/STANDALONE_SOURCE_COMMIT/scripts/unraid-doctor-export.sh \
  --output "$wrapper_dir/unraid-doctor-export.sh"
printf '%s  %s\n' 5645bac00aa0f2d1c3480ce9e8b4c7dee5a4ebe2fbe68f80d195af695b9c63c3 "$wrapper_dir/unraid-doctor-export.sh" | sha256sum -c -
```

Bei Curl-/Hashfehler nicht ausführen. Im Folgenden `/PRIVATE/unraid-doctor-export.sh`
durch den tatsächlichen geprüften Pfad ersetzen. Archivierte lokale Originale
unter `local-originals` sind ausschließlich Reviewmaterial.

## 1. Rein lesender Vorabtest

```sh
bash /PRIVATE/unraid-doctor-export.sh --check-only
rc=$?
printf 'Vorabtest-Exitcode: %s\n' "$rc"
```

Erfolg: Exitcode 0, `preflight=passed`, `shared_lock_verified=true`,
`artifact_count=7`, `export_created=false`, `doctor_acceptance=false`.
Keine Dateien, Downloads oder privaten Messwerte in der Vorabtest-Ausgabe.

Beim bestätigten `waiting-publication` ohne Event-Version und mit zwei Erfolgen
ist ohne historische Eingaben ein begründeter Abbruch erwartet:
`Historical input evidence incomplete ... 2 succeeded claim(s) do not prove saved prices/SoC/PV`.
Kein Lock-/Modbus-/Optimierungsfehler. Keine Optimierung starten, Claims löschen
oder Dateien umbenennen, um die Diagnose zu umgehen.

## 2. Vorhandenes historisches Ereignis auswählen

Ein vollständiges Schema-2-ZIP enthält `snapshot.json` und sieben unveränderte
Rohartefakte derselben Erhebung: `sync-report.json`, `sync-state.json`,
`prices.json`, `soc.json`, `forecast.json`, `report.json`,
`solution-<version>.json`. Erfolgsreport, Preisversion, SoC-Beweis und PV-Daten
müssen zum gewählten Claim gehören. Ein altes Schema-1-ZIP mit vier Rohartefakten
reicht nicht. Den Versionsplatzhalter durch die echte Archiv-/Claim-Version ersetzen:

```sh
bash /PRIVATE/unraid-doctor-export.sh --check-only \
  --historical-snapshot /PRIVATE/EXISTING-HISTORICAL.zip \
  --event-version ACTUAL_64_HEX_EVENT_VERSION
rc=$?
printf 'Historischer Vorabtest-Exitcode: %s\n' "$rc"
```

Es wird kein vermeintlich jüngster Erfolg gewählt: Archivversion bzw. explizite
Version bestimmt genau ein Ereignis. Aktuelle Preise, SoC, Prognose und Bericht
werden hierbei nicht als historische Eingaben gelesen. Unter Shared-Lock werden
persistierter erfolgreicher Claim und exakte Lösungsbytes mit dem Archiv verglichen.

**Ohne vollständige alte Eingaben hier stoppen.** Ein konsistenter damaliger
privater Backup-Satz kann zuerst offline geprüft werden. Nicht aus heutigen Dateien
eine Vergangenheit zusammensetzen oder Zeitstempel, Messwerte und Manifeste
rekonstruieren. Der neue Parser erzeugt keine verlorene Historie. Die private
Abnahme bleibt dann offen; dieser Auftrag fordert keinen neuen GENETIC-Lauf an.

## 3. Export nach erfolgreichem Vorabtest

Mit denselben historischen Optionen, oder ohne Optionen nur bei vollständig
belegtem ursprünglichem Erfolgszyklus:

```sh
bash /PRIVATE/unraid-doctor-export.sh --export \
  --historical-snapshot /PRIVATE/EXISTING-HISTORICAL.zip \
  --event-version ACTUAL_64_HEX_EVENT_VERSION
rc=$?
printf 'Export-Exitcode: %s\n' "$rc"
```

Erfolg: 0 und neuer privater `/tmp/eos-v010-doctor.…`-Ordner. Erneutes Shared-Lock,
Inhalts-/Hash-/Privacy-Prüfung vor ZIP-Ausgabe und unabhängige Streamprüfung.
Historische ZIP-Bytes und `captured_at_utc` bleiben exakt erhalten; der heutige
Exportzeitpunkt steht getrennt in `operator-observed-at-utc.txt`.

```sh
cd /tmp/eos-v010-doctor.TATSAECHLICHER_SUFFIX
sha256sum -c SHA256SUMS.txt
sha256sum doctor-snapshot.zip
sha256sum historical-doctor.py
```

ZIP, mitgelieferte Engine und Herkunftsdateien privat sichern. Keine TOML, Tokens,
Env-Dumps oder evcc-Rohantworten im Export. `.partial` ist kein Erfolg.
Bei Lockbelegung später erneut prüfen, keinen Writer stoppen. `/tmp` ist flüchtig.
Archive, Messwerte und Secrets niemals nach GitHub hochladen.

## 4. Offline auf dem Diagnose-Rechner

ZIP und `historical-doctor.py` privat übertragen; Hashes mit Unraid vergleichen.
Das vorhandene private Diagnose-Image genügt, die neue Engine wird nur lokal
read-only eingebunden. Beispiel PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 C:\Users\volke\eos-v010-private\doctor-snapshot.zip
Get-FileHash -Algorithm SHA256 C:\Users\volke\eos-v010-private\historical-doctor.py
docker --context desktop-linux run --rm --pull=never --network none --read-only --cap-drop=ALL --security-opt=no-new-privileges --user 10001:10001 --entrypoint python --mount type=bind,source=C:\Users\volke\eos-v010-private\doctor-snapshot.zip,target=/private/snapshot.zip,readonly --mount type=bind,source=C:\Users\volke\eos-v010-private\historical-doctor.py,target=/private/historical-doctor.py,readonly eos-pv-helper:v010-private -I -S -B /private/historical-doctor.py --snapshot /private/snapshot.zip
$LASTEXITCODE
```

Alternativ im Entwicklungscheckout mit installierten Abhängigkeiten:
`python -B -m eos_pv_helper doctor --snapshot PRIVATE.zip`.
Im produktiven Image fehlt `doctor.py`; im eingefrorenen Diagnose-Kandidaten
kennt der alte eingebaute Doctor das neue Schema nicht. Deshalb ausdrücklich
die mitgelieferte eigenständige Engine verwenden. Kein Netzwerk, Docker-Socket,
Live-Output oder produktive Konfiguration mounten. Kein `--write-eos`/Refresh.

## 5. Ergebnis und Fehler

Erforderlich: Exitcode 0, `accepted=true`, alle Checks wahr, sieben Artefakthashes,
`capture_manifest_sha256`, `evidence_mode=historical_snapshot`,
`historical_reference_kind=persisted_claim`, `current_freshness_verified=false`.

`historical_reference_utc` ist das unveränderte gespeicherte `claimed_at_utc`:
SoC höchstens 300 s bzw. strengere Grenze **damals**, Lesebeweis vor Dispatch
abgeschlossen. Originale Erhebungszeit und heutige Prüfzeit bleiben getrennt.
Kein Rückdatieren. Fehlende/abweichende Versionen, Eingaben, Hashes oder Lösungen
sperren die Abnahme mit Diagnose. Hashes authentifizieren die Herkunft nicht:
Betreiber muss Originalerhebung, tatsächliche Grenzen und Kandidatenbezug prüfen.
Alle historischen Betreiber-, Lizenz- und Releasefreigaben bleiben separat offen.
