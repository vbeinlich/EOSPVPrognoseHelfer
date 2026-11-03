# PR22-Gegenproben vor und nach der Korrektur

Der Originalbericht und `pr22_contract_probe_result.json` dokumentieren den
BLOCKED-Befund auf db5b304 / Review 1282d77. Sie bleiben als historische Artefakte
erhalten. Das aktuelle Programm prueft dieselben Widersprueche fail-closed;
`pr22_contract_probe_result_after.json` dokumentiert PASS mit dem neuen Enginehash.

Die erweiterte unabhaengige Vektorsammlung in `scripts/evidence_vectors.py` wird
verpflichtend von Unit- und echten Altimage-Consumern verwendet. Sie berechnet
Datei- und Parameterhashes fuer falsche Werte neu; ein reiner Hashcheck reicht
also nicht. Legacy wird separat als lesbar, aber eingeschraenkt geprueft.

Nur auf einem lokalen Linux-Diagnoserechner mit bereits vorhandenenen
Testabhaengigkeiten und aktuellem Korrekturcheckout ausfuehren, nicht auf Unraid:

```sh
python scripts/update_evidence_transports.py
PYTHONPATH=src:scripts:tests python review/pr22_contract_probe.py
pytest -q -m 'not genetic_execution'
```

Erwartet auf dem Korrekturstand: Exit 0, R1 und R2 PASS. Auf dem alten Code wurden
die Widersprueche angenommen. Traceback oder unerwarteter Exit ist kein Beleg.
Die regulare CI verlangt jetzt diese Gegenprobe, alle Consumer-Negativtests,
Actionlint sowie Non-root-/Read-only- und Transporthash-Gates.

Die Gegenprobe sperrt Socket-Aufrufe und nutzt ausschliesslich temporaere
synthetische Dateien. Kein Quelladapter, Live-HTTP oder nativer Optimierer.
Synthetische Ergebnisse sind keine reale private Doctor- oder Betreiberabnahme.

[Pruefvertrag](../docs/INPUT_BINDING_CONTRACT.md) und
[erneuter Gate-Bericht](../docs/PR22_INPUT_BINDING_FIX_REVIEW.md).
