# Formale Lizenz-/Distributionsprüfung: Kandidat v0.1.0

**Technische Unterlagen vorhanden; formale Freigabe ausstehend.**
[Ausfüllbare Vorlage](license-review-template.json), getrennt vom aktiven
`GENETIC_ACCEPTANCE.json`. Kein Werkzeug überträgt Entscheidungen automatisch.

| Bindung | Genau geprüfte Bytes |
| --- | --- |
| Source | `47bd42468ffbf2876143ba950512e968825a5f53` |
| OCI-Digest | `sha256:69d4e1974bb5190d6fd63b2533c5e1c71e23589dd1e1314c6744659dcbded61a` |
| Roh-Inventar SHA256 | `222261b5a20a816a335fb2011fccdbb57c20fe34fc08b6f86c6b2e9fc3b6b93f` |
| Quellenarchiv SHA256 | `ecdf8cbc6ac27e892713af1cf1ffef43fbb9c4fb0f6f3118c64a34463fcf3308` |

OCI-Archiv, alle Blobs, tatsächliches Inventar und Quellenarchiv wurden für diesen
Auftrag erneut geprüft. Konfiguration/Rootfs passen zum lokalen privaten Image.
615 Source-/Notice-Payloads stimmen mit dem konkreten Inventar überein. Kein
Neubau und keine Änderung an diesen Artefakten. Neue Admin-/Exporthilfen liegen
als MIT-Quellcode im neuen PR, nicht nachträglich im eingefrorenen Image/Archiv.

## Durch den benannten Reviewer zu bestätigen

- Eigener Code MIT, keine pauschale Umlizenzierung des Containers. EOS Apache-2.0
  inklusive NOTICE; CPython-/Debian-/Python-/Vendor-Originaltexte erhalten.
- 110 Python-Distributionen und 105 OS-Pakete, darunter 73 exakte Debian-Source-
  Versionen/235 Quelldateien. Original-Notices im Image unter
  `/usr/share/eos-pv-helper/licenses`, Detailmatrix in [LICENSE_REVIEW.md](../LICENSE_REVIEW.md).
- LGPL: DEAP/moocore-Sources, passende GCC-SRPMs für libquadmath 4.8.5/8.5.0,
  Distributorpatches und Rebuildanweisungen. lxml/libiconv 1.18 einschließlich
  statischer Relinkmöglichkeit, passender nativer Quellen und bereits belegtem
  unabhängigen Änderungs-/Rebuild-Test. GCC-Runtime-Exceptions korrekt beibehalten.
- MPL-certifi inklusive bearbeitbarer Quellen; ODbL-Zeitzonendaten samt
  Attribution, unverändertem Datensatz und passendem Reader. Unicode-/Font-/Codec-
  und weitere verschachtelte Notices nicht entfernen.
- Das vollständige exakte Quellenangebot muss **vor** erster neuer öffentlicher
  Image-Verteilung anonym erreichbar sein. Die geplante versionierte URL ist
  aktuell nicht veröffentlicht. Promotion überprüft später Hash und Inhalt erneut.

Die technische Prüfung belegt die Zuordnung und Vollständigkeit des Materials,
keine unabhängige juristische Distributionsentscheidung. Bei rechtlichen Zweifeln
muss der verantwortliche Reviewer die offene Frage klären. Keine aktuelle CVE-
Freiheit oder unabhängig geprüfte Debian-Signaturschlüssel werden behauptet.

## Noch fehlend

1. Reviewer-Identität, Zuständigkeit, Reviewzeit und ausdrückliche Entscheidung.
2. Vollständiger privater Doctor-Beleg mit bestätigter Herkunft; separat beim Betreiber.
3. Nach ausdrücklicher Veröffentlichungserlaubnis tatsächliches öffentliches
   Quellenangebot und dessen anonyme Rückprüfung. Hier keine Veröffentlichung.
4. Betreiberfreigabe für die konkrete Distribution und erfüllte GitHub-/GHCR-Gates.

Bis dahin `approved=false`, Reviewer/Zeit/Entscheidung `null`; alle aktiven
Freigabeflags bleiben unverändert. Bei anderem Digest oder Source-Archiv neue
Prüfung, keine nachträgliche Anpassung eines bereits freigegebenen Hashes.
