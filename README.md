# EOS PV-Prognose-Helfer

Neu im Review: [optionale automatische GENETIC-Beweisarchivierung](docs/GENETIC_EVIDENCE.md).
Standardmäßig deaktiviert; keine zusätzlichen Optimierungen, kein Backfill.

Validiert vorhandene Forecast.Solar-Prognosen für Akkudoktor EOS und stellt eine zentrale
UTC-Viertelstundenreihe bereit. Keine Gerätebefehle, keine neue Wetter-API und kein eigener
Forecast.Solar-Client: verwendet wird der originale EOS-Provider `PVForecastForecastSolar`.

**Standard: Dry-run und Cache-only.** Ein externer Abruf braucht zwei ausdrückliche
Opt-ins. EOS-Schreibzugriffe benötigen `DRY_RUN=false`, Konfigurationsfreigaben und
`--write-eos`. Die reale Unraid-Abnahme von PV-, SoC- und Preisimport ist bestätigt;
auch der erste automatische GENETIC-Plan wurde am 29.10.2026 bestätigt und dessen
vorhandene Lösung unabhängig lesend validiert. [Abnahmebeleg](docs/GENETIC_ABNAHME.md).

Der rein lesende `doctor` prüft vorhandene Abnahme-Artefakte ohne HTTP oder
Schreibzugriffe. [GENETIC-Abnahme, Merge und MIT-Release](docs/RELEASE_CHECKLIST.md)
beschreiben die konkreten Schritte und verbleibenden Gates.
PR #3 ist nach `main` gemergt (`55e1bd8`); **v0.1.0 ist noch nicht veröffentlicht**.
Der [Release-Readiness-Bericht](docs/RELEASE_0_1_0_READINESS.md) trennt technische
Validierung, private Nachweise, formale Freigaben und tatsächliche Veröffentlichung.
Eigener Code: [MIT](LICENSE); [Fremdlizenzen und Image-Inventar](THIRD_PARTY_NOTICES.md)
gelten unabhängig davon. Nächste Reihenfolge: gesondert freigegebener stabiler Release →
[Setup-Wizard und Skill #5](docs/ISSUE_5_PLAN.md) →
[Savings Dashboard #6](docs/ROADMAP.md). Der produktive Helfer bleibt unverändert.

Die [aktuellen Findings und der erneute Unraid-Test](docs/FINDINGS_ISSUE_1.md) dokumentieren
den dynamischen 24..48-h-Horizont, periodische native Aktualisierung, historische
Preisschnitte und den eng geprüften evcc-SoC-Frischenachweis. Geschützte evcc-GETs benötigen
einen vorhandenen privaten API-Key; ohne erfolgreichen Nachweis bleibt SoC gesperrt.

## Recherche zuerst

Die [Recherche und Entscheidung](docs/research.md) erklärt, warum `PVForecastImport`
allein keine Nachtlücken ergänzt. Der aktuelle GENETIC-Optimierer verlangt vollständige
Rohdaten, auch nachts. Allgemeine EOS-Interpolation unterscheidet Tages-/Nachtlücken nicht.
Ein nativer direkter Import bleibt vorzuziehen, wenn die Quelle bereits vollständig ist.

## Datenvertrag

- Dynamisch werden mindestens 24 h und darüber alle lückenlos validierten Viertelstunden
  bis zum konfigurierten Maximum (Standard 48 h, zusätzlich durch EOS begrenzt) exportiert.
  Eine Lücke vor 24 h sperrt; eine spätere Tageslücke begrenzt den Horizont. 48 verstrichene
  Stunden ergeben 192 UTC-Intervalle, auch über DST-Wechsel.
- Nur **vollständig nächtliche** fehlende Intervalle werden mit 0 W ergänzt. Astral
  berechnet Sonnenaufgang/-untergang lokal; keine festen Nachtuhrzeiten.
- Vorhandene Werte auf dem Zielraster einschließlich Tages-0-W bleiben unverändert.
  Null, NaN, negative Werte, Duplikate und unklare Zeitstempel sind Fehler.
- Forecast.Solar liefert Leistungs-Stützstellen. Bei ausdrücklich stündlicher Quelle
  werden zusätzliche Viertelstunden linear zwischen benachbarten Stützstellen berechnet.
  Die Originalwerte bleiben im Rohcache erhalten; vorhandene Rasterpunkte bleiben exakt.
  **Abstände über die deklarierte Quellkadenz werden tagsüber nicht interpoliert.**
- Rein viertelstündliche Datei-/HTTP-Quellen sind strikt: jeder fehlende Tagespunkt begrenzt
  den nutzbaren Präfix bzw. sperrt vor dem Minimum. Kein ffill und keine Nullfüllung tagsüber.
- Eine Prognose mit 26 Stundenwerten belegt keine 48 Stunden. Ein fehlender Tageshorizont
  wird nicht erfunden; der tatsächlich zusammenhängende Horizont wird ausgewiesen.
- `source.json` ist der zentrale native Rohcache, `forecast.json` die EOS-kompatible Reihe,
  `report.json` der Qualitätsnachweis. Später kann EMHASS diese Dateien mitbenutzen und
  muss Forecast.Solar nicht erneut abrufen.

## Wiederverwendung des EOS-Providers

Der Helfer liest per GET die bestehende EOS-Konfiguration. Koordinaten, Zeitzone,
PV-Flächen, Neigung, Azimut, kWp und ggf. API-Key werden daraus übernommen, nicht erfunden.
`native_forecast()` ruft ausschließlich die originale `_request_forecast()`-Methode eines
gepinnten EOS-Commits in einem **lokalen Helferprozess** auf. Die EOS-Instanz auf dem Server
wird nicht umkonfiguriert. Andere Provider und EMS-Läufe werden nicht gestartet.

Der persistente Rohcache ist an die EOS-Parameter gebunden, standardmäßig eine Stunde gültig
und mit einem Dateilock gegen parallele Abrufe geschützt. Solange er gültig ist, wird
auch mit Abruffreigabe kein weiterer Abruf ausgelöst. Mehrere PV-Flächen erfordern gemäß
EOS je einen Request pro Fläche; nicht einen zusätzlichen Client pro Verbraucher.

Die vorhandene EOS-Installation muss `PVForecastImport` verwenden. Ist dort Forecast.Solar
selbst aktiv, verweigert der Helfer die zweite Abrufstrecke. Die konkrete native Auflösung
ist vor Produktivbetrieb gegen `source.interval_seconds` zu prüfen.

**Größentradeoff:** Das Ziel `eos-source` enthält die EOS-Abhängigkeiten, um keinen zweiten
Client zu pflegen. Das Ziel `normalizer` ist schlank (Python, Astral, tzdata) und kann
bereits exportierte Datei-/lokale HTTP-Prognosen verarbeiten. Es kann selbst nicht abrufen.

## Unraid: Docker → Add Container

Die [öffentliche Schritt-für-Schritt-Anleitung](docs/UNRAID_SETUP.md) beschreibt die
Installation mit dem [Unraid-XML-Template](templates/eos-pv-helper.xml), GHCR-Image,
privater TOML, Dateirechten und Bridge-Netzwerk. **Kein Compose-Plugin erforderlich.**
Aktualisieren, Rollback, Image-Digest-Pinning, Secret-Dateien und getrennte Freigaben
sind dort vollständig beschrieben. Die reale Unraid-GUI-Abnahme aus
[Issue #4](https://github.com/vbeinlich/EOSPVPrognoseHelfer/issues/4) ist bestätigt.

Registry: `ghcr.io/vbeinlich/eospvprognosehelfer`. Seit dem Release-Audit vom
30.10.2026 veröffentlichen Branch-/Main-Pushes und Versionstags **keine Images**;
`pr-3` wird nicht automatisch aktualisiert. CI baut und testet nur lokal.
Eine spätere manuelle Promotion benötigt konkrete Digest-/Inventar-/Quellmaterial-
Freigabe, vollständigen Doctor-Beleg und ausdrückliche Betreiberfreigabe.
[Verbindlicher Ablauf](docs/RELEASE_CHECKLIST.md). Die Projektversion ist
kein Nachweis eines bereits veröffentlichten Tags.
Der [geprüfte Veröffentlichungsnachweis](docs/IMAGE_PUBLICATION.json) enthält den
tatsächlich anonym abrufbaren Digest, auf den das Unraid-Template gepinnt ist.

## Alternative für Entwickler: lokaler Build und Compose

Voraussetzung: Docker; für Compose zusätzlich Compose-Manager oder Docker Compose.
Nur ein neues Helferverzeichnis anlegen, keine bestehenden Container/Dateirechte ändern:

```sh
mkdir -p /mnt/user/appdata/eos-pv-helper
cd /mnt/user/appdata/eos-pv-helper
git clone --branch feat/issue-1-pv-normalization https://github.com/vbeinlich/EOSPVPrognoseHelfer.git app
cd app
cp config.example.toml config.toml
mkdir -p input output
chown 10001:10001 config.toml output
chmod 600 config.toml
```

Bis zum Merge den PR-Branch, danach `main` verwenden. In der privaten `config.toml` nur
die bestehende lokale EOS-URL eintragen. Beide Freigaben zunächst `false` lassen.
Standort und Dachparameter werden live gelesen. Keine privaten Konfigurationen einchecken.

```sh
docker compose config
docker compose build
docker compose run --rm eos-pv-helper run --once
```

Ohne gültigen zentralen Rohcache ist zunächst ein klarer Cache-only-Fehler zu erwarten.
Das ist kein Anlass, unbemerkt einen weiteren externen Abruf zu starten. Bereits vorhandene
native Cache-/Exportdaten müssen zuerst geprüft werden. EOS-eigene Pickle-Cachedateien
werden aus Sicherheits- und Kompatibilitätsgründen nicht ungeprüft deserialisiert.

**Erst nach Freigabe eines Abrufs der bestehenden Quelle:** `source.refresh_enabled=true`
setzen und `run --once --refresh-source` verwenden. Das erzeugt nur die zentrale Prognose,
noch keinen EOS-Import. Bei einem Zugriff alle fünf Minuten verhindert die Cachefrist
weitere Abrufe innerhalb derselben Stunde. Für dauerhaften freigegebenen Quellenbetrieb
den Helfer mit `run --refresh-source` starten.

**Erst nach separater EOS-Schreibfreigabe:** zusätzlich `DRY_RUN=false`,
`eos.write_enabled=true` und `--write-eos` verwenden. Im PV-Kommando `run` ist die
einzige produktive Schreiboperation
`PUT /v1/prediction/import/PVForecastImport`, anschließend GET zur Rückleseprüfung.
Kein `force_enable`, kein Provider-Update, keine Konfigurationsänderung oder Optimierung.

## Optionale SoC-, Preis- und Ereignis-Erweiterung

Das Kommando `sync` liest aktivierte HA-/evcc-Quellen alle 60 Sekunden; die PV-Prüfung
behält `poll_seconds` bei. Alle Erweiterungen sind in `config.example.toml` deaktiviert.
Die [Installations- und Ablaufbeschreibung](docs/synchronisation.md) erklärt die
getrennten Freigaben, Eingabeprüfungen und Betriebsgrenzen.

- HA `sensor.evcc_battery_soc`: Prozent → Faktor, Quellzeitstempel erhalten,
  maximal 300 Sekunden alt; bestätigtes EOS-API `/v1/measurement/value` mit Roh-Rücklesung.
- Bevorzugt evcc: ein gemeinsamer `/api/state`-Snapshot für Preise und genau das konfigurierte
  Batteriegerät. Übernahme nur nach geprüftem ungecachtem E3/DC-RSCP-Statusabruf in evcc
  0.318.1; HTTP-/Wertänderungen allein reichen nicht. Kein automatischer HA-Fallback.
- evcc `forecast.grid`: vollständiger EUR/kWh-Endkundenpreis → EUR/Wh durch 1.000;
  keine zusätzlichen LUOX-, USt- oder Netzgebühren. Negative Preise bleiben gültig.
- Nur eine neue vollständige Day-Ahead-Preisversion kann einen separat freigegebenen
  EOS-Lauf auslösen. Verschobene Prognosefenster und SoC-Änderungen lösen keinen aus.
- EOS bleibt `PREDICTION`, Intervall 3.600 s. Der Helfer ruft keine periodischen
  Wetter-/Lastupdates auf und verändert weder Provider noch Gebühren oder Geräte.
- Vor Simulation: vollständiger Kontrollhorizont, frischer SoC, verifizierte Importe,
  keine aktiven EOS-Geräteadapter oder Benachrichtigungs-Webhooks.
- `sync-state.json` verhindert Wiederholungen nach Neustarts. Ein unklarer HTTP-Ausgang
  bleibt gesperrt und benötigt manuelle Prüfung. Dry-run verbraucht keine Live-Preisversion.

`soc.json`, `prices-source.json`, `prices.json` und `sync-report.json` ergänzen den
gemeinsamen Dateicache für spätere EMHASS-/HA-Verbraucher. Kein zusätzlicher Dienstport
und keine zweite externe Preisquelle sind erforderlich. Modul-3-Netzentgelte werden
nicht als aktive Preiskomponente ergänzt.
Die beiden CLI-Flags können kombiniert werden, jedoch nur nach entsprechender Freigabe.

```sh
docker compose up -d
docker compose logs --tail=50
docker inspect --format '{{.State.Health.Status}}' app-eos-pv-helper-1
```

Der konkrete Compose-Containername hängt vom Projektverzeichnis ab. Der Container läuft
als UID/GID 10001, ohne Ports, Docker-Socket, Geräte oder Privilegien. Nur das eigene
Ausgabeverzeichnis ist schreibbar; das Root-Dateisystem ist read-only.
Die Healthprüfung meldet Fehler oder veraltete Prüfungen. Eine früher importierte EOS-Reihe
wird bei neuen Fehlern nicht gelöscht. Deshalb später nur bei aktuellem healthy-Status und
ausreichendem Horizont optimieren; alte Dateien nicht als frische Prognose behandeln.

Ohne Compose kann dasselbe Image mit `docker build --target eos-source -t eos-pv-helper:local .`
und `docker run` installiert werden: `config.toml` read-only nach `/app/config.toml`, eigenes
`output` nach `/output`, `--read-only --cap-drop ALL --security-opt no-new-privileges`
und `--tmpfs /tmp:rw,size=16m --memory 512m`. Keine Ports oder bestehenden EOS-Volumes nötig.

## Alternative Datei-/HTTP-Eingabe

`source.kind="file"`, `path="/input/forecast.json"`, `format="records"` akzeptiert:

```json
[{"timestamp":"2026-06-20T10:00:00+02:00","power_w":3123.45}]
```

Hier zusätzlich die echten Koordinaten/Zeitzone unter `[location]` konfigurieren.
`records_path`, `timestamp_key`, `power_key`, `unit="W"`/`"kW"`,
`timestamp_convention="start"`/`"end"` sind konfigurierbar. Standardkadenz ist 900 Sekunden.
Für einen vorhandenen lokalen HTTP-Endpunkt `kind="http"` und `url` setzen; Tokens nur
über `bearer_token_env` aus privater Umgebung. Weiterleitungen sind deaktiviert.
`format="eos-series"` liest eine rohe EOS-`data`-Map. Leere Reihen werden abgelehnt.

## Tests und Abnahme

```sh
python -m pip install '.[test]'
ruff check src tests
pytest -q
docker build --target test -t eos-pv-helper:test .
docker run --rm --network none eos-pv-helper:test
docker build -f tests/integration/Dockerfile -t eos-pv-helper:eos-test .
docker run --rm --network none eos-pv-helper:eos-test
```

Der optionale EOS-Test verwendet echten, gepinnten EOS-Code und synthetische Daten.
Import und 48-h-Optimierung laufen **ohne Netzwerk** im temporären Prozess. Ein weiterer
Test ruft den nativen Forecast.Solar-Code auf, fängt aber den HTTP-Aufruf ab. Keine dieser
Prüfungen ist eine Freigabe oder ein Nachweis für das bestehende Unraid-/EOS-System.

Vor Schließen von Issue #1 müssen reale Rohdaten, Auflösung und Horizont geprüft,
Unraid-Dry-run und ausdrücklich freigegebener PV-Import zurückgelesen sowie ein separat
freigegebener Optimierungslauf mit genau dieser Prognose erfolgreich dokumentiert sein.
Diese Voraussetzungen sind nun [belegt](docs/GENETIC_ABNAHME.md). Merge und stabiler
Release bleiben gesonderte Freigabeschritte; daraus folgt noch kein Sparnachweis.
