# Explizite Gegenprobe für PR #22

Nur synthetische Daten. Getesteter Quellcommit ist `db5b304`.
Der separate Reviewbranch verändert keine Anwendungs-, Engine-, Wrapper-,
Workflow- oder Testdateien; die einzige bestehende Dateiänderung ist ein UTF-8-Banner.
Dies ist ein Reviewbericht mit reproduzierten offenen Findings, kein Fix-PR.

Auf einem **lokalen Linux-Diagnoserechner**, nicht auf Unraid, ein bereits lokal
vorhandenes Entwicklungs-Testimage mit Python 3.11 und den Testabhängigkeiten nutzen.
`LOCAL_TEST_IMAGE` ist durch dessen Namen zu ersetzen; nicht das Produktivimage
verwenden und keine Installation oder Containeränderung auf dem NAS durchführen.

```sh
git diff --exit-code db5b304 -- src tests scripts .github Dockerfile pyproject.toml
docker run --rm --pull=never --network none --read-only --cap-drop=ALL \
  --security-opt=no-new-privileges --user 10001:10001 \
  --tmpfs /tmp:rw,nosuid,nodev,mode=1777 \
  --mount type=bind,source="$PWD",target=/work,readonly \
  -e PYTHONPATH=/work/src:/work/tests -w /work --entrypoint python \
  LOCAL_TEST_IMAGE -B review/pr22_contract_probe.py
probe_exit=$?
printf 'review_probe_exit=%s\n' "$probe_exit"
```

**Erwartet auf db5b304: Exit 2, R1 und R2 BLOCKED.** Exit 0 wäre bei behobenen
Verträgen zu erwarten, ersetzt aber weder Gesamttests noch private Abnahme.
Ein Traceback/anderer Exit ist ein fehlerhafter Testaufbau, kein positiver Beleg.
Die Socket-Sperre liegt zusätzlich zum isolierten Docker-Netzwerk vor. Es werden
nur synthetische Dateien in einem temporären Verzeichnis angelegt und entfernt.

Der gespeicherte [JSON-Befund](pr22_contract_probe_result.json) stammt aus diesem
lokalen Lauf. Er enthält keine echten Messwerte, Gerätetitel, IPs oder Secrets.
Die normale Pytest-/GitHub-CI auf db5b304 enthält diese neu geschriebenen
Negativgegenproben noch nicht; deren Grün ist nicht die Aufhebung der Findings.

[Vollständiger Merge-Gate-Bericht](../docs/PR22_MERGE_GATE_REVIEW.md).
