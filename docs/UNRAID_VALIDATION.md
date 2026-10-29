# Abnahmeprotokoll zu Issue #4

Stand: 29.10.2026. Diese Datei unterscheidet isolierte Tests von einem echten
Unraid-GUI-Test. Bestehende Container wurden nicht verändert.

Aktueller Fix-Stand und erneuter Test: [Findings aus Issue #1](FINDINGS_ISSUE_1.md).
Die zwischenzeitliche reale PV-Abnahme wurde vom Betreiber in Issue #1 beschrieben;
die folgenden ursprünglichen GUI-/Image-Nachweise sind davon getrennt. Nach den Fixes
steht insbesondere die authentifizierte evcc-SoC-Abnahme noch aus.

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
| Tests | 116 Tests mit gepinntem EOS erfolgreich; Ruff und Actionlint erfolgreich |
| Lokales Vollimage | Ziel `eos-source` erfolgreich gebaut, `scripts/unraid_smoke.py` ohne Netzwerk bestanden |
| GHCR | Image tatsächlich veröffentlicht; [Push-Lauf 40829029860](https://github.com/vbeinlich/EOSPVPrognoseHelfer/actions/runs/40829029860) vollständig grün, anonymer Pull und Smoke-Test des Registry-Digests erfolgreich; [Digest-/Source-Nachweis](IMAGE_PUBLICATION.json) |
| Echte Unraid-GUI-Installation | Noch offen; keine tatsächliche Template-Auswahl/Installation auf dem privaten Server behauptet |

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

## Vor Schließen des Issues

1. GHCR-Image mit erfolgreichem anonymem Pull und Source-Revision ist dokumentiert;
   Template und öffentliche Anleitung verwenden den geprüften Digest.
2. Vorlage auf Unraid unter User Templates auswählen; ausschließlich neuen Helfer im
   Dry-run anlegen, Pfade, PostArgs, Netzwerk, Logs und Health nach Anleitung prüfen.
3. Ergebnisse im Issue dokumentieren. Issue #4 bleibt bis zur echten Unraid-Abnahme offen.
4. Ein gemeinsamer Release und Merge von PR #3 erfolgt separat; Issue #1 benötigt weiterhin
   den echten ausdrücklich genehmigten EOS-Lauf mit der aufbereiteten Produktionsprognose.
