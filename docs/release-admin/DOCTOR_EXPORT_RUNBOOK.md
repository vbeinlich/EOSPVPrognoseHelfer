# Unraid-Export und spätere Offline-Auswertung

> **Ersetzt am 31.10.2026:** Für vollständige historische Abnahmen ausschließlich
> die [aktuelle Anleitung](../doctor-export-review/OPERATOR_RUNBOOK.md) verwenden.
> Das unten dokumentierte alte Vier-Artefakt-Verfahren belegt historische SoC-/PV-
> Eingaben nicht vollständig. Bei `waiting-publication` keine heutigen Preise mit
> alten Lösungen verbinden. Die folgenden Befehle bleiben nur als historische
> Dokumentation erhalten und sind nicht die aktuelle Ausführungsempfehlung.

Die reale Doctor-Abnahme läuft separat beim Betreiber. Dieser PR liefert nur
geprüfte Werkzeuge und synthetische Tests, keinen echten Abnahmebeleg. Bestehende
konsistente Exporte bleiben nutzbar; nicht allein für einen neuen Wrapper erneut
exportieren. `doctor=null` und alle Freigaben bleiben unverändert.

## Was geprüft wurde

[`scripts/unraid-doctor-export.sh`](../../scripts/unraid-doctor-export.sh) verwendet
ausschließlich Unraids lokalen Docker-Socket. Genau ein laufender Helfer und die
vorhandenen Mountziele `/output` und `/app/config.toml` müssen erkennbar sein.
Andernfalls Abbruch, kein Start/Stop/Update und keine geratenen Alternativpfade.
Es gibt keine produktiven Schreibbefehle, POSTs, Importe oder Optimiereraufrufe.

Der unveränderte Exporter aus `47bd42468ffbf2876143ba950512e968825a5f53` wird
vor Ausführung gegen SHA256
`56a950467d27482bf3361c0739f6cccab394dcbe04d3c0238255119d6bbc8ca5`
geprüft. Nur Python-Standardbibliothek, keine Installation im Helfer. Nicht
blockierendes Shared-Lock, Originaldateien und Originalzeitstempel unverändert.

ZIP-Guard prüft vor Ausgabe im Speicher die exakte Fünf-Dateien-Whitelist,
Größenlimits und jeden Artefakthash. Bekannte Token-/Secret-/Konfigurationsfelder
und typische Credential-Muster führen zum Abbruch, ohne Rohwerte auszugeben.
Die ZIP-Bytes werden nicht umgeschrieben oder bereinigt. Erst nach Erfolg wird
die leere/temporäre `.partial`-Datei zum endgültigen Archiv umbenannt.

Tests verwenden Fake-Docker/Fake-Curl und echte Exporter-/Lock-Funktionen:
keine Quelldateiänderung, keine Konfig-/Secret-Canaries im entpackten ZIP,
sofortiger Lock-Fehler, Hash-/ZIP-Fehler, fehlende/Symlink-Dateien und uneindeutige
Container. Ein Inhaltsfilter ersetzt keine private Herkunfts-/Inhaltsprüfung;
auch ein korrektes ZIP enthält private Mess- und Preisdaten und gehört nie nach GitHub.

## Exakte Ausführung auf Unraid

Nur den nach Review ausgewählten Wrapper aus diesem PR privat nach Unraid
übertragen. Vor Ausführung seine SHA256 mit dem dokumentierten Stand vergleichen;
nicht ungeprüft eine bewegliche Branch-URL ausführen. Die konkrete Wrapper-
Revision und ihr Hash stehen im [Restarbeiten-Bericht](../RELEASE_0_1_0_FINAL_GATES.md).

Nach Review kann der exakt geprüfte Wrapper in der Unraid-Root-Konsole in einen
neuen privaten Ordner geladen und hashgeprüft ausgeführt werden. Diese Befehle
wurden hier **nicht auf Unraid ausgeführt**:

```sh
umask 077
set -eu
set -C
wrapper_dir=$(mktemp -d /tmp/eos-doctor-wrapper.XXXXXXXX)
curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' --max-time 60 \
  https://raw.githubusercontent.com/vbeinlich/EOSPVPrognoseHelfer/0a8d70612d3ff82929c60a924ba346ff28f1a30d/scripts/unraid-doctor-export.sh \
  --output "$wrapper_dir/unraid-doctor-export.sh"
printf '%s  %s\n' 6aaa96f93a2bd166671003edc861b59f18d58a8e8fb717b9b789af1d62fc82ca "$wrapper_dir/unraid-doctor-export.sh" | sha256sum -c -
bash "$wrapper_dir/unraid-doctor-export.sh"
```

Das Skript erzeugt ausschließlich einen **neuen** privaten Diagnoseordner
`/tmp/eos-v010-doctor.*`, Modus 0700/Dateien 0600. Es protokolliert UTC-Zeit,
begrenzte Container-/Imageherkunft, Exporterskript-Revision und SHA256-Werte.
Keine vollständigen Inspect-/Env-Ausgaben, keine Konfiguration/Token-Datei wird
kopiert. Die TOML wird im Helfer nur für Zeitzone und bestehende Prüfgrenzen gelesen.

Nur Exitcode 0 und die Meldung `Export successful` bestätigen die Exporterstellung.
Das ist **keine Doctor-Abnahme**. Bei Fehler den privaten Diagnoseordner erhalten,
später mit neuem Ordner erneut versuchen; keinen Sync/GENETIC-Lauf erzwingen.
Bei unbekanntem Container oder Mount die tatsächliche Zuordnung lesend prüfen.
Keine neue Helferinstanz und keine Rechteänderungen an produktiven Originalen.

Den ausgegebenen Ordner vor einem Neustart sicher auf den Diagnose-Rechner
übertragen; `/tmp` ist flüchtig. ZIP, `SHA256SUMS.txt`, `runtime.json`,
`image-origin.json` und Erhebungs-/Skriptherkunft gemeinsam privat aufbewahren.
Ein unbekannter Origin-Wert muss durch den Betreiber geklärt werden, nicht ergänzt.

## Offline auf dem Diagnose-Rechner

Vorher ZIP-SHA256 mit `SHA256SUMS.txt` vergleichen. Auf diesem Windows-Rechner:

```powershell
Get-FileHash -Algorithm SHA256 C:\Users\volke\eos-v010-private\doctor-snapshot.zip
docker --context desktop-linux run --rm --network none --read-only --cap-drop=ALL --security-opt=no-new-privileges --user 10001:10001 --mount type=bind,source=C:\Users\volke\eos-v010-private\doctor-snapshot.zip,target=/private/snapshot.zip,readonly eos-pv-helper:v010-private doctor --snapshot /private/snapshot.zip
$LASTEXITCODE
```

Das vorhandene private lokale Image verwenden, nichts auf Unraid pullen oder
installieren. Nur die einzelne Diagnosekopie muss lesbar sein. Kein Docker-Socket,
keine Live-Konfiguration und keine produktiven Datenverzeichnisse mounten.
Ergebnis auf der Konsole prüfen; einen privaten JSON-Bericht anschließend als
UTF-8 sichern, keine PowerShell-5-Textumleitung für das binäre Export-ZIP verwenden.

Abnahme erfordert Exitcode 0, `accepted=true`, alle Checks wahr, vier passende
Artefakthashes, Preis-/Eventversion, persistierten `succeeded`-Claim und zugehörige
Lösung. Es gilt ausdrücklich `evidence_mode=historical_snapshot` und
`current_freshness_verified=false`. Die SoC-300-s-Grenze bzw. strengere konfigurierte
Grenze gilt zum echten Erhebungszeitpunkt, nicht erst beim späteren Öffnen.
Keine Zeitstempel zurückdatieren oder fehlende Messwerte ergänzen.

Herkunft durch den Betreiber bestätigen lassen. Erst nach separater Freigabe darf
ein autorisierter Reviewer einen bereinigten Nachweis für das aktive Release-Gate
vorbereiten. Dieser Ablauf schreibt keine Freigabeflags und löst keine Simulation aus.
