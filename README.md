# EOS PV-Prognose-Helfer

Validiert vorhandene Forecast.Solar-Prognosen für Akkudoktor EOS und stellt eine zentrale
UTC-Viertelstundenreihe bereit. Keine Gerätebefehle, keine neue Wetter-API und kein eigener
Forecast.Solar-Client: verwendet wird der originale EOS-Provider `PVForecastForecastSolar`.

**Standard: Dry-run und Cache-only.** Ein externer Abruf braucht zwei ausdrückliche
Opt-ins, ein Import ins bestehende EOS zwei weitere. Unraid-/Produktionsabnahme steht
noch aus. [Issue #1](https://github.com/vbeinlich/EOSPVPrognoseHelfer/issues/1) bleibt offen.

## Recherche zuerst

Die [Recherche und Entscheidung](docs/research.md) erklärt, warum `PVForecastImport`
allein keine Nachtlücken ergänzt. Der aktuelle GENETIC-Optimierer verlangt vollständige
Rohdaten, auch nachts. Allgemeine EOS-Interpolation unterscheidet Tages-/Nachtlücken nicht.
Ein nativer direkter Import bleibt vorzuziehen, wenn die Quelle bereits vollständig ist.

## Datenvertrag

- 48 verstrichene Stunden ergeben 192 UTC-Intervalle à 15 Minuten, auch bei DST-Wechseln.
  Der Horizont ist konfigurierbar. Ein zu kurzer Quellhorizont führt zum Fehler.
- Nur **vollständig nächtliche** fehlende Intervalle werden mit 0 W ergänzt. Astral
  berechnet Sonnenaufgang/-untergang lokal; keine festen Nachtuhrzeiten.
- Vorhandene Werte auf dem Zielraster einschließlich Tages-0-W bleiben unverändert.
  Null, NaN, negative Werte, Duplikate und unklare Zeitstempel sind Fehler.
- Forecast.Solar liefert Leistungs-Stützstellen. Bei ausdrücklich stündlicher Quelle
  werden zusätzliche Viertelstunden linear zwischen benachbarten Stützstellen berechnet.
  Die Originalwerte bleiben im Rohcache erhalten; vorhandene Rasterpunkte bleiben exakt.
  **Abstände über die deklarierte Quellkadenz werden tagsüber nicht interpoliert.**
- Rein viertelstündliche Datei-/HTTP-Quellen sind strikt: jeder fehlende Tagespunkt ist
  ein Fehler. Es gibt weder pauschales ffill noch Nullfüllung tagsüber.
- Eine Prognose mit 26 Stundenwerten belegt keine 48 Stunden. Ein fehlender Tageshorizont
  wird nicht erfunden; ggf. muss der Betreiber einen kürzeren geprüften Horizont wählen.
- `source.json` ist der zentrale native Rohcache, `forecast.json` die EOS-kompatible Reihe,
  `report.json` der Qualitätsnachweis. Später kann EMHASS diese Dateien mitbenutzen und
  muss Forecast.Solar nicht erneut abrufen.

## Wiederverwendung des EOS-Providers

Der Helfer liest per GET die bestehende EOS-Konfiguration. Koordinaten, Zeitzone,
PV-Flächen, Neigung, Azimut, kWp und ggf. API-Key werden daraus übernommen, nicht erfunden.
`native_forecast()` ruft ausschließlich die originale `_request_forecast()`-Methode eines
gepinnten EOS-Commits in einem **lokalen Helferprozess** auf. Die EOS-Instanz auf dem Server
wird nicht umkonfiguriert. Andere Provider und EMS-Läufe werden nicht gestartet.

Der persistente Rohcache ist an die EOS-Parameter gebunden, maximal eine Stunde gültig
und mit einem Dateilock gegen parallele Abrufe geschützt. Solange er gültig ist, wird
auch mit Abruffreigabe kein weiterer Abruf ausgelöst. Mehrere PV-Flächen erfordern gemäß
EOS je einen Request pro Fläche; nicht einen zusätzlichen Client pro Verbraucher.

Die vorhandene EOS-Installation muss `PVForecastImport` verwenden. Ist dort Forecast.Solar
selbst aktiv, verweigert der Helfer die zweite Abrufstrecke. Die konkrete native Auflösung
ist vor Produktivbetrieb gegen `source.interval_seconds` zu prüfen.

**Größentradeoff:** Das Ziel `eos-source` enthält die EOS-Abhängigkeiten, um keinen zweiten
Client zu pflegen. Das Ziel `normalizer` ist schlank (Python, Astral, tzdata) und kann
bereits exportierte Datei-/lokale HTTP-Prognosen verarbeiten. Es kann selbst nicht abrufen.

## Unraid-Installation

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

**Erst nach separater EOS-Schreibfreigabe:** zusätzlich `eos.write_enabled=true` und
`--write-eos` verwenden. Einzige produktive Schreiboperation ist
`PUT /v1/prediction/import/PVForecastImport`, anschließend GET zur Rückleseprüfung.
Kein `force_enable`, kein Provider-Update, keine Konfigurationsänderung oder Optimierung.
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
Ein PR-Merge schließt das Issue nicht automatisch.
