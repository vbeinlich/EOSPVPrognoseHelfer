# Phase-2-Review: konkrete Prüfnachweise

Stand 31.10.2026. Separater Review-Branch `release/issue-6-economics`, auf dem
offenen Phase-1-PR #14 aufgebaut. Kein Merge, Release, Deployment oder Produktivtest.
Vollständige [Modelldefinition und private Abnahme](ECONOMICS_COMPARISON.md).

## Tatsächlich lokal geprüft

- **374 Tests bestanden, 3 echte Optimierer-Tests ausdrücklich ausgeschlossen.**
  Vollständiger Lauf im lokalen Entwicklungscontainer, Netzwerk aus, Quellmounts
  und RootFS read-only; temporäre EOS-Konfiguration ausschließlich im tmpfs.
- **73 gezielte Tests als UID 10001**: Reader, Wrapper, Wirtschaftlichkeit und
  native Wiedergabe mit read-only RootFS/Quellmount und ohne Netzwerk.
- Native Forward-Replays: volle Wirkungsgradkette, DC-basierter LCOS, PV-Laden
  ohne Netzladung, Leistungs-/SoC-Begrenzung durch dieselben EOS-Geräteklassen,
  Preisverschiebung mit +0,40 und −0,40 EUR, negative Preise, End-SoC-Fairness,
  900/3600-s-Energieäquivalenz. Kein `optimize_ems()`; HTTP und Optimierer werden
  in diesen Integrationstests zusätzlich per Fail-Hook blockiert.
- Datenfehler: fehlende SoC-/PV-/Last-/Preise-/Gerätewerte, NaN, inkonsistente
  Längen/Aliase/Zeitraster/Versionen, unklarer Zeitbezug, nicht unterstützte Modelle,
  abweichender Original-Replay, falsche Endkurve und veränderte native Quelldateien.
- Kostenrechnung: Netzbezug minus Erlös plus Verschleiß, Verluste nicht doppelt
  monetarisiert, gemeinsame Kurve nur einmal, tatsächlicher Endzustand nach letztem
  Slot, positive und negative Vorteile; keine Prozente bei nicht positiven Referenzkosten.
- Export: `waiting-publication` blendet historische Pläne nicht aus. Keine heutigen
  Preis-/SoC-/PV-/Konfigurationsdateien gelesen, keine Writes/HTTP/Simulation im
  NAS-Reader. Hashes, Dateibytes und mtimes der synthetischen Quellen unverändert.
- Zwei echte lokale Altcontainer-Consumer: Produktions-Digest `7e957da3…` und
  privater eingefrorener Kandidat (Image-ID `56fab872…`). UID 10001, kein Netzwerk,
  RootFS/Quellvolume read-only, `python -I -S -B`, keine aktuellen Projektmodule
  gemountet/importierbar. Stdlib-Bundle exportiert eine vollständige numerische
  Projektion und meldet den notwendigen Offline-Vergleich statt Traceback.
- Echter Übergabetest: numerischer Export aus dem alten Produktionsimage im
  separaten nativen Offline-Container verarbeitet. Vollständiger synthetischer
  Plan berechnet; zweiter, unvollständiger Plan ausdrücklich nicht berechenbar.
- Zwei echte Edge-Browserprüfungen: berechnete Kostenansicht und fehlende Eingaben;
  Planauswahl, 96 Viertelstunden-/24 Originalstunden-Zeilen, 72 Steuerbalken,
  Slot-Details, Kostenkomponenten und Last-Annahmetest. Je **0 externe Requests,
  0 Browserfehler**. Screenshot ausschließlich synthetisch und privat lokal.
- Ruff, Actionlint 1.7.7 (ohne optionale Shellcheck-/Pyflakes-Plugins),
  JavaScript-Syntax, Compose-Konfiguration und `git diff --check` erfolgreich.

## Private reale Ausgangsdaten

Die bereits vorhandenen lokalen GET-Antworten der Pläne vom 29. und 31.10. wurden
unverändert und offline ausgewertet. Native Original-Replays einschließlich Kosten
und Endenergie bestanden. Input-Hashes vor/nach der Auswertung unverändert.
Private Ergebnisse, komplette Eingaben und Reportdateien bleiben außerhalb Git.
Diese Ergebnisse sind weder eine vollständige Doctor-Abnahme noch gemessene
Einsparungen. Der private Originaldatensatz vom **30.10. fehlt lesbar**: ausdrücklich
„Nicht berechenbar“. Keine Preise, SoCs oder Prognosen aus Nachbartagen übernommen.

Der 11.251/8.000-kWh-Vergleich ist ein gekennzeichneter linearer Annahmetest auf dem
vorhandenen Profil, keine behauptete historische Konfiguration und kein neuer
optimierter Plan. Freigaben und historische Endwertkurve werden festgehalten.

## CI und unabhängiger Review

Die Review-CI führt Unit-/Integrationsprüfungen, den echten alten Container und
zusätzlich eine native synthetische Kosten-/Browserprüfung aus. Der Ausschluss
echter Optimiererlauf-Tests gilt jetzt unabhängig vom Branch-Namen; AST-/CI-Tests
prüfen diese Grenze. Main-Push-, Tag- und Preview-Publishing-Sperren unverändert.

Der tatsächliche Head-CI-Status ist im separaten Review-PR zu prüfen. Dieser lokale
Bericht behauptet keinen noch nicht abgeschlossenen GitHub-Lauf und ersetzt keine
Betreiberfreigabe. Die CI erhält ausschließlich synthetische Daten; keine privaten
Reports als Workflow-Artefakte.

## Noch offen

1. Unabhängiger Code-/Modellreview und ausdrückliche spätere Integrationsfreigabe.
2. Privater Operator-Export aller drei Originalpläne und Herkunftsbestätigung;
   insbesondere fehlenden 30.10.-Datensatz bereitstellen, ohne ihn zu rekonstruieren.
3. E3/DC-Referenzannahmen, Batterieparameter/LCOS und individuelle Lastqualität
   fachlich kalibrieren. Endwert-Sensitivität beachten.
4. Eine neue 11.251-kWh-Prognose bzw. erneute Optimierung nur nach gesondertem Auftrag.
5. Plan-vs-Ist, reale Kosten und realisierte Einsparungen sind nicht Teil dieses PRs.

Review-Code-Bundle SHA256:
`ca3d2d8543ca9923b9024c3b1ad5d683fcd8cb5b01d84d13a180cdc47662a8a8`.
Wrapper SHA256, UTF-8/LF:
`aeb5a12796adf8a940c18ac289643e8fd4f54a2cd2e6ec2b1e1861bb4c31c1fd`.
Diese Hashes sind weder Release-Digests noch Betreiberfreigaben.
