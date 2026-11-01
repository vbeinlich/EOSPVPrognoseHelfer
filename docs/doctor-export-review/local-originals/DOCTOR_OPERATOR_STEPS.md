# Private Doctor-Abnahme nach Merge von PR #8

Das Skript unraid-doctor-export.sh ist eine Operatorvorlage und wurde NICHT auf Unraid ausgeführt.
Keine produktiven Dateien wurden geändert. Nur ein neuer privater Diagnoseordner unter /tmp wird bei Ausführung angelegt.

1. Das Skript privat auf Unraid übertragen und in der Unraid-Root-Konsole ausführen:

    bash /PRIVATE/unraid-doctor-export.sh

   Es identifiziert genau einen laufenden Helfer anhand des GHCR-Images, prüft die
   vorhandenen Mountziele, verifiziert den geprüften Exporter per SHA256 und exportiert
   nur bestehende Dateien unter Shared-Lock. Kein Start/Stop/Update und keine Simulation.
   Falls die eindeutige Auswahl oder der Zugriff scheitert: stoppen, tatsächliche
   Container-/Mountzuordnung lesend prüfen, keine zweite Instanz starten.
   Bei belegtem Lock oder fehlendem passenden Event das nächste reguläre Ereignis
   abwarten. Keinen manuellen Sync/POST oder Optimierungslauf auslösen.

2. Den ausgegebenen privaten /tmp-Ordner vor einem Unraid-Neustart sicher auf den
   Diagnose-Rechner kopieren. Insbesondere ZIP, SHA256SUMS.txt und Provenienzdateien
   erhalten. Nichts nach GitHub hochladen; ZIP enthält private Mess-/Preisdaten.
   /tmp ist flüchtig. Die Skriptausführung nur mit Exitcode 0 als erfolgreichen
   Export behandeln; eine nach Fehler vorhandene Teil-ZIP ist kein Beleg.

3. Auf diesem Windows-Diagnose-Rechner die ZIP als
   C:\Users\volke\eos-v010-private\doctor-snapshot.zip bereitstellen.
   SHA256 vorher mit dem auf Unraid erzeugten SHA256SUMS.txt vergleichen:

    Get-FileHash -Algorithm SHA256 C:\Users\volke\eos-v010-private\doctor-snapshot.zip

4. Nur auf dem Diagnose-Rechner, NICHT auf dem produktiven Unraid, ausführen:

    docker --context desktop-linux run --rm --network none --read-only --cap-drop=ALL --security-opt=no-new-privileges --user 10001:10001 --mount type=bind,source=C:\Users\volke\eos-v010-private\doctor-snapshot.zip,target=/private/snapshot.zip,readonly eos-pv-helper:v010-private doctor --snapshot /private/snapshot.zip

   Das bereits vorhandene lokale private Image verwenden. Nicht auf Unraid pullen
   oder installieren. Nur diese einzelne Diagnosekopie muss für UID 10001 lesbar
   sein; keine Rechte an produktiven Originalen ändern.

5. Für die Abnahme nötig: Exitcode 0, accepted=true, alle Checks wahr, vier
   konsistente Artefakthashes, Preis-/Eventversion und passender succeeded-Claim
   samt Lösung. runtime.json und image-origin.json mit der tatsächlichen
   Herkunft abgleichen; der historische Erhebungszeitpunkt muss bestätigt sein.
   Unbekannte Herkunft oder fehlende Origin-Labels vom Betreiber klären.

   evidence_mode=historical_snapshot und current_freshness_verified=false sind
   zwingend. 300 Sekunden SoC-Alter bzw. strengere konfigurierte Grenze gelten
   zur echten Erhebung. Alter Bericht oder fehlende Werte werden nicht repariert,
   Zeiten niemals rückdatiert. Der Operator bestätigt die Herkunft getrennt.
   Synthetische Tests ersetzen keinen realen privaten Doctor-Beleg.

Die Freigabeflags bleiben false. Erst nach echter Abnahme darf ein autorisierter
Reviewer einen bereinigten Nachweis für eine spätere Freigabe vorbereiten.
