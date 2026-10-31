# Unabhängiger Review der lokalen Doctor-Exportdateien

Stand 31.10.2026. Die Vorbereitung existierte bereits in PR #9. Die beiden vom
Betreiber benannten lokalen Dateien waren jedoch älter. Dieser separate Review-PR
baut auf PR #9 auf; weder PR #9 noch dieser PR werden automatisch gemergt.
Es wurde nichts auf Unraid ausgeführt und keine reale private Abnahme behauptet.

## Vollständige unveränderte Originale

| Lokale Datei / vollständige Kopie | SHA256 der Originalbytes |
| --- | --- |
| [DOCTOR_OPERATOR_STEPS.md](local-originals/DOCTOR_OPERATOR_STEPS.md) | `98111e0abbbe95260b7f63e567d68117b7fe5e00c7be8fff45f64bca739e24a9` |
| [unraid-doctor-export.sh](local-originals/unraid-doctor-export.sh) | `5749ecd60abb1fc627ad1126bdafd1c21b41138ba2054565bfb2d5a256029fb6` |

Beide Texte wurden vollständig gelesen und bytegleich übernommen. Sie enthalten
keine Messdaten, Zugangsdaten, produktiven IP-Adressen oder Exportarchive.
Die lokalen Originaldateien werden nicht überschrieben. Die Kopien sind
Reviewmaterial, nicht die zur neuen Ausführung vorgesehene Variante.

## Befund

- Originalskript: nur lokale Docker-Lesezugriffe/lesender Python-Export; kein
  POST, Sync, Import, Optimiereraufruf, Containerupdate oder Claim-/Lösungsreset.
- Der Exporter aus `47bd424...` wird gegen
  `56a950467d27482bf3361c0739f6cccab394dcbe04d3c0238255119d6bbc8ca5`
  geprüft. Er hält ein nicht blockierendes Shared-Lock über der vollständigen
  Dateierhebung. Daten-/Quellzeitstempel werden nicht geändert.
- Ein frischer privater mktemp-Ordner und Noclobber schützen vorhandene Exporte.
  Das Original schreibt jedoch direkt auf den endgültigen ZIP-Namen; bei Abbruch
  kann dort eine leere/partielle Datei zurückbleiben. Ein separater reiner Vorabtest
  und die zusätzliche Inhalts-/Integritätsprüfung aus PR #9 fehlen lokal.
- Die TOML und Token-Dateien werden nicht kopiert. Exportiert werden genau Report,
  State, kanonischer Preis-Snapshot und passende Lösung plus Hashmanifest.
  Rohartefakte bleiben privat; die neue Fassung blockiert zusätzlich erkannte
  Token-/Passwort-/Konfigfelder und typische Credentials vor der ZIP-Ausgabe.

## Zur Ausführung vorgesehene Fassung

[`scripts/unraid-doctor-export.sh`](../../scripts/unraid-doctor-export.sh),
SHA256 `65bac0c457795079ba703c68ec7a48e89c0fc097108c14f51621389fcec6d0fd`.
Der ausführbare Fix-Quellstand wird nach dem Code-Commit eingetragen. Die
Downloadvorlage mit `FIX_COMMIT` bis dahin nicht verwenden.
Sie enthält die Schutzprüfungen aus PR #9 und zusätzlich `--check-only` als
sicheren Standard ohne Argumente. Nur `--export` erzeugt einen Export:

- Vorabtest erzeugt keine Dateien, lädt nichts herunter und exportiert keine Werte.
  Er liest vorhandene Dateien unter Shared-Lock, prüft die passende erfolgreiche
  Claim-Version, JSON-Lesbarkeit und vorhandene TOML. Ausgabe enthält nur Status.
- Export nimmt später sein eigenes Lock; ein früherer Vorabtest ist keine
  zeitlich unbegrenzte Freigabe oder Frische-/Doctor-Abnahme.
- `--export` prüft den gepinnten Exporterhash, Stream-/ZIP-Integrität und Whitelist
  im Speicher. Nur bei Erfolg erscheint eine fertige ZIP; Fehler/erkannte Secrets
  führen zum Abbruch ohne Veränderung oder Bereinigung produktiver Originale.
- Neue Diagnoseausgaben ausschließlich in privatem `/tmp`-Ordner; keine Änderungen
  an bestehender Appdata, Konfiguration, Status, Claims oder Lösungen.

### Korrektur der Container-Erkennung

Der reale Unraid-Befund zeigt, dass die Image-Anzeige von `docker ps` den Tag/
Digest weglassen kann. Deshalb werden ausschließlich laufende IDs aufgelistet;
für jede ID liest `docker inspect` selektiv `.State.Running` und `.Config.Image`.
Akzeptiert wird genau ein noch laufender Container aus dem exakten Repository,
mit optionalem gültigem Tag und/oder vollständigem `sha256`-Digest. Andere
Registries, Präfix-Lookalikes, fehlerhafte Digests und mehrere Treffer brechen ab.
Inspektionsfehler werden nicht als Abwesenheit interpretiert. Kein Image-Pull,
kein Start/Stop und kein Zugriff auf andere Containerdateien.

Die Mount-, Shared-Lock-, Exporter-SHA256- und Privacy-/ZIP-Prüfungen bleiben
erhalten. Die tatsächliche Image-ID/Referenz wird weiterhin privat protokolliert.
Die Auswahl ist keine neue Distributionsfreigabe oder Remote-Image-Verifikation.

## Ausführung und Bewertung

[Kurzanleitung](OPERATOR_RUNBOOK.md). Technisch ist diese Fassung zur rein lesenden
Operatorausführung geeignet, wenn die unabhängige Prüfung abgeschlossen ist und
der Vorabtest erfolgreich ist. Tatsächliche Container-/Dateizugriffsrechte werden
erst vor Ort bestätigt. Hier keine produktive Ausführung und keine pauschale
Distributions-/Releasefreigabe.

Tests verwenden ausschließlich synthetische Dateien und Fake-Docker/Curl, aber
den echten gepinnten Exporter und echte Shared-/Exclusive-Locks. Originalhashes,
Privacy, konsistente Rohbytes, fehlende/Symlink-Dateien, falsche Hashes, aktive
Writer und fehlerhafte Optionen werden geprüft. Drei echte Optimiererläufe
werden in der Review-CI gezielt ausgenommen; keine neue GENETIC-Simulation.
Lokaler Stand nach Erkennungsfix: **353 bestanden, 3 gezielt deselected**,
darunter 37 Wrapper-Tests. Der reale Fall mit gekürzter Image-Anzeige ist als
Regression abgedeckt, ebenso Tag-/Digest-Referenzen, mehrere Treffer, falsche
Images, gestoppte Container und Inspect-Fehler. Ruff,
Actionlint, Compose, Bash-Syntax und diff-check erfolgreich. Die konkreten
CI-Links am geprüften Head stehen in [PR #10](https://github.com/vbeinlich/EOSPVPrognoseHelfer/pull/10/checks);
keine Optimiererausführung. Der PR basiert für einen kleinen unabhängigen Delta-
Review auf PR #9; die zusätzliche Dokumentation ändert den ausführbaren Quellstand nicht.

Die private Doctor-Abnahme bleibt offen bis zum erfolgreich geprüften echten
Export einschließlich bestätigter Herkunft. `GENETIC_ACCEPTANCE.json`, Kandidat,
Releaseartefakte und alle Approval-Flags bleiben unverändert.
