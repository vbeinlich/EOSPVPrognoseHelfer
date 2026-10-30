# Validierung für v0.1.0 nach dem Merge, 30.10.2026

Aktueller Nachweis: [RELEASE_0_1_0_READINESS.md](RELEASE_0_1_0_READINESS.md).
PR #3 wurde als `55e1bd8` gemergt; Main-CI
[41063469358](https://github.com/vbeinlich/EOSPVPrognoseHelfer/actions/runs/41063469358)
ist erfolgreich. Der neue Readiness-Stand ergänzt reale Download-/Archivprüfpfade,
Workflow-Policy-Mutationstests und private OCI-/Runtime-/Quellenverifikation.
**302 Tests** mit nativer EOS-Integration lokal bestanden; Ruff, Actionlint und
Compose grün. Kandidaten-/CI-Belege und Freigabestatus stehen im Readiness-Bericht.
Neuer privater Vollimage-Build erfolgreich, Offline-Smoke mit 192 Intervallen
bestanden. UID 10001, CapEff=0, NoNewPrivs=1 und DRY_RUN=true bestätigt.
Alle OCI-Blobs, Config/Rootfs, tatsächliches Inventar und vollständiges Quellen-
archiv geprüft: [Kandidatennachweis](RELEASE_0_1_0_CANDIDATE.json).
[Push-CI](https://github.com/vbeinlich/EOSPVPrognoseHelfer/actions/runs/41066776595)
und [PR-CI](https://github.com/vbeinlich/EOSPVPrognoseHelfer/actions/runs/41066889174)
am Quellcommit `47bd424...` erfolgreich. Letzter reiner Nachweis-Commit wird vor
Reviewbereitschaft in [PR #8](https://github.com/vbeinlich/EOSPVPrognoseHelfer/pull/8/checks)
ebenfalls geprüft. Echte private Doctor-Abnahme und formale Freigaben bleiben offen.
Alle Tests verwenden synthetische Daten und isolierte lokale Container; kein
produktiver Import, Forecast-Abruf oder zusätzlicher GENETIC-Lauf.

Die Prüfabdeckung umfasst Rechte, Dry-run, Read-only, Secrets im Repository,
Workflow-Veröffentlichungspfade und Artefakthashes. Keine aktuelle CVE-Freiheit
wird behauptet; es wurde keine externe Schwachstellen-API abgefragt.

## Historischer Stand 29.10.2026

**Historisches Protokoll.** Der Audit vom 30.10.2026 hat einen Veröffentlichungs-
Bypass außerhalb des damaligen Stable-Gates gefunden. Maßgeblich sind jetzt die
[Korrekturen und aktuellen Nachweise](RELEASE_BLOCKER_RESULTS.md). Automatisches
Image-Publishing wurde vollständig entfernt; siehe [neue Checkliste](RELEASE_CHECKLIST.md).

Ergänzung zu den [realen Betreiberbelegen](UNRAID_VALIDATION.md). Die folgenden
Tests liefen isoliert auf dem Entwicklungsrechner, ohne produktive Schreibzugriffe,
Optimierungsläufe, externe Prognoseabrufe oder Änderungen bestehender Container.

| Prüfung | Ergebnis |
| --- | --- |
| Vollständige pytest-Suite einschließlich gepinntem nativen EOS | **216 bestanden** |
| Ruff für `src`, `tests`, `scripts` | bestanden |
| Actionlint 1.7.12 | bestanden |
| `docker compose config --no-path-resolution --quiet` | bestanden |
| `git diff --check` | bestanden |
| Docker-Ziel `eos-source`, Python 3.11, gepinnter EOS-Quellstand | erfolgreich gebaut |
| `scripts/unraid_smoke.py --image eos-pv-helper:release-prep` | bestanden, `network=none`, 192 synthetische Viertelstunden |
| Paket-/Image-Lizenztest | eigenes Wheel `License-Expression=MIT` samt LICENSE; EOS-NOTICE/Apache-Text und Inventar im Image vorhanden |
| Tatsächliches Inventar des lokalen Vollimages | 110 Python-Komponenten, 105 OS-Copyright-Nachweise; Quellenarchive DEAP, moocore, SciPy, loguru, dnspython |
| Reale automatische GENETIC-Abnahme | **bestätigt**: Betreiberbeleg, gespeicherte Datei und unabhängiger lesender Schema-/Doctor-Lösungscheck; [Beleg](GENETIC_ABNAHME.md) |
| Stable-Release-Gate bei alleiniger GENETIC-Abnahme | wird erwartungsgemäß abgewiesen: vollständiger Live-Doctor-Beleg, Lizenzreview und ausdrückliche Release-Freigabe bleiben getrennt |

Neue Tests belegen insbesondere:

- Doctor liest vorhandene Sync-Artefakte ohne HTTP oder Dateiveränderung; aktive
  Writer, fehlende/kaputte Lösungen, falscher Start/Intervall, nicht endliche
  Kosten, unzulässige Steuerwerte, abweichender Preis-/Claim-Hash, unsicherer
  Versionspfad, veraltete Reports und falsche SoC-Belege werden abgelehnt.
- `waiting-publication` wird von tatsächlicher Abnahme getrennt; auch ein
  vorhandenes Lösungsfile ersetzt keinen bestätigten `succeeded`-Claim.
- Neuer Regressionstest bildet den Betreiberfall ab: evcc liefert trotz extern
  schon bekannter Preise zunächst nur den aktuellen Tag; mehrere reguläre Ticks
  warten ohne POST. Nach tatsächlicher Veröffentlichung löst ein normaler Tick
  genau einen Lauf aus. Persistierter Claim und unveränderte Lösung verhindern
  nach erneuter Instanziierung einen zweiten POST; der Doctor bestätigt den Verlauf.
- Beim SoC-Mismatch erfolgt höchstens ein frischer gemeinsamer State-GET;
  ursprünglicher Gerätebeleg, 300-s-Grenze und Auswahl einer einzelnen Batterie
  bleiben erhalten. Kein zweiter Geräte-Getter. Verbleibende Abweichung, Timeout,
  Fehler, Duplikate, fremde Version oder unplausible Leistung bleiben gesperrt.
- Preise verwenden nach einem erfolgreichen Retry denselben erneuerten Snapshot.
- Eigene MIT-Metadaten, Vendor-Notices, LGPL-Quellarchivbehandlung und exakt
  versionierte fehlende Upstream-Lizenzen werden geprüft; unbekannte fehlende
  Lizenzen lassen den Build fehlschlagen.
- Stabile Tags sind von Kandidaten getrennt; Promotion folgt erst Registry-Test
  und realem Abnahme-/Inventarbeleg. Ausstehende/abweichende Belege sperren.

Am 30.10. wurde die exakte GCC/libquadmath-Zuordnung ergänzt, einschließlich
Distributorpatches. Die erweiterte Prüfung deckt auch OS-Quellen, MPL-Zertifikate,
ODbL-Daten und eingebettetes lxml/libiconv ab. [Aktuelle Lizenzprüfung](LICENSE_REVIEW.md).
Veröffentlichtes Quellmaterial und konkrete Freigaben bleiben getrennte Gates.
Kein stabiler Tag, Merge oder Release wurde durch lokale Prüfungen freigegeben.

CI-Ergebnisse müssen sich auf den veröffentlichten aktuellen PR-Commit beziehen;
ein älterer grüner Lauf ist kein Nachweis für diese Änderungen. Der unveränderte
Template-Digest in `IMAGE_PUBLICATION.json` bezeichnet weiterhin das bereits
real vom Betreiber eingesetzte Vorgängerimage; Vorschau-Publishing aktualisiert
keinen produktiven Helfer. [Abschluss-Schritte und Gates](RELEASE_CHECKLIST.md).
