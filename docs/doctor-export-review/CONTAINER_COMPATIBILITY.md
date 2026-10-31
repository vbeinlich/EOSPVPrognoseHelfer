# Doctor: Nachweis gegen tatsächliche Containerstände

Stand 31.10.2026. Ausschließlich lokale Docker-Desktop-Kopien, keine Verbindung
zu Unraid, keine produktiven Dateien, keine neue Optimierung. Alle Eingaben der
Kompatibilitätstests sind synthetisch. Kein realer privater Abnahmebeleg.

## Ursache und geprüfte Abhängigkeiten

Der bisherige Test nutzte nur den privaten Kandidaten. Dieser enthält `doctor.py`,
das tatsächlich produktive Preview-Image dagegen nicht. Der vorherige Import von
`eos_pv_helper.doctor.acceptance` konnte dort bereits vor der Fehlerbehandlung
abbrechen. Die neuen Tests unterscheiden diese beiden unveränderten Image-Stände:

| Nachweis | Produktive Image-Version als lokale Kopie | Eingefrorener Kandidat |
| --- | --- | --- |
| Referenz | `ghcr.io/vbeinlich/eospvprognosehelfer@sha256:7e957da3e2fdb67456a46e5538ad3c74b43fa21892d2998e93bca9de83d9daf7` | OCI `sha256:69d4e1974bb5190d6fd63b2533c5e1c71e23589dd1e1314c6744659dcbded61a` |
| Quellrevision | `b648a61699854d325eceb5f823f6de999a989525` | `47bd42468ffbf2876143ba950512e968825a5f53` |
| Python | 3.11.18 | 3.11.18 |
| `doctor.py` vorhanden | nein | ja |
| `inputs.py` / `normalize.py` vorhanden | ja / ja | ja / ja |
| `historical.py` vorhanden | nein | nein |
| Neue Engine: sechs reale Container-Szenarien | bestanden | bestanden |

Der lokale Kandidat `eos-pv-helper:v010-private` hat Docker-ID
`sha256:56fab8727a38a7e4931c43635d13cd891a17e17992bd4a813a79019807828359`.
Diese ID wird nicht mit dem OCI-Manifestdigest gleichgesetzt. Vor seinem Test
wurde die Bindung mit `candidate_verify.py` erneut geprüft: OCI-Blobs, Config,
RootFS-Diff-IDs, Labels, Inventar und zugehöriges Quellenarchiv stimmen überein.

- OCI-Archiv-SHA256: `6b7f4a79272fe732e57da7929c1efcef75277c55b62adbf29d87eaedc67cf265`.
- Config-Digest: `sha256:93a64948ffe62a5462422b5a880d7d388be7ee68f46b63cb8c88fde87e1650ff`.
- Inventar-SHA256: `222261b5a20a816a335fb2011fccdbb57c20fe34fc08b6f86c6b2e9fc3b6b93f`.
- Quellenarchiv-SHA256: `ecdf8cbc6ac27e892713af1cf1ffef43fbb9c4fb0f6f3118c64a34463fcf3308`.

## Eigenständige Engine

Keine Projektimporte mehr: ISO-Zeitprüfung, endliche Zahlen, Delivery-Day-Hash,
Intervallabdeckung, SoC-/Import-/Claim-/Lösungsprüfungen sind direkt enthalten.
Die bestehenden Abnahmebedingungen bleiben erhalten. Tests vergleichen die
Ablehnungen mit dem bisherigen Doctor-Vertrag und die Preisversionsbildung an
normalen, 23- und 25-Stunden-Liefertagen. Historische Fehlermeldungen sind bereinigt;
das erwartete `waiting-publication` ohne Eingaben liefert Exitcode 1 und eine
verständliche JSON-Diagnose, keinen Python-Traceback.

Die Engine braucht Linux-Python 3.11 und dessen Standardbibliothek einschließlich
`fcntl`, `tomllib`, `zoneinfo` sowie die System-Zeitzonendaten. Diese Voraussetzungen
sind in beiden tatsächlichen Images durch erfolgreiche Ausführung geprüft.
`python -I -S -B` deaktiviert Projektpfade, Site-Packages und Bytecode-Schreiben.
Der Test bestätigt ausdrücklich `helper_visible_in_isolated_interpreter=false`.
Weder EOS, Astral noch ein installiertes Helfer-Modul sind erforderlich.

## Dauerhafter echter Container-Test

[`doctor_container_smoke.py`](../../scripts/doctor_container_smoke.py) startet
kurzlebige, automatisch entfernte Container des zuvor inspizierten Image-IDs.
`--pull=never`, lokaler Docker-Kontext, Netzwerk aus, read-only RootFS, UID 10001,
Capabilities entfernt, `no-new-privileges`. Nur synthetische Daten sind read-only
gemountet; kein Repository, keine Projektmodule und kein Docker-Socket im Testcontainer.
Die Engine kommt als geprüfter Code über `python -c` wie beim Wrapper.

Sechs Szenarien je Image:

1. `waiting-publication`, zwei erfolgreiche Claims/Lösungen, fehlende Historie:
   klare Ablehnung ohne Traceback und ohne Dateien zu ändern.
2. Vollständiger historischer Vorabtest trotz Waiting und anderer aktueller Eingaben.
3. Erfolgreiche Offline-Abnahme des vollständigen synthetischen Snapshots.
4. Fehlerhafter Preisartefakthash: Ablehnung.
5. Abweichende ausgewählte Event-Version: Ablehnung.
6. Synthetische ZIP-Ausgabe bytegleich mit dem ursprünglichen Archiv; Zeiten bleiben
   erhalten. Kein echter Export. Eingabebytes und mtimes vor/nach allen Szenarien gleich.

Reproduktion auf einem lokalen Diagnose-/Entwicklungsrechner mit vorhandenem Image:

```sh
python scripts/doctor_container_smoke.py --docker-context LOCAL_DEVELOPMENT \
  --image ghcr.io/vbeinlich/eospvprognosehelfer@sha256:7e957da3e2fdb67456a46e5538ad3c74b43fa21892d2998e93bca9de83d9daf7 \
  --expect-no-doctor
python scripts/doctor_container_smoke.py --docker-context LOCAL_DEVELOPMENT \
  --image eos-pv-helper:v010-private
```

Vor dem Kandidatentest zusätzlich die bekannte OCI-/Quellenbindung nach der
Release-Anleitung prüfen. Kein Remote-Docker-Kontext wird akzeptiert. Das Skript
zieht oder baut keine Images und kontaktiert keine laufenden Produktivcontainer.

Die CI lädt ausschließlich den bereits veröffentlichten **unveränderlichen**
Produktions-Digest zur Regression und führt den echten Container-Test aus. Sie
veröffentlicht dadurch kein Image. Das private Kandidatenarchiv wird nicht in CI
hochgeladen; dessen obiger Test wurde separat lokal durchgeführt.

## Hashes und Status

Review-Quellcommit: `STANDALONE_SOURCE_COMMIT` (vor Ausführung fest pinnen).
Wrapper-SHA256: `5645bac00aa0f2d1c3480ce9e8b4c7dee5a4ebe2fbe68f80d195af695b9c63c3`.
Eingebettete Engine ohne Schluss-Zeilenumbruch:
`d4d713cd53c3a94621032ea7aeb2c76b5787b96e53ec8658544ab248c896a564`.

409 Unit-/Integrationstests bestanden, drei echte Optimiererläufe ausgenommen.
Zusätzlich je sechs reale Szenarien in Produktionsimage und Kandidat bestanden.
Ruff, Actionlint, Bash-Syntax, Compose und diff-check erfolgreich. Endgültige CI
am Review-Head in [PR #10](https://github.com/vbeinlich/EOSPVPrognoseHelfer/pull/10/checks).

Private reale Doctor-Abnahme, Betreiber- und Lizenzfreigaben bleiben offen.
Keine Änderung der Kandidatenartefakte, kein Merge, kein Release und keine
Veröffentlichung durch diese Korrektur.
