# Kurzanleitung für den geprüften Doctor-Export

Nur die in [REVIEW.md](REVIEW.md) identifizierte neue Skriptfassung verwenden.
Originale unter `local-originals` sind ausschließlich Reviewmaterial. Skript
privat nach Unraid kopieren; dessen SHA256 vor Ausführung vergleichen:

```sh
printf '%s  %s\n' d60871dc64f67041842e9089c864e0a0cbb90dc29161c620bed0e6bad986cd1d /PRIVATE/unraid-doctor-export.sh | sha256sum -c -
```

## 1. Rein lesender Vorabtest – Unraid-Root-Konsole

```sh
bash /PRIVATE/unraid-doctor-export.sh --check-only
rc=$?
printf 'Vorabtest-Exitcode: %s\n' "$rc"
```

Erwartet: Exitcode 0, `preflight=passed`, `read_only=true`,
`shared_lock_verified=true`, `export_created=false`, `doctor_acceptance=false`.
Keine Ausgabedateien und kein Download. Bei Fehler stoppen, Container/Mounts/
Leserechte bzw. normalen laufenden Sync prüfen. Nicht stoppen oder umkonfigurieren.
Auch ein Aufruf ohne Argumente macht ausschließlich diesen Vorabtest.

## 2. Export – nur nach erfolgreichem Vorabtest

```sh
bash /PRIVATE/unraid-doctor-export.sh --export
rc=$?
printf 'Export-Exitcode: %s\n' "$rc"
```

Erwartet: 0 und `Export successful; private directory: /tmp/eos-v010-doctor.…`.
Das Skript prüft erneut unabhängig den Lock und den SHA256 des Originalexporters.
Kein manueller Sync, POST, Quellenrefresh oder GENETIC-Aufruf.

## 3. Privates ZIP und Hash prüfen

Den tatsächlich ausgegebenen privaten Verzeichnispfad verwenden:

```sh
cd /tmp/eos-v010-doctor.TATSAECHLICHER_SUFFIX
sha256sum -c SHA256SUMS.txt
sha256sum doctor-snapshot.zip
```

Nur bei Export-Exitcode 0, fertiger ZIP und passenden Hashes übertragen. Eine
`.partial`-Datei oder ein fehlendes Hashfile ist kein Erfolg. Fehler nicht durch
Umbenennen oder Zeitänderungen beheben. Bei belegtem Lock später einen neuen
Export versuchen; keinen Optimierungslauf erzwingen. Private Daten nie nach GitHub.
`/tmp` ist flüchtig: ZIP, Hash-/Herkunftsdateien vor Neustart sicher übertragen.

## 4. Offline auf dem Diagnose-Rechner

ZIP als private Diagnosekopie unter dem bekannten lokalen Pfad ablegen und Hash
gegen den echten Unraid-Wert vergleichen. Beispiel für PowerShell, ausschließlich
auf dem Diagnose-Rechner mit vorhandenem lokalen privaten Image:

```powershell
Get-FileHash -Algorithm SHA256 C:\Users\volke\eos-v010-private\doctor-snapshot.zip
docker --context desktop-linux run --rm --network none --read-only --cap-drop=ALL --security-opt=no-new-privileges --user 10001:10001 --mount type=bind,source=C:\Users\volke\eos-v010-private\doctor-snapshot.zip,target=/private/snapshot.zip,readonly eos-pv-helper:v010-private doctor --snapshot /private/snapshot.zip
$LASTEXITCODE
```

Kein Pull/Deployment auf Unraid und kein produktiver Docker-Socket. Nur die
einzelne Diagnosekopie muss für den gewählten Benutzer lesbar sein; keine
produktiven Originalrechte verändern. Kein `--write-eos` oder `--refresh-source`.

## 5. Erwartetes Ergebnis

Erst Exitcode 0, `accepted=true`, alle Checks wahr, vier passende Artefakthashes,
konsistente Preis-/Eventversion und `succeeded`-Claim mit zugehöriger Lösung
erfüllen den technischen Doctor-Nachweis. Herkunft aus `runtime.json`,
`image-origin.json`, Skriptrevision und tatsächlicher Erhebung vom Betreiber
bestätigen lassen. Hashes allein authentifizieren den Ursprung nicht.

Historische Prüfung: `evidence_mode=historical_snapshot`,
`current_freshness_verified=false`. Report-/SoC-Alter werden zum echten
Erhebungszeitpunkt bewertet, SoC maximal 300 s oder strengere konfigurierte Grenze.
Keine Messwerte ergänzen oder Zeiten zurückdatieren. Bei Fehler bleibt die
Abnahme offen; ein erfolgreicher Export allein ist keine Doctor-/Releasefreigabe.

Diese Befehle wurden hier nicht auf Unraid ausgeführt. Keine private Datei,
Konfiguration, IP-Adresse oder Zugangsdaten werden im Review-PR veröffentlicht.
