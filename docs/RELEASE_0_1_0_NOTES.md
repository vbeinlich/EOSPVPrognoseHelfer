# EOSPVPrognoseHelfer v0.1.0 – vorbereitete Release Notes

**Entwurf, keine Veröffentlichung oder Distributionsfreigabe.** Den tatsächlichen
Digest, Inventar-/Quellarchivhash und aktuelle CI-Links nach Freigabe aus dem
Readiness-Nachweis übernehmen; keine nicht vorhandene Veröffentlichung behaupten.

- Forecast.Solar über nativen gepinnten EOS-Provider, dynamischer validierter
  Viertelstundenhorizont, astronomische Nachtfüllung und strenge Tageslückenprüfung.
- Zentrale Cache-/Dateilocks, nachvollziehbare Preis-/SoC-Importe und separat
  freigegebene idempotente GENETIC-Simulation. Keine Geräteansteuerung.
- Docker/Unraid mit Non-root/read-only, Dry-run/Cache-only als Vorgaben;
  Installation, Update und Rollback dokumentiert.
- Rein lesender Doctor einschließlich explizit historischer privater Snapshots.
- Manuelle, digest- und inventargebundene Distribution statt automatischer Images
  durch Main-/Preview-/Tag-Pushes; vollständig indexiertes Quellmaterial.

Eigener Code und Dokumentation: MIT. EOS und alle mitgelieferten Komponenten/Daten
behalten ihre ursprünglichen Lizenzen. Vollständige Notices im Image,
Quellmaterial als getrenntes versioniertes Release-Asset. Siehe
`THIRD_PARTY_NOTICES.md`, `docs/LICENSE_REVIEW.md` und `docs/RELEASE_0_1_0_READINESS.md`.

Ein Update des bestehenden produktiven Helfers ist eine gesonderte Betreiberaktion.
Bestehende Konfiguration, Claims und Lösungen erhalten; kein Reset oder zweiter
Helfer mit demselben Output. Neue Installationen beginnen im Dry-run.

Wizard/Skill #5 und Savings Dashboard #6 sind nicht Teil von v0.1.0. Ein
GENETIC-Kostenwert ist kein nachgewiesener Sparbetrag.
