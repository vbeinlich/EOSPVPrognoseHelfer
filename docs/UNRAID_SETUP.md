# Installation über Unraid: Docker → Add Container

Diese Anleitung verwendet die normale Unraid-Docker-Oberfläche. Compose und ein dauerhaft
manuell gestarteter `docker run` sind nicht erforderlich. Zielsystem: Unraid 7.3.1 auf x86-64;
das Image wird als `linux/amd64` gebaut. Die Erstfassung dieser Anleitung war vor der realen Abnahme entstanden;
am 29.10.2026 hat der Betreiber Installation/Upgrade, Secret-Mounts und echte Datenimporte
auf Unraid bestätigt. Details unter [UNRAID_VALIDATION.md](UNRAID_VALIDATION.md).
Die automatisch erstellte GENETIC-Lösung wurde inzwischen vom Betreiber bestätigt
und unabhängig lesend geprüft: [GENETIC-Abnahme](GENETIC_ABNAHME.md).

Für den inzwischen vorhandenen Helfer gelten die [aktuellen Findings mit konkretem
erneutem Dry-run-Test](FINDINGS_ISSUE_1.md). Sie behandeln dynamischen PV-Horizont,
TTL-Aktualisierung, korrigierte Preis-Rücklesung und evcc als bevorzugte SoC-Quelle.
Eine zweite Helferinstanz ist dafür nicht erforderlich.

**Stand nach Merge von PR #3:** v0.1.0 ist noch nicht öffentlich veröffentlicht.
Neue private Kandidaten sind keine installierbaren GHCR-Releases. Für den
Release-Nachweis und spätere ausdrücklich freigegebene Updates gilt
[RELEASE_0_1_0_READINESS.md](RELEASE_0_1_0_READINESS.md). Diese Vorbereitung
ändert keine produktiven Container, Post Arguments, Secrets oder Freigaben.
Ein späteres Update darf erst nach Veröffentlichung des konkret geprüften
Digests erfolgen. Vorher den tatsächlichen bisherigen Digest, Mounts und
Startargumente privat sichern; bestehende Claims und Lösungen erhalten. Nicht
mit Add Container eine zweite Instanz auf denselben Output setzen. Rollback
bedeutet bewusste Rückkehr zum zuvor gesicherten Digest, keinen Claim-Reset und
kein Verschieben eines unveränderlichen Versionstags. [Ablauf und Fehlerfälle](RELEASE_0_1_0_READINESS.md#8-rollback-und-fehlerfälle).

**Vorab:** Bestehende EOS-, evcc- und HA-Container bleiben unverändert. Existiert bereits ein
Helfercontainer, nicht einfach eine zweite Instanz starten oder einen gleichen Namen in
„Add Container“ verwenden: das könnte eine bestehende Installation ersetzen. Eine Migration
ist separat zu planen. Diese Anleitung legt ausschließlich einen neuen Helfer an.

## 1. Image und Version wählen

Registry-Name (Groß-/Kleinschreibung beachten):
`ghcr.io/vbeinlich/eospvprognosehelfer`.

Die Pipeline baut ausdrücklich das Dockerfile-Ziel `eos-source` einschließlich des nativen
EOS-Forecast.Solar-Providers. `ENTRYPOINT` ist `python -m eos_pv_helper`, `CMD` ist `run`.
Die Codeversion in `pyproject.toml` ist **kein Nachweis eines veröffentlichten Image-Tags**.

**Tatsächlich veröffentlicht und anonym geprüft am 29.10.2026:**

```text
ghcr.io/vbeinlich/eospvprognosehelfer@sha256:7e957da3e2fdb67456a46e5538ad3c74b43fa21892d2998e93bca9de83d9daf7
```

Dieser Vorschau-Build stammt aus Commit
[`b648a61699854d325eceb5f823f6de999a989525`](https://github.com/vbeinlich/EOSPVPrognoseHelfer/commit/b648a61699854d325eceb5f823f6de999a989525)
einschließlich der Findings-Korrekturen aus Issue #1.
[Erfolgreicher Build/Pull/Test](https://github.com/vbeinlich/EOSPVPrognoseHelfer/actions/runs/40845383381),
[maschinenlesbarer Nachweis](IMAGE_PUBLICATION.json). Das XML ist auf genau diesen Digest
gepinnt. Es wurde noch kein gemeinsamer stabiler Release erstellt. Der obige Textblock
ist ein Repository-Feldwert für die GUI, kein Shell-Befehl.

- Seit dem Audit vom 30.10.2026 bauen und testen die
  [Actions-Läufe](https://github.com/vbeinlich/EOSPVPrognoseHelfer/actions) nur lokal.
  Main-/Branch-Pushes und Versionstags veröffentlichen keine Images.
- `pr-3` wird nicht automatisch aktualisiert. Vorhandene Vorschau-Digests sind
  historische Installationsbelege, keine Freigabe des neuesten Quellstands.
- Stabile Images benötigen eine gesonderte Digest-/Inventar-/Quellmaterial-Freigabe
  und manuelle Promotion. Ein Git-Tag erzeugt kein `latest`.
  [Verbindliche Release-Gates](RELEASE_CHECKLIST.md).
- Das neue CI-Artefakt `candidate-license-inventory-<SHA>` enthält nur das Inventar.
  Ältere `image-publication-<SHA>`-Artefakte dokumentieren damalige Veröffentlichungen.

Für eine unveränderliche Installation den vollständigen `pinned_image`-Wert als
**Repository** in Unraid einsetzen. Tags können grundsätzlich verschoben werden;
ein `@sha256:...`-Digest bezeichnet exakt das geprüfte Image. Der bewegliche `pr-3`-Tag
ist eine Vorschau und kein stabiles Release-Versprechen.

Vor einem künftig freigegebenen Release muss genau dessen Digest **ohne Docker-
Anmeldedaten** abrufbar sein und den netzlosen Smoke-Test bestehen. Package-Sichtbarkeit,
geschütztes Release-Environment und ausschließliche Registry-Schreibrechte sind
separat zu prüfen; ihre Konfiguration wird hier nicht als erfolgt behauptet.
Falls der Job beim anonymen Pull scheitert, muss der Eigentümer in den
[Package settings](https://github.com/users/vbeinlich/packages/container/package/eospvprognosehelfer/settings)
die Sichtbarkeit auf **Public** setzen und den fehlgeschlagenen Job erneut ausführen.
Ein Repository allein macht das Containerpaket nicht öffentlich. Unraid benötigt für
das fertig öffentlich geprüfte Image keine GitHub-Anmeldung und keinen Registry-Token.

## 2. Eigenes Appdata-Verzeichnis und private TOML vorbereiten

Im Unraid-Terminal zunächst nur Verzeichnisse des **neuen** Helfers anlegen. Bei einer
bereits vorhandenen `config.toml` stoppen und deren Herkunft prüfen; nicht überschreiben.

```sh
test ! -e /mnt/user/appdata/eos-pv-helper/config.toml || { echo 'config.toml existiert bereits – zuerst prüfen'; exit 1; }
mkdir -p /mnt/user/appdata/eos-pv-helper/input /mnt/user/appdata/eos-pv-helper/output
curl --fail --location --output /mnt/user/appdata/eos-pv-helper/config.toml \
  https://raw.githubusercontent.com/vbeinlich/EOSPVPrognoseHelfer/feat/issue-1-pv-normalization/config.example.toml
chown 10001:10001 /mnt/user/appdata/eos-pv-helper /mnt/user/appdata/eos-pv-helper/config.toml \
  /mnt/user/appdata/eos-pv-helper/input /mnt/user/appdata/eos-pv-helper/output
chmod 750 /mnt/user/appdata/eos-pv-helper /mnt/user/appdata/eos-pv-helper/input /mnt/user/appdata/eos-pv-helper/output
chmod 600 /mnt/user/appdata/eos-pv-helper/config.toml
```

Die Beispieldatei und das XML stammen vor dem Merge aus dem PR-Branch. Für eine fixierte
Installation in diesen Download-URLs den Branch durch den zur Image-Revision gehörenden
Commit ersetzen; nach dem gemeinsamen Release dessen verifizierten Tag verwenden.

Die Datei mit einem Texteditor bearbeiten, zum Beispiel `nano` im Unraid-Terminal oder
einem lokalen Editor über einen bereits vorhandenen sicheren Dateizugriff. TOML ist
**Dateiinhalt**, kein Shell-Befehl. In `[eos]` die tatsächliche lokale EOS-URL eintragen,
beispielsweise nach dem Schema `http://UNRAID-HOST:8503`; den Platzhalter durch die eigene
erreichbare Adresse ersetzen. Diese Datei bleibt privat und wird niemals hochgeladen.

Diese Standards unverändert lassen:

```toml
[source]
refresh_enabled = false
# Die weiteren source-Felder aus config.example.toml beibehalten.

[eos]
url = "http://UNRAID-HOST:8503" # Platzhalter im privaten Editor ersetzen.
write_enabled = false

[soc]
enabled = false
write_enabled = false

[prices]
enabled = false
write_enabled = false
retail_prices_confirmed = false

[trigger]
enabled = false
run_enabled = false
```

Dies ist ein **Auszug**. Bestehende Tabellen in der Beispieldatei bearbeiten, nicht dieselbe
TOML-Tabelle zweimal anlegen. Geometrie, Koordinaten und kWp kommen bei `eos-forecastsolar`
aus der bestehenden EOS-Konfiguration; keine Werte erfinden. Eine Änderung der privaten
TOML erfordert beim laufenden Dienst einen Neustart **nur des neuen Helfers**, weil dieser
sie beim Prozessstart liest. Bestehende EOS-/evcc-/HA-Container werden dafür nicht verändert.

**Die Datei muss vor „Apply“ existieren.** Andernfalls kann Docker/Unraid an ihrer Stelle
ein Verzeichnis erzeugen. Der Container benötigt keine Schreibrechte an dieser Datei.
Es gibt keine `PUID`-/`PGID`-Umsetzung: die UID/GID ist fest 10001.

## 3. XML in Unraid verfügbar machen

Die [versionierte Vorlage](../templates/eos-pv-helper.xml) als
`/boot/config/plugins/dockerMan/templates-user/my-eos-pv-helper.xml` speichern.
Das ist die normale Unraid-User-Template-Ablage auf dem Flash-Laufwerk. Im Terminal:

```sh
mkdir -p /boot/config/plugins/dockerMan/templates-user
test ! -e /boot/config/plugins/dockerMan/templates-user/my-eos-pv-helper.xml || { echo 'Vorlage existiert bereits – nicht überschreiben'; exit 1; }
curl --fail --location --output /boot/config/plugins/dockerMan/templates-user/my-eos-pv-helper.xml \
  https://raw.githubusercontent.com/vbeinlich/EOSPVPrognoseHelfer/feat/issue-1-pv-normalization/templates/eos-pv-helper.xml
```

Nur Vorlagen aus vertrauenswürdiger Quelle verwenden; XML kann zusätzliche Docker-Argumente
enthalten. Die Projektvorlage enthält keine Zugangsdaten und kein fremdes Logo. Unraid
verwendet das Standardicon. Eine Aufnahme in Community Applications wird nicht behauptet.

## 4. Docker → Add Container ausfüllen

„Docker“ öffnen, **Add Container**, im Dropdown unter User Templates **eos-pv-helper**
wählen. Gegebenenfalls die Seite neu laden. **Advanced View** aktivieren und prüfen:

| Unraid-Feld | Einstellung |
| --- | --- |
| Name | `eos-pv-helper`, nur wenn dieser Name noch nicht existiert |
| Repository | geprüfter GHCR-Digest aus Schritt 1; Vorschau-Tag nur bewusst verwenden |
| Network Type | `bridge` |
| Privileged | aus |
| Console shell | `sh` |
| Post Arguments / Command nach dem Image | `run --config /app/config.toml` |
| DRY_RUN | `true` |
| HA_TOKEN | leer |
| optionale HA Secret-Datei | leer |
| EVCC_TOKEN / optionale evcc Secret-Datei | zunächst leer; später nur vorhandenen privaten Key verwenden |
| WebUI / Ports | keine |

**Post Arguments** überschreibt das Image-CMD und wird an den vorhandenen Entrypoint
angehängt. Hier **nicht** nochmals `python -m eos_pv_helper` eintragen. **Extra Parameters**
enthält Docker-Optionen vor dem Imagenamen, nicht den Anwendungsbefehl. Die Vorlage setzt
Root-Dateisystem read-only, alle Capabilities entfernt, `no-new-privileges`, 16 MiB `/tmp`,
512 MiB RAM, 0,25 CPU, 128 Prozesse und UID/GID 10001. Kein erzwungener Restart-Loop:
ein `--once`-Lauf darf nicht unbeabsichtigt neu starten. Autostart zunächst aus lassen.

Die Pfade prüfen:

| Host unter `/mnt/user/appdata/eos-pv-helper/` | Container | Modus |
| --- | --- | --- |
| `config.toml` (Datei) | `/app/config.toml` | read-only |
| `input` | `/input` | read-only |
| `output` | `/output` | read-write |

Keine EOS-, evcc- oder HA-Appdata-Verzeichnisse, keinen Docker-Socket und keine Geräte
hinzufügen. **Apply** installiert jetzt nur den neuen Helfer. `output` über Updates und
Neustarts erhalten: darin liegt auch die Sperre gegen doppelte EOS-Simulationsläufe.

## 5. Netzwerk und Erststart prüfen

Der Helfer bietet keinen Webserver; Portfreigaben sind unnötig. Er benötigt ausgehend
Zugriff auf die privat konfigurierten lokalen Dienste: EOS Port 8503, bei späterer
Aktivierung HA Port 8123 und evcc Port 7070. In Bridge-Netzwerken ist `localhost` der
Helfer selbst. Container-Namen sind nur mit passender gemeinsamer Docker-DNS-Auflösung
nutzbar; erreichbar veröffentlichte Host-/LAN-Adressen sind häufig einfacher.

Bei macvlan-/ipvlan- oder Host-Zugriffsproblemen zunächst die bestehende Erreichbarkeit
prüfen. Diese Anleitung ändert keine globalen Docker-Netzwerke und erzwingt kein Host-
oder privilegiertes Netzwerk. Nicht zur Fehlerbehebung alle vorhandenen Container umbauen.

Im Docker-Menü des Helfers **Logs** öffnen. Ohne passenden aktuellen Rohcache ist
`No matching fresh source cache; explicit source-refresh approval needed` erwartbar.
Der Prozess bleibt im Cache-only-Betrieb und versucht im nächsten Intervall erneut.
`unhealthy` bedeutet in diesem Fall fehlende Prognosedaten, **keinen Image-/Builddefekt**.
Es erfolgt kein automatischer Forecast.Solar-Abruf und kein EOS-Schreiben.

In **Console** des neuen Helfers sind ausschließlich lesende Checks möglich:

```sh
id
python -m eos_pv_helper health
cat /output/health.json
cat /output/report.json
```

`report.json` fehlt, solange noch keine gültige Prognose erzeugt wurde. Nach erfolgreicher
Prüfung stehen `forecast.json`, `report.json`, `source.json` und `health.json` in `output`.
`health` liefert Exitcode 0 bei aktuellem gesunden Zustand, sonst 1. Logs enthalten
gezielt keine Tokens oder vollständigen Quellantworten.

## 6. Schrittweise Freigaben

**Die folgenden Schritte benötigen jeweils die genannte ausdrückliche Betreiberfreigabe.**
Eine Image-Installation ist keine Freigabe zum Abruf, EOS-Import oder Optimieren.

1. **Einmaliger Forecast.Solar-Abruf:** nach Freigabe in der privaten TOML nur
   `source.refresh_enabled=true` setzen. Nur den neuen Helfer stoppen/starten, damit auch
   ein vom Editor ersetzter Datei-Inode neu eingebunden wird. Post Arguments unverändert
   **ohne** `--refresh-source` lassen; dadurch bleibt der Hintergrundprozess Cache-only.
   In der Console des neuen Helfers einmal:

   ```sh
   DRY_RUN=true python -m eos_pv_helper run --config /app/config.toml --once --refresh-source
   ```

   Danach `source.refresh_enabled=false` zurücksetzen und nur den Helfer neu starten.
   Der einmalige Prozess verwendet
   den nativen EOS-Provider und einen gemeinsamen Dateilock. Ein Abruf kann pro PV-Fläche
   einen Request benötigen. Ein vorhandener gültiger Cache verhindert einen erneuten Abruf.
   26 Stundenwerte belegen keinen 48-h-Horizont; fehlende Tageswerte führen zum Fehler.

2. **EOS-PV-Import:** separat genehmigen. In TOML `eos.write_enabled=true` setzen, nur den
   Helfer neu starten und in der Console einmal mit bewusstem `DRY_RUN=false` und
   `--write-eos` starten. Das unveränderte
   GUI-Feld `DRY_RUN=true` schützt weiterhin den normalen Hintergrundprozess:

   ```sh
   DRY_RUN=false python -m eos_pv_helper run --config /app/config.toml --once --write-eos
   ```

   Roh-Rücklesung und Bericht prüfen, anschließend `eos.write_enabled=false` zurücksetzen,
   falls nur ein einzelner Import freigegeben war. Keine fremden Provider umkonfigurieren.

3. **SoC und Preise zunächst nur lesend:** die private gemeinsame `[evcc].url` eintragen,
   Preise mit `enabled=true`, alle Schreibfreigaben weiter `false`. Für evcc-SoC zusätzlich
   die genaue eigene Gerätekennung und den geprüften RSCP-Frischenachweis samt vorhandenem
   API-Key konfigurieren; ohne erfolgreichen Nachweis bleibt SoC gesperrt. HA ist optionaler
   Vergleich unter `[soc.ha]`. Im GUI ausschließlich
   beim Helfer **Post Arguments** auf `sync --config /app/config.toml` setzen und Apply.
   Dies erstellt nur diesen Helfer neu. SoC wird nach Quellzeitstempel/Alter geprüft;
   `soc.json`, `prices.json`, `prices-source.json` und `sync-report.json` kontrollieren.

4. **SoC-/Preisimport einzeln:** benötigt eigene Freigaben, passende individuelle
   `write_enabled=true`, `eos.write_enabled=true`, GUI `DRY_RUN=false` und zusätzlich
   `--write-eos` in Post Arguments. Ein aktiver `sync`-Schreibmodus umfasst auch PV-Import;
   nur nach entsprechender PV-Freigabe einschalten. evcc-Endpreise zunächst gegen LUOX
   vergleichen. EOS muss bereits separat freigegeben `ElecPriceImport` verwenden;
   `ElecPriceEnergyCharts` wird weiterhin abgelehnt. Der Helfer stellt den Provider nie um.
   Ein EOS-Schreibmodus bedeutet keine dauerhafte externe Forecast-Abruffreigabe.

5. **GENETIC-Simulation:** erst nach eigenständiger Freigabe
   `trigger.enabled=true` und `trigger.run_enabled=true`. Neue vollständige Day-Ahead-
   Preise lösen höchstens einen Versand je Preisversion und gemeinsamer Statusablage aus.
   Alle Eingaben, Rohimporte, Frische und Horizont müssen gültig sein. EOS bleibt
   `PREDICTION`/3.600 s. Aktive Adapter oder Abschluss-Webhooks sperren den Aufruf.
   Details und Timeout-Behandlung: [synchronisation.md](synchronisation.md).

Ein dauerhaft erneuernder Quellenbetrieb ist eine zusätzliche ausdrückliche Freigabe:
TOML `source.refresh_enabled=true` plus `--refresh-source` in Post Arguments erlaubt dann
TTL-gesteuerte Wiederabrufe. Für den hier beschriebenen Ersttest bleibt das deaktiviert.

## 7. Optionaler HA-Token

Bevorzugt eine neue private Datei unter dem eigenen Helferverzeichnis anlegen, etwa
`/mnt/user/appdata/eos-pv-helper/secrets/ha_token`, mit dem Token als einzigem Inhalt.
Per Editor eingeben, nicht in Shell-Befehle oder die Shell-History kopieren. Verzeichnis
UID/GID 10001 und Modus 750, Datei UID/GID 10001 und Modus 600 geben; nur diese neu angelegten
Pfade ändern. Im Advanced-Formular **HA Secret-Datei** den vollständigen Host-Dateipfad
eintragen. Er wird read-only nach `/run/secrets/ha_token` eingebunden. Für den optionalen
Vergleich im bestehenden `[soc.ha]`-Block (bei ausdrücklich gewählter Legacy-HA-Quelle
stattdessen im `[soc]`-Block):

```toml
# bearer_token_env entfernen, nicht beide Quellen gleichzeitig konfigurieren:
bearer_token_file = "/run/secrets/ha_token"
```

Alternative: das maskierte Feld **HA_TOKEN** und `bearer_token_env="HA_TOKEN"` verwenden.
**Maskierung ist kein Secret-Speicher:** Umgebungswerte können in `docker inspect`, dem
gespeicherten Unraid-XML, Supportexporten und Flash-Backups stehen. Auch eine Secret-Datei
ist vor ungeschützten Appdata-Backups zu schützen. Keine privaten XML-/TOML-/Token-Dateien
in Issues, Git oder Screenshots veröffentlichen. Ein leerer optionaler Tokenpfad erzeugt
keine Mounts; eine verwendete Token-Datei muss vor Apply existieren.

Für den bevorzugten evcc-SoC die optionale **evcc Secret-Datei** verwenden: eine bereits
vorhandene private API-Key-Datei read-only nach `/run/secrets/evcc_token` einbinden und
in `[evcc]` `token_file="/run/secrets/evcc_token"` setzen. Alternative ist das maskierte
Feld `EVCC_TOKEN` mit `token_env="EVCC_TOKEN"`; dieselben Inspect-/XML-/Backup-Risiken gelten.
Der Helfer erstellt oder rotiert keine API-Keys. Auf der aktuell ohne Key geprüften Anlage
liefern die geschützten Geräte-GETs HTTP 401; das ist eine echte SoC-Sperre. Ein neuer Key
oder Änderungen an evcc sind nicht Bestandteil dieser Implementierung.

## 8. Aktualisieren, zurückrollen und Version festhalten

1. Aktuellen Repository-Digest und die eigene TOML/Statusablage privat sichern. Bei
   bestehender `sync-state.json` einen Backupstand nicht blind zurückspielen: dadurch
   könnten bereits versandte Preisversionen vergessen werden.
2. In den Veröffentlichungsläufen einen **tatsächlich vorhandenen**, erfolgreichen Build
   wählen. Release-Tag oder besser geprüften Digest verwenden; `latest` nicht für eine
   unbemerkte Produktionsumstellung einsetzen.
3. Nur beim Helfer **Edit → Repository** auf den neuen Pin ändern, übrige Freigaben und
   Mounts prüfen, Apply. Unraid lädt das Image und ersetzt ausschließlich diesen Helfer.
4. Logs, Health und aktuelle Ausgabedaten kontrollieren. Bei Fehlern beim gleichen Helfer
   den vorher notierten Digest wieder einsetzen. Die Ausgabe- und Idempotenzdateien
   erhalten; ein Rollback setzt keine Preisversionen zurück und ändert keine EOS-Daten.

Für eine Rückkehr zum sicheren Zustand GUI `DRY_RUN=true`, Post Arguments `run --config
/app/config.toml` und alle privaten TOML-Schreib-/Abruf-/Triggerfreigaben deaktivieren.

## Troubleshooting

| Meldung/Symptom | Prüfen |
| --- | --- |
| Vorlage nicht auswählbar | exakt `templates-user/my-eos-pv-helper.xml`, gültiges XML, Add-Container-Seite neu laden; keine Community-Applications-Aufnahme vorausgesetzt |
| GHCR `denied` / `unauthorized` | richtiger kleingeschriebener Name, tatsächlich veröffentlichtes Tag/Digest, Package-Sichtbarkeit Public und erfolgreicher anonymer Pull im Push-Lauf |
| `Private config.toml missing or a directory` | echte Datei vor Apply erstellen; versehentliches neues Helferverzeichnis an dieser Stelle nur nach Inhaltsprüfung korrigieren |
| `startup_failed TOMLDecodeError` | TOML im Editor reparieren, Tabellen nicht doppelt einfügen; keinen Dateiinhalt als Shell ausführen |
| `PermissionError` / read-only | nur eigenes `output` für UID/GID 10001 schreibbar; config und Secret-Datei für diese UID lesbar, nicht pauschal alle Appdata-Rechte ändern |
| Cache-only-Fehler / unhealthy beim Erststart | erwartbar ohne frischen passenden Cache; erst separate Abruffreigabe, keine automatische Nullfüllung von Tageslücken |
| `Local HTTP host could not be resolved` | private URL/Hostadresse, gemeinsames DNS, kein fremdes Container-`localhost` |
| `HTTP request failed` | lokale IP/Ports aus dem Helfer-Netz erreichbar? Unraid-/LAN-Routing prüfen, keine bestehenden Container ungefragt ändern |
| HA 401 / Token fehlt | Secret-Datei oder genau eine Env-Quelle, HA-Leserechte, Datei-Mount und UID; Tokens niemals ins Log kopieren |
| SoC stale/unknown/unavailable | echter HA-Quellzeitstempel, max. 300 s, keine Ersetzung durch die Helferzeit |
| Preisprovider-Sperre | erwartbar bei `ElecPriceEnergyCharts`; Umstellung auf `ElecPriceImport` verlangt separate Freigabe |
| Tages-/Horizontlücke | keine erfundene 48-h-Abdeckung; Rohquelle und tatsächliche Kadenz prüfen |
| `uncertain` im Ereignisstatus | kein automatischer zweiter POST; tatsächlichen EOS-Lauf prüfen, Statusdatei nicht löschen |

## Abnahme und Quellen

[Issue #4](https://github.com/vbeinlich/EOSPVPrognoseHelfer/issues/4) bleibt offen bis zum
echten Test über Unraid **Add Container**, sichtbaren Mounts/Command, Logs und Health.
Ein grüner CI-Lauf bestätigt Imagebau, anonyme Pullbarkeit und isolierten Containerbetrieb;
er bestätigt keine bereits erfolgte Installation auf dem privaten Unraid-Server.

- [Unraid: Container verwalten](https://docs.unraid.net/unraid-os/using-unraid-to/run-docker-containers/managing-and-customizing-containers/)
- [Unraid 7.3.1: XML/Command-Verarbeitung](https://github.com/unraid/webgui/blob/982b3c207599446989e521f13d707cf3809a4318/emhttp/plugins/dynamix.docker.manager/include/Helpers.php)
- [Unraid 7.3.1: Add-Container-Vorlagenauswahl](https://github.com/unraid/webgui/blob/982b3c207599446989e521f13d707cf3809a4318/emhttp/plugins/dynamix.docker.manager/include/CreateDocker.php)
- [GitHub: Container Registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
- [GitHub: Package-Sichtbarkeit](https://docs.github.com/en/packages/learn-github-packages/configuring-a-packages-access-control-and-visibility)

## Abschluss der laufenden Abnahme

PV-, evcc-SoC- und Preisimport sowie der automatische GENETIC-Plan wurden real
bestätigt. Der [rein lesende Doctor und Release-Ablauf](RELEASE_CHECKLIST.md)
prüft die vorhandenen Artefakte ohne erneuten Lauf. Kein Deployment oder Update
durch Codex ohne ausdrückliche Freigabe. Wizard/Skill werden gemäß PR-Auftrag erst
nach erfolgreichem Abschluss #1, Merge #3 und stabilem Release implementiert.
