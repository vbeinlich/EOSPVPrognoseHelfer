# Doctor-Export: aktuelle Anleitung und eingeschraenkte Legacy-Abnahme

Die alte Anleitung ist durch den gemeinsamen versionierten Pruefvertrag ersetzt.
Verbindlich sind [Operator-Schritte](../doctor-export-review/OPERATOR_RUNBOOK.md),
[Pruefvertrag v2](../INPUT_BINDING_CONTRACT.md) und
[aktuelle Code-/Transporthashes](../INPUT_BINDING_TRANSPORTS.json).

Ein Vier-Artefakt-Snapshot ist kein vollstaendiger historischer Nachweis.
Sieben unveraenderte Originale ohne damals gespeicherten Request-Beleg bleiben
lesbar, aber `legacy_limited` / Exit 2 / `accepted=false`.
Keine alten Reportdateien ergaenzen, keine Zeitstempel oder Claims aendern.

Der neue Wrapper und die eigenstaendige Engine werden nur nach Review privat
bereitgestellt. Weder ein neu gebautes Image noch eine Produktionsoptimierung
ist fuer die Offline-Lesebewertung vorhandener Archive notwendig.
Skript- und ZIP-Hashes sowie Herkunft gesondert dokumentieren; keine privaten
Messwerte oder Zugangsdaten nach GitHub hochladen.

Die reale private Doctor-Abnahme, Administration, Lizenz-/Distributionsfreigaben
und Issue #21 bleiben offen. Keine neuen Befehle auf Unraid in diesem Auftrag.
