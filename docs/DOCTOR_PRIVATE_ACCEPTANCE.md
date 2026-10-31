# Private Doctor-Abnahme ohne neuen Produktionslauf

Stand 31.10.2026. Die GENETIC-End-to-End-Abnahme aus Issue #1 bleibt gültig;
die vollständige private Doctor-Abnahme für den Release ist weiterhin offen.

Verbindliche aktualisierte
[Operator-Anleitung](doctor-export-review/OPERATOR_RUNBOOK.md) und
[Prüfbericht](doctor-export-review/REVIEW.md). Die alten Vier-Artefakt-Anweisungen
werden dadurch ersetzt, nicht zusätzlich zur neuen Anleitung ausgeführt.

Der neueste Produktionsbericht `waiting-publication` ohne Event-Version widerlegt
die zwei gespeicherten erfolgreichen Claims nicht. Er enthält aber nicht mehr
die ursprünglichen Eingaben. Die Anwendung versioniert Claims und Lösungen,
überschreibt jedoch Report, Preise, SoC und Prognose. Der heutige Export dieser
Dateien ist kein historischer Eingabennachweis.

Die korrigierte Abnahme prüft ein ausgewähltes Erfolgsereignis aus einem vorhandenen
vollständigen historischen Snapshot (Schema 2), unabhängig vom neuesten Report.
Sie verlangt sieben Rohartefakte, Hash-/Event-/Preiszuordnung, passenden Claim und
Lösung, SoC-/PV-Eingaben und vollständige Zeitachsen. Schema 1 mit vier Rohartefakten
wird für diese vollständige Abnahme als unvollständig abgelehnt.

Historische Frische gilt zum unveränderten `claimed_at_utc` des Dispatchs:
SoC höchstens 300 s bzw. strengere Grenze, Leseabschluss vor Dispatch.
Erhebungszeit wird weder ersetzt noch zurückdatiert.
`evidence_mode=historical_snapshot`, `historical_reference_kind=persisted_claim`,
`current_freshness_verified=false`. Der Live-Doctor prüft weiter die aktuelle Uhrzeit.

Fehlt ein vollständiger damaliger Snapshot-/Backup-Satz, bleibt die Abnahme
blockiert. Keine Messwerte rekonstruieren, aktuellen Preise unter eine alte Version
stellen oder neue Optimierungen auslösen. Der normale Betrieb wird nicht geändert.

Hashes beweisen Konsistenz, keine vertrauenswürdige Herkunft. Betreiber muss
Originalerhebung, tatsächliche Grenzen und Kandidatenbezug separat bestätigen.
`historical_snapshot_operator_approved`, `operator_approved` und Lizenzfreigaben
werden nicht automatisch gesetzt. `GENETIC_ACCEPTANCE.json` bleibt unverändert.
Private Messwerte, Konfigurationen, Tokens und Archive niemals nach GitHub.

Der alte `scripts/doctor_snapshot.py` bleibt zur Reproduzierbarkeit unverändert,
ist aber nicht mehr die Anleitung für vollständige neue Abnahmen.
Produktiver Helfer und eingefrorene Releaseartefakte werden nicht aktualisiert.
