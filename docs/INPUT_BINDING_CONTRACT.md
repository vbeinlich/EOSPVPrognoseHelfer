# Ereignisprüfung v2: Originale → Request → Solver

Korrektur von R1/R2/R3 aus dem Review `1282d77`, Stand 03.11.2026.
Kein Deployment, keine neue Optimierung und keine Gerätefreigabe.

## Ein Vertrag, vier Consumer

Die einzige fachliche Validierung liegt in `src/eos_pv_helper/historical.py` und
benötigt ausschließlich Python 3.11 und die System-Zeitzonendaten. App-Doctor,
Archivwriter, eigenständiger Export-Doctor und Plan-Inspector verwenden dieselbe
Funktion. `event_context.py` erstellt nur sichere Beobachtungen und reexportiert
die kanonischen Hilfsfunktionen; es enthält keine zweite Validierungslogik.

`validation_contract = eos-pv-helper/event-evidence-v2` ist unabhängig vom
weiterhin lesbaren ZIP-Schema 2 und dessen exakt sieben Originalartefakten.
Ein neuer Request-Beleg wird im ursprünglichen `sync-report.json` unter
`event.request_binding` gespeichert, mit eigenem Vertrag
`eos-pv-helper/solver-input-binding-v1`:

- unverändertes `request`-Payload, ausschließlich der bestehende SoC-/Preisrequest;
- `request_sha256` über sortiertes kompaktes JSON ohne NaN;
- tatsächliche Client-Zeitbasis `timezone` und `origin_utc`;
- kein achtes Rohartefakt, kein Token, keine Konfigurationsdatei.

Der Beleg wird vor dem bereits vorhandenen POST erzeugt. Keine Anfrage, Preise,
PV-Prognose oder Claim-Semantik wird verändert. Ein Fehler in der zusätzlichen
Archivmetadaten-Erfassung startet keinen Retry und unterdrückt keine bisher
freigegebene normale Anfrage; stattdessen `evidence_missing`, Health nicht OK.

## Umfang und Ergebnisse

| Ergebnis | Exitcode Doctor | Umfang |
| --- | --- | --- |
| `accepted`, `input_binding_complete=true` | 0 | Originalartefakte konsistent und gespeicherter Request mit den zurückgegebenen SoC-/Preis-/PV-Eingaben gebunden |
| `legacy_limited`, `accepted=false`, `readable=true` | 2 | Sieben Originale konsistent, aber keine vollständige Request-Bindung; `validation_scope=event_artifacts_only` |
| `blocked` | 1 | Widerspruch, beschädigte vorhandene Metadaten, ungültige Zeitbasis/Hashes oder unvollständige Originalartefakte |

Alle Consumer urteilen gleich über denselben Umfang. Der Writer verlangt für
ein neues vollständiges Erfolgsarchiv Exit-0-Qualität. Der Inspector zeigt Legacy
sichtbar eingeschränkt und schaltet dort keinen als verifiziert bezeichneten
PV-/Preisoverlay frei. Ein nicht vorhandener optionaler Kontext ist kein
beschädigter Kontext. Vorhandene unvollständige Kontextfelder und falsche Hashes
werden jedoch überall abgelehnt, auch im alten Container mit externer Engine.

Der Live-Doctor ohne Archiv bleibt als `live_status_only` gekennzeichnet; sein
aktueller Frischecheck ist kein vollständiger historischer Eingabenachweis.
Vier-Artefakt-Schema-1-Exporte reichen weiterhin nicht für die historische Abnahme.

## Zeit- und Wertbindung

Der unterstützte installierte EOS-Vertrag ist der native stündliche GENETIC-Pfad
aus Quellstand `8a8cd43a1915668927eda5504b7de039c2e762b4`:

1. `ConfigOptimizationRequest.resolve` erwartet die Preisreihe ab **lokalem
   Mitternacht**. Der gespeicherte Request muss genau denselben Zeitraum abdecken
   wie die Originalpreise und genau am validierten Control-/Tail-Ende enden.
2. `GeneticOptimization._parameters_for_slot_grid` entfernt den Mitternachtspräfix.
   Zurückgegebene Parameter sind bei `controls_start_at_now=true` **laufrelativ**.
   Ihr Umfang ist exakt Control + belegter Tail. Keine Rate-/Indexverschiebung.
3. UTC-Zeitdifferenzen bestimmen den Offset, einschließlich der beiden gleichen
   Lokalstunden beim Herbstwechsel. Auf Frühlings-/Herbsttagen keine pauschalen
   24-Stunden-Offsets verwenden. Die IANA-Zeitzone muss übereinstimmen.
4. SoC-Request = `int(original_percent)` wie im bestehenden Helfer und EOS-Pfad.
   55,999 % wird explizit als 55 % gesendet; 0 % und 100 % sind mit gültigem
   ursprünglichen Frischebeleg erlaubt. Zurückgegebenes Gerät und Start-SoC müssen passen.
5. Viertelstündliche PV-Werte werden nur über vollständig bedeckte Quellintervalle
   gemittelt und einmalig von W nach Slot-Wh umgerechnet. Gültige Tagesnullen
   bleiben gültig, fehlende Intervalle werden nicht erfunden.
6. Preise bleiben EUR/Wh; negative Werte sind erlaubt. Keine erneuten LUOX-Aufschläge.
   Vergleichstoleranz: relativ `1e-9`, absolut `1e-12 EUR/Wh` bzw. `1e-6 Wh` für PV.
   Das erlaubt Gleitkommaabweichungen, keine Zähler-/Preisrundung auf Cent.
7. Zurückgegebene Last-/Einspeisetarifreihen müssen den verwendeten Horizont
   vollständig und endlich enthalten. Ihre Originalbytes bleiben in der Lösung.
   Es wird dadurch keine unabhängige Lastquellen- oder Jahreslastprovenienz behauptet.

Unbekannte neue Intervalle/Profile werden nicht geraten. Legacy-Parameter mit
nicht belegbarer Zeitbasis bleiben eingeschränkt. Bei erkanntem alten Profil
werden bereits beweisbare SoC-/PV-/Preiswidersprüche auch ohne Request-Beleg abgelehnt.
Mehrdeutige JSON-Duplikate und NaN/Infinity in Originaldateien sind keine gültige Evidenz.

## Transparente Restgrenzen

`exact_solver_options_proven=false` bleibt bestehen. Die 11.251-kWh-Jahreslast,
globale Solveroptionen, Config-Races und der atomare No-Device-Vertrag aus **#21**
werden hierdurch ausdrücklich nicht als bewiesen markiert. Hashes belegen
Konsistenz, keine vertrauenswürdige Erhebung oder Signatur. Betreiberprovenienz
und historische Frische am ursprünglichen Claim bleiben gesonderte Prüfungen.

Ein Crash vor dauerhafter vollständiger `.ready`-Datei kann weiterhin
`evidence_missing` ergeben. Keine Rekonstruktion alter Reports, neuen Preise unter
alten Claims oder Optimierungswiederholung. Diese aus #13 bekannte Verfügbarkeitsgrenze
ist weder durch v2 geschlossen noch als verlustfreie Archivierung freigegeben.

## Entwicklung und Operator-Vorbereitung

[Code-/Transporthashes](INPUT_BINDING_TRANSPORTS.json), keine Image-/Lizenzfreigabe.
Entwicklungsbefehle, ausschließlich im lokalen Checkout:

```sh
python scripts/update_evidence_transports.py --write
python scripts/update_evidence_transports.py
pytest -q -m 'not genetic_execution'
PYTHONPATH=src:scripts:tests python review/pr22_contract_probe.py
```

Der erste Befehl bettet die neue Engine ein und aktualisiert das öffentliche
Hashmanifest; er ist kein Unraid-Befehl. Ohne `--write` ist es ein strenger CI-Check.
Das deterministische Inspector-Bundle enthält dieselbe Engine. Die Operatoranleitung
muss zum exakt geprüften Korrekturcommit und dessen Hashmanifest passen.

**Migration:** bestehende ZIPs, Claims und Lösungen nicht verändern. Ohne damals
erfassten Request bleibt ein altes Archiv eingeschränkt; keine neue Metadaten-
„Bestätigung“ hineinbauen. Neue vollständige Belege entstehen erst nach separat
freigegebenem Imagewechsel/Archiv-Opt-in beim nächsten ohnehin regulären Erfolg.
Keinen neuen Lauf zur Abnahme erzwingen. Das produktive Image bleibt hier unverändert.

[Erneuter Gate-Bericht](PR22_INPUT_BINDING_FIX_REVIEW.md).
