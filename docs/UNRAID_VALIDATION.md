# Abnahmeprotokoll zu Issue #4

Stand: 29.10.2026. Diese Datei unterscheidet isolierte Tests von der inzwischen
vom Betreiber durchgeführten echten Unraid-Installation. Die lokalen Testbelege
stammen aus der Betreiber-Rückmeldung; sie wurden nicht von CI auf dem privaten NAS erhoben.

Aktueller Fix-Stand und erneuter Test: [Findings aus Issue #1](FINDINGS_ISSUE_1.md).
Die folgenden CI-Nachweise und der spätere echte Unraid-Betreibertest sind getrennt.
Die authentifizierte evcc-SoC-Prüfung und ein echter EOS-Datenimport wurden
inzwischen vom Betreiber erfolgreich durchgeführt. Die automatische GENETIC-Planberechnung
ist noch nicht nachgewiesen.

| Kriterium | Nachweis / Stand |
| --- | --- |
| Unraid-XML Version 2 | Geparst und auf Pflichtfelder, sichere Defaults, optionale leere Pfade sowie Path/Variable-Typen getestet |
| Unraid 7.3.1 | `xmlToVar()`/`xmlToCommand()` und Add-Container-Auswahl im offiziellen Quellstand `982b3c207599446989e521f13d707cf3809a4318` geprüft; `PostArgs` steht nach dem Image, ExtraParams davor |
| Volumes | TOML/input ro, nur eigenes output rw; keine fremden Appdata-/Socket-/Geräte-Mounts |
| Command/Entrypoint | `python -m eos_pv_helper`, CMD `run`, GUI PostArgs `run --config /app/config.toml` im Image getestet |
| Sicherheitsoptionen | Non-root UID/GID 10001, read-only Root, keine Capabilities, no-new-privileges, Ressourcenlimits; isolierter Container-Test erfolgreich |
| Erststart | Fehlende Datei bzw. Verzeichnis statt TOML verständlich gemeldet; fehlender nativer Quellcache verweigert automatischen Abruf |
| Dry-run | 192 synthetische Viertelstunden erzeugt; `--write-eos` bleibt bei DRY_RUN=true gesperrt; Netzwerk im Test vollständig deaktiviert |
| Healthcheck | Nach erfolgreicher Normalisierung Exitcode 0; native EOS-Provider-Abhängigkeiten im Vollimage importierbar |
| Secret-Datei | Datei/Env gegenseitig ausgeschlossen; fehlende, leere, zu große und ungültige Tokens vor HTTP abgelehnt; keine Token-Logs |
| Release-/Preview-Tags | Commit-Tags, PR-Vorschau und spätere Versions-Tags separat getestet; unpassende Versionen/Fork-Refs abgelehnt |
| Tests | Ursprüngliche Findings: 168 Tests; Release-Vorbereitung mit Doctor, begrenztem Snapshot-Retry und Release-Gates: 215 Tests mit gepinntem EOS erfolgreich; Ruff und Actionlint erfolgreich |
| Lokales Vollimage | Ziel `eos-source` erfolgreich gebaut, `scripts/unraid_smoke.py` ohne Netzwerk bestanden |
| GHCR | Fix-Image tatsächlich veröffentlicht; [Push-Lauf 40845383381](https://github.com/vbeinlich/EOSPVPrognoseHelfer/actions/runs/40845383381) vollständig grün, anonymer Pull und Smoke-Test des Registry-Digests erfolgreich; [Digest-/Source-Nachweis](IMAGE_PUBLICATION.json) |
| Echte Unraid-GUI-Installation | **Vom Betreiber bestätigt:** vorhandenen Helfer über Docker → Edit → Apply auf geprüften GHCR-Digest aktualisiert; Docker-Inspect mit `sync --config /app/config.toml --refresh-source --write-eos`; separater evcc-Secret-Mount im GUI ergänzt. `<PostArgs>` war in Advanced View nicht sichtbar und musste im User-Template angepasst werden. |

## Zusätzlicher realer Unraid-Abnahmenachweis (Betreiber, 29.10.2026)

- Docker-Inspect bestätigte den Digest `sha256:7e957da3e2fdb67456a46e5538ad3c74b43fa21892d2998e93bca9de83d9daf7` und den späteren Sync-Startbefehl mit `--refresh-source --write-eos`.
- Dynamische PV-Prognose real validiert: 175 Viertelstunden = 43,75 h, davon 110 astronomisch geprüfte Nachtfüllungen; `pv.import_verified=true` im echten Einmalimport.
- Authentifizierter evcc-API-Key: Secret-Datei (UID 10001, 0600), read-only nach `/run/secrets/evcc_token` eingebunden; `[evcc].token_file` ergänzt. Vorheriger HTTP-401-Gerätezugriff behoben; `soc.freshness_verified=true`, `usable=true`, geprüfter ungecachter `e3dc-rscp`-Getter. Einzelne zeitversetzte SoC-Snapshot-Differenzen sperren einen Zyklus korrekt.
- Einmaliger EOS-Schreibtest: `forecast_valid mode=write intervals=175`, `sync_completed mode=write errors=`; 96 Preisintervalle mit `readback.verified_interval_count=96`, 0 fehlende/abweichende Intervalle. Danach regulärer Sync mit `DRY_RUN=false`, getrennten Schreibfreigaben und weiterhin ohne Fehler bestätigt.
- EOS-Sicherheitsprüfung: `ems.mode=PREDICTION`, Intervall 3600 s, `adapter.provider=null`, `ems.notify_url=null`; GENETIC/24h wurde separat konfiguriert. Letzter Triggerstatus `event.status=waiting-publication`, noch keine `solution-*.json` nachgewiesen. **Automatische GENETIC-Abnahme bleibt in Issue #1 offen.**
- UI-/Migrationsprobleme (fehlender `[evcc]`-Abschnitt, Secret-Onboarding, verborgenes PostArgs, Statusanzeige, stabiler `:latest`-Release) werden in Issue #5 behandelt. Diese Nacharbeiten gehören nicht mehr zur Basis-Unraid-Docker-Installierbarkeit.

## Wiederholen

Auf einem Docker-Entwicklungsrechner, nicht durch Änderung bestehender Container:

```sh
python -m pip install '.[test]'
ruff check src tests scripts
pytest -q
docker build --target eos-source -t eos-pv-helper:unraid-test .
python scripts/unraid_smoke.py --image eos-pv-helper:unraid-test
```

Der Smoke-Test verwendet ausschließlich neue temporäre synthetische Testdaten und
automatisch entfernte Container. Die veröffentlichte Pipeline führt denselben Test
gegen den tatsächlichen Registry-Digest durch und vergleicht dessen OCI-Source-Revision.
Das Produktions-Template mountet keinen Docker-Socket; der Test nutzt die Docker-CLI
des Entwicklungsrechners bzw. des GitHub-Runners.

## Historische ursprüngliche Abschluss-Checkliste (inzwischen teilweise erfüllt)

1. GHCR-Image mit erfolgreichem anonymem Pull und Source-Revision ist dokumentiert;
   Template und öffentliche Anleitung verwenden den geprüften Digest.
2. Vorlage auf Unraid unter User Templates auswählen; ausschließlich neuen Helfer im
   Dry-run anlegen, Pfade, PostArgs, Netzwerk, Logs und Health nach Anleitung prüfen.
3. Ergebnisse im Issue dokumentieren. Issue #4 bleibt bis zur echten Unraid-Abnahme offen.
4. Ein gemeinsamer Release und Merge von PR #3 erfolgt separat; Issue #1 benötigt weiterhin
   den echten ausdrücklich genehmigten EOS-Lauf mit der aufbereiteten Produktionsprognose.
