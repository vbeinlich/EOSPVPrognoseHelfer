# Endgültige GENETIC-Abnahme zu Issue #1

Stand: 29.10.2026. Die ursprünglich fehlende End-to-End-Abnahme ist jetzt erfüllt.
[Konsolidierter Abschlussbeleg in Issue #1](https://github.com/vbeinlich/EOSPVPrognoseHelfer/issues/1#issuecomment-6497898549).
Diese Feststellung betrifft Prognose-/Messwertimporte und einen berechneten,
persistierten Simulationsplan. Sie bestätigt keine Geräteansteuerung oder Ersparnis.
Der produktive Helfer wurde durch diese Prüfung nicht verändert.

## Reale Herkunft und Persistenz: Betreiberbeleg

Der Betreiber dokumentiert in [Issue #1](https://github.com/vbeinlich/EOSPVPrognoseHelfer/issues/1#issuecomment-6497116506)
und [PR #3](https://github.com/vbeinlich/EOSPVPrognoseHelfer/pull/3#issuecomment-6497605866):

- Nach `waiting-publication` hat evcc die vollständigen nächsten Day-Ahead-Preise
  übernommen. Ohne manuellen Trigger erschien anschließend der Plan in EOS.
- `event.status=succeeded`, `errors={}`, `delivery_day=2026-10-30`,
  `delivery_intervals=96`.
- Preisversion: `46d32bd047bc983219b9a85b1b6d3a1f8e4eaded90c2d0a9aee6fc42c88c5484`.
- Der Betreiber hat die dazugehörige persistierte `solution-<version>.json` gelesen.
  Die Datei ist auch beim unabhängigen SMB-Verzeichnislesen sichtbar (121692 Bytes;
  Dateizeit 29.10.2026 13:44:16 MEZ / 12:44:16 UTC). Diese Dateizeit ist kein
  vollständiger Laufzeit-/Dispatch-Zeitstempel.
- PV im erfolgreichen Ablauf: `validated_hours=41.0`, Minimum 24 h,
  `mode=write`, `import_verified=true`. Zuvor wurden 175 Viertelstunden/43,75 h mit
  110 Nachtfüllungen sowie authentifizierter frischer RSCP-SoC und 96 korrekt
  rückgelesene Preisintervalle abgenommen.

Die Verzögerung zwischen externer Veröffentlichung und evcc-Verfügbarkeit ist
ein beobachteter Upstream-/Tarif-Cache-Effekt. Der Helfer hat bis zur tatsächlichen
Verfügbarkeit seiner autoritativen evcc-Quelle korrekt gewartet. Er darf dafür
keine zweite Marktpreisquelle abfragen oder fehlende Preise erfinden.

## Unabhängiger lesender Abgleich mit dem Doctor

Am **29.10.2026, 13:18:30 UTC / 14:18:30 MEZ** wurde ausschließlich die bereits
vorhandene Lösung über `GET /v1/energy-management/optimization/solution/GENETIC`
geprüft. Der vorher im gepinnten EOS-Code geprüfte Handler gibt nur die gespeicherte
In-Memory-Lösung zurück; er ruft weder Optimierung noch Prognoseupdates auf.
Zusätzlich wurde das installierte `/openapi.json` lesend abgerufen. Keine weiteren
Gerätezugriffe, Importe, POSTs, Konfigurationsänderungen oder Neustarts.

Die eigentliche Validierung lief **offline auf dem Entwicklungsrechner**:

| Prüfung | Tatsächliches Ergebnis |
| --- | --- |
| Installierte EOS-Version | `v0.3.0.dev2602241646141478` |
| Vollständiges `GeneticSolution`-Schema aus installierter OpenAPI | 0 Validierungsfehler |
| Dieselbe `verify_solution()`-Funktion, die der Doctor verwendet | bestanden |
| Erwarteter Planstart aus Betreiberbeleg | `2026-10-29T13:00:00+01:00` = `12:00:00 UTC` |
| Kontrollhorizont / Intervall | 24 h / 3600 s |
| `ac_charge`, `dc_charge`, `discharge_allowed` | jeweils 24 vollständige gültige Werte |
| Last, Netzbezug, Einspeisung, Verluste, SoC, Strompreis, Stundenkosten | jeweils 24 endliche Stundenwerte |
| `result.total_costs` | `2.687513895312027` €; identisch mit Betreiberbeleg |
| `result.total_losses` | `2373.7471929170215` Wh |
| Tatsächlich gedeckter Tail | 11 h; getrennt von 24 h Kontrolle |
| `terminal_value.battery_energy_wh` | `9145.803773224492` Wh |
| `terminal_value.credited_euro` | `0.7381608151121515` € |
| `fitness_history` | vorhanden |

Maschinenlesbare, auf diese Prüfung begrenzte Zusammenfassung:
[GENETIC_RESULT_VERIFIED.json](GENETIC_RESULT_VERIFIED.json).
Der SHA256 der **GET-Antwortbytes** ist
`9d2acc2ca585f915784cbd891100fc551cab8b194b2b065a01e0bff1ba5fe284`;
der kanonische semantische JSON-Hash ist
`a9eb07226fa8b66ab0e4d315c4872a0a7895f540e07f8ac48ecd89cd3c8a15cc`.
Diese Hashes sind ausdrücklich **keine behaupteten Hashes der privaten NAS-Datei**;
unterschiedliche JSON-Einrückung erklärt bereits unterschiedliche Dateigrößen.

## Grenzen und Entscheidung

`sync-report.json`, `sync-state.json`, `prices.json` und die persistierte Lösung
sind über den verfügbaren SMB-Zugang weiterhin nicht inhaltlich lesbar. Rechte
wurden nicht verändert. Deshalb wurde kein vollständiger Live-Doctor mit
`accepted=true` fingiert und kein Claim-/Preisdatei-Hash rekonstruiert. Der Doctor-
Lösungsteil und das installierte Ausgabeschema sind unabhängig grün; automatische
Herkunft, Eventversion, Fehlerfreiheit und Persistenz sind vom Betreiber bestätigt.
Zusammen erfüllen diese Belege die angeforderte endgültige Abnahme von Issue #1.

Die neue synthetische Regression bildet denselben Ablauf mit dem vollständigen
Doctor nach: mehrere Ticks nur mit heutigen Preisen → kein POST/kein Claim;
Veröffentlichung → genau ein automatischer POST, bestätigte gespeicherte Lösung;
erneute Instanziierung mit demselben Versionshash → kein zweiter POST und dieselbe
Datei. Sie verändert keine Produktionsdaten und ist kein Ersatz für den obigen
realen Beleg. Aktueller Umfang: **216 Tests mit gepinntem EOS**.

Der MIT-Release bleibt ein eigener Freigabeschritt: vollständiger privater Doctor-
Beleg für das bestehende strenge Release-Gate, konkret passende libquadmath/GCC-
Quellen, kandidatenspezifische Lizenzprüfung sowie ausdrückliche Merge-/Release-
Freigabe. Kein neuer produktiver Lauf ist zur Abnahme nötig. [Release-Checkliste](RELEASE_CHECKLIST.md).

## Bedeutung für die nächste Phase

**2,6875 € sind simulierte Kosten, kein Sparbetrag.** Ein Vergleichslauf des normalen
E3/DC-PV-Eigenverbrauchsbetriebs fehlt. Weder Endenergie noch Terminalgutschrift
dürfen allein als Mehrersparnis ausgegeben werden. Die nächsten Schritte bleiben
PR #3/Release → Wizard/Skill #5 → [Savings Dashboard #6](ROADMAP.md).
