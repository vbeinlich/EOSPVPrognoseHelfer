# Issue #12 – Review-Nachweise

Basis: Main `5688084ad3ea7bdc7cd603c09ade65293e8609c7`, eigener Branch
`release/issue-12-genetic-evidence`. Kein gestapelter PR auf #9/#10.
Die benötigte eigenständige Engine wird bytegleich aus PR #10 / `45ee76c`
wiederverwendet; die Umsetzung benötigt keinen vorgezogenen Merge dieser PRs.

| Prüfung | Ergebnis |
| --- | --- |
| Vollständige lokale Suite mit gepinntem EOS-Quellcode, Netzwerk aus | **326 bestanden, 3 Optimierer-Tests ausdrücklich ausgenommen** |
| Neue Archivierungsfälle | 25 bestanden |
| Reale Container-Consumer im exakten Produktions-Digest `7e957da3…` | 5 Szenarien bestanden; `doctor.py` fehlt, Helfer nicht importierbar |
| Reale Container-Consumer im eingefrorenen OCI-Kandidaten `69d4e197…` | 5 Szenarien bestanden; keine Entwicklungsquellcode-Mounts |
| Originaler privater OCI-Kandidat und Quellenarchiv | Hashes, Blobs, Config/RootFS, Inventar und Quellenbindung erneut bestätigt |
| Ruff, Actionlint, Compose, diff-check | erfolgreich |
| Zusätzliche API-Aufrufe oder geänderter Dispatch-Payload | vollständiger Mock-HTTP-Trace mit deaktivierter Archivierung identisch |
| Historische Doctor-Abnahme nach späterem Waiting | erzeugtes Schema-2-Archiv wird ohne aktuelle Preise/SoC/PV erfolgreich geprüft |
| Aktive Freigaben, Produktionssysteme, PR #10 | unverändert |

Die konkreten CI-Läufe und der endgültige Head werden im separaten Review-PR
verlinkt. CI lädt nur den unveränderlichen alten öffentlichen Image-Digest und
verwendet ausschließlich vom neuen Writer **synthetisch** erzeugte Nachweise.
Keine privaten Archive werden hochgeladen. Das private OCI-/Quellenarchiv bleibt
lokal und wird nicht durch einen neuen Build ersetzt.

Engine-SHA256 ohne abschließenden Zeilenumbruch:
`d4d713cd53c3a94621032ea7aeb2c76b5787b96e53ec8658544ab248c896a564`.

Kandidatensource: `47bd42468ffbf2876143ba950512e968825a5f53`.
OCI: `sha256:69d4e1974bb5190d6fd63b2533c5e1c71e23589dd1e1314c6744659dcbded61a`.
Archiv-SHA256: `6b7f4a79272fe732e57da7929c1efcef75277c55b62adbf29d87eaedc67cf265`.
Inventar-SHA256: `222261b5a20a816a335fb2011fccdbb57c20fe34fc08b6f86c6b2e9fc3b6b93f`.
Quellenarchiv-SHA256: `ecdf8cbc6ac27e892713af1cf1ffef43fbb9c4fb0f6f3118c64a34463fcf3308`.
Diese Werte gelten für den alten Kandidaten, **nicht** für einen späteren Build mit
der neuen automatischen Schreibfunktion.

[Schema, Schreibreihenfolge, Fehlergrenzen, Migration und Doctor-Prozedur](GENETIC_EVIDENCE.md).
Insbesondere sind Unterbrechungen vor einer vollständigen Ready-Datei keine
garantiert rekonstruierbaren Transaktionen; fehlende Belege bleiben sichtbar.

**Abweichung des ersten lokalen Prüflaufs:** Auf der Main-Basis fehlten zunächst
die drei GENETIC-Testmarker; dadurch liefen drei synthetische Optimierungen in
einem lokalen, netzwerkisolierten Wegwerfcontainer. Kein produktiver Zugriff.
Die Marker und eine AST-/CI-Schutzprüfung sind nun enthalten; der endgültige
326-Test-Lauf und die Review-CI schließen die drei Optimierer explizit aus.

Offene Gates: unabhängiger Review, neues gesondert geprüftes Image/Deployment und
Opt-in nur nach Betreiberfreigabe, Hardlink-/fsync-Unterstützung des tatsächlichen
Unraid-Output-Volumes sowie private Abnahme beim nächsten regulären Ereignis.
Kein Merge, Release, Rollout, Backfill oder Abschluss von Issue #12 durch diesen Nachweis.
