# Plan-Inspector Phase 1 – Review-Nachweise

Eigener Branch `release/issue-6-plan-inspector` auf Main
`5688084ad3ea7bdc7cd603c09ade65293e8609c7`, unabhängig von PR #10/#13.
Keine Produktivdateien oder Datenarchive für die Tests verwendet.

| Prüfung | Ergebnis |
| --- | --- |
| Vollständige lokale Suite mit gepinntem EOS, Netzwerk aus | **332 bestanden, 3 Optimierer-Tests ausdrücklich ausgespart** |
| Neue Reader-/Bundle-/Wrapper-Fälle | 31 bestanden, zusätzlich Non-root/read-only geprüft |
| Produktionsimage `7e957da3…` | echtes Bundle über denselben Bootstrap erfolgreich; keine installierten Helfer-Module und kein Source-Mount |
| Privater eingefrorener Kandidat, lokale Docker-ID `56fab872…` | derselbe Consumer erfolgreich, Artefakte unverändert |
| Echter lokaler Edge-Browser | zwei Pläne auswählbar, 96 Viertelstunden-/24 Originalstunden-Zeilen, 72 Steuerbalken, Slot-Details erfolgreich |
| Externe Seitenanfragen / Browserfehler | **0 / 0** |
| Quellbytes und mtimes | vor/nach Lesen unverändert; Schreib-/Netzwerkversuche zusätzlich blockiert |
| Ruff, Actionlint, Bash-Syntax, Compose, diff-check, JS-Syntax | erfolgreich |

Die CI wiederholt Reader-Tests, den echten Produktionsimage-Consumer und einen
echten statischen Browser-Test. Konkrete Läufe und Commit stehen im Review-PR.
Code-Bundle/HTML/PNG werden nicht als öffentliche Release-Artefakte hochgeladen.
Alle Tests bleiben synthetisch; diese Tabelle ist keine reale Anlagenabnahme.

Geprüfte Sonderfälle: 900/3600 s, DST-Frühjahr/-Herbst, explizite Legacy-Zeitbasis,
abweichende Claim-Zuordnung, Waiting, mehrere Pläne, fehlende/defekte Lösungen,
ungleiche oder ungültige Werte, gebundene historische Preise/PV nur aus vollständigem
Schema-2-Archiv, falsche Lösungsbytes, Privacy-/XSS-Canaries, anonymisierte Geräte,
Shared-Lock belegt/fehlend, falscher Bundle-Hash und konkurrierende/falsche Container.

Der eigenständige Validator entspricht bytegleich PR #10 / `45ee76c`, SHA256 ohne
Schluss-Zeilenumbruch `d4d713cd53c3a94621032ea7aeb2c76b5787b96e53ec8658544ab248c896a564`.
Keine Änderung am produktiven Image, am eingefrorenen Kandidaten, Sync-Ablauf,
GENETIC-Trigger, Claims, vorhandenen Lösungen oder Release-/Lizenzfreigaben.

Vorbereitete Code-Dateien und **konkrete private Unraid-Anleitung** einschließlich
Hashes: [PLAN_INSPECTOR.md](PLAN_INSPECTOR.md).

Offen: unabhängiger Review und reale private Sichtprüfung der vorhandenen Lösungen
durch den Betreiber. Kein Merge/Release/Deployment. Phase 2 mit Referenzsimulation
und Einsparungsrechnung ist nicht implementiert; keine entsprechende Abnahme behauptet.
