# Validierung der Release-Vorbereitung, 29.10.2026

Ergänzung zu den [realen Betreiberbelegen](UNRAID_VALIDATION.md). Die folgenden
Tests liefen isoliert auf dem Entwicklungsrechner, ohne produktive Schreibzugriffe,
Optimierungsläufe, externe Prognoseabrufe oder Änderungen bestehender Container.

| Prüfung | Ergebnis |
| --- | --- |
| Vollständige pytest-Suite einschließlich gepinntem nativen EOS | **216 bestanden** |
| Ruff für `src`, `tests`, `scripts` | bestanden |
| Actionlint 1.7.12 | bestanden |
| `docker compose config --no-path-resolution --quiet` | bestanden |
| `git diff --check` | bestanden |
| Docker-Ziel `eos-source`, Python 3.11, gepinnter EOS-Quellstand | erfolgreich gebaut |
| `scripts/unraid_smoke.py --image eos-pv-helper:release-prep` | bestanden, `network=none`, 192 synthetische Viertelstunden |
| Paket-/Image-Lizenztest | eigenes Wheel `License-Expression=MIT` samt LICENSE; EOS-NOTICE/Apache-Text und Inventar im Image vorhanden |
| Tatsächliches Inventar des lokalen Vollimages | 110 Python-Komponenten, 105 OS-Copyright-Nachweise; Quellenarchive DEAP, moocore, SciPy, loguru, dnspython |
| Reale automatische GENETIC-Abnahme | **bestätigt**: Betreiberbeleg, gespeicherte Datei und unabhängiger lesender Schema-/Doctor-Lösungscheck; [Beleg](GENETIC_ABNAHME.md) |
| Stable-Release-Gate bei alleiniger GENETIC-Abnahme | wird erwartungsgemäß abgewiesen: vollständiger Live-Doctor-Beleg, Lizenzreview und ausdrückliche Release-Freigabe bleiben getrennt |

Neue Tests belegen insbesondere:

- Doctor liest vorhandene Sync-Artefakte ohne HTTP oder Dateiveränderung; aktive
  Writer, fehlende/kaputte Lösungen, falscher Start/Intervall, nicht endliche
  Kosten, unzulässige Steuerwerte, abweichender Preis-/Claim-Hash, unsicherer
  Versionspfad, veraltete Reports und falsche SoC-Belege werden abgelehnt.
- `waiting-publication` wird von tatsächlicher Abnahme getrennt; auch ein
  vorhandenes Lösungsfile ersetzt keinen bestätigten `succeeded`-Claim.
- Neuer Regressionstest bildet den Betreiberfall ab: evcc liefert trotz extern
  schon bekannter Preise zunächst nur den aktuellen Tag; mehrere reguläre Ticks
  warten ohne POST. Nach tatsächlicher Veröffentlichung löst ein normaler Tick
  genau einen Lauf aus. Persistierter Claim und unveränderte Lösung verhindern
  nach erneuter Instanziierung einen zweiten POST; der Doctor bestätigt den Verlauf.
- Beim SoC-Mismatch erfolgt höchstens ein frischer gemeinsamer State-GET;
  ursprünglicher Gerätebeleg, 300-s-Grenze und Auswahl einer einzelnen Batterie
  bleiben erhalten. Kein zweiter Geräte-Getter. Verbleibende Abweichung, Timeout,
  Fehler, Duplikate, fremde Version oder unplausible Leistung bleiben gesperrt.
- Preise verwenden nach einem erfolgreichen Retry denselben erneuerten Snapshot.
- Eigene MIT-Metadaten, Vendor-Notices, LGPL-Quellarchivbehandlung und exakt
  versionierte fehlende Upstream-Lizenzen werden geprüft; unbekannte fehlende
  Lizenzen lassen den Build fehlschlagen.
- Stabile Tags sind von Kandidaten getrennt; Promotion folgt erst Registry-Test
  und realem Abnahme-/Inventarbeleg. Ausstehende/abweichende Belege sperren.

Noch kein vollständiger Fremdlizenz-Abschluss: Für das in SciPy und NumPy gebündelte
`libquadmath` muss die zum tatsächlich ausgelieferten Build passende GCC-Quelle
belegt werden. Das SciPy-sdist und die Lizenztexte allein sind kein solcher Beleg.
[Einzelheiten](../THIRD_PARTY_NOTICES.md). Kein stabiler Tag, Merge oder Release
wurde durch diese lokalen Prüfungen freigegeben.

CI-Ergebnisse müssen sich auf den veröffentlichten aktuellen PR-Commit beziehen;
ein älterer grüner Lauf ist kein Nachweis für diese Änderungen. Der unveränderte
Template-Digest in `IMAGE_PUBLICATION.json` bezeichnet weiterhin das bereits
real vom Betreiber eingesetzte Vorgängerimage; Vorschau-Publishing aktualisiert
keinen produktiven Helfer. [Abschluss-Schritte und Gates](RELEASE_CHECKLIST.md).
