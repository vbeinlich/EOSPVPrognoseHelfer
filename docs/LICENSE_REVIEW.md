# Lizenzprüfung des vollständigen Image-Inventars

Technischer Prüfstand 30.10.2026, `linux/amd64`, Dockerfile-Ziel `eos-source`.
**Vorbereiteter Distributionsnachweis, keine erteilte Release-Freigabe.**
Die Prüfliste umfasst 110 Python-Distributionen und 105 OS-Pakete sowie außerhalb
dieser Paketlisten enthaltenes CPython, native Wheel-Bibliotheken und Daten.
Die folgenden Versionen stammen aus dem lokalen Prüfbau; der abschließende
Kandidat und seine Hashes werden getrennt im [Ergebnisprotokoll](RELEASE_BLOCKER_RESULTS.md)
festgehalten. Neubauten müssen erneut abgeglichen werden. Der alte öffentliche
Preview-Digest wird nicht rückwirkend als geprüft freigegeben.

## Pflichten und konkrete Umsetzung

| Bestandteil | Pflichten / Umsetzung | Restgate |
| --- | --- | --- |
| Eigener Code | MIT, LICENSE und Paket-Metadaten beibehalten | Review des Quellstands |
| EOS, Astral, Apache-Komponenten | Lizenztext, Attribution und vorhandene NOTICE erhalten; EOS unverändert unter `/opt/eos` | inventargebundene Freigabe |
| MIT/BSD/ISC/PSF/Unlicense/Zlib/OLDAP und weitere permissive Texte | Originaltexte und Disclaimer, gegebenenfalls Werbe-/Namensnutzungsbedingungen erhalten; nicht zu MIT umdeklarieren | Originalnotices im konkreten Image prüfen |
| DEAP / moocore | LGPL-3.0 / LGPL-2.1-or-later; passende sdists, Lizenzen und Builddateien im Image und Quellarchiv; Austausch und Debugging zulässig | anonym verfügbares Quellmaterial vor Distribution |
| libquadmath | LGPL-2.1-or-later; unten belegte GCC-SRPMs inklusive Patches, Spezifikationen und Lizenztexte im separaten Quellarchiv | öffentliches Archiv und konkrete Freigabe |
| GCC-Runtimes mit Runtime Library Exception | Original-GPL-/Exception-Texte erhalten; Ausnahme ist keine pauschale Aufhebung von Pflichten an separat ausgelieferten Runtime-Bibliotheken | exakte Originalnotices mitprüfen |
| lxml / libiconv | lxml überwiegend BSD/PSF, eingebettetes iconv LGPL-2.1; vollständiger lxml-Quellcode plus passende native Quellen und Relink-Anleitung | Quellmaterial und Relink-Prüfung unten |
| certifi, OS-CA-Zertifikate | MPL-2.0: bevorzugte bearbeitbare Quellen und Bezugsinformation; certifi-sdist samt PEM, Debian-ca-certificates-Quellen enthalten | tatsächliches Quellenangebot |
| tzfpy | MIT-Code, Rust-Notices und ODbL-Daten gesondert behandeln; unveränderte Daten plus Parser/Exportcode im Quellarchiv, Attribution und ODbL-Text im Image | unverändertes Quellenangebot und Attribution |
| NumPy/SciPy/OpenBLAS | Originale verschachtelte BSD/MIT/Zlib/CC0/SVML/Highway/LAPACK/Qhull-Notices erhalten; GCC/quadmath separat geprüft | keine bloße Bewertung anhand des obersten BSD-Feldes |
| Pillow/Matplotlib/h5py | PIL/MIT-CMU, FreeType, Codec-/HDF-Notices und DejaVu/STIX-Fontbedingungen erhalten; keine Schriftumbenennung/Änderung | tatsächliche Komponenten statt aller optionalen Lizenzabschnitte |
| pip/setuptools/uvloop/tzfpy und vendorte Komponenten | Alle verschachtelten Notices werden kopiert, Apache-/MIT-/BSD-/Unicode-Texte erhalten | kein Weglassen der Vendor-Lizenzen beim Slimming |
| Debian-OS einschließlich glibc/OpenSSL/Utilities | 105 exakte Binärpakete → 73 Source-Versionen; 235 Dateien mit `.dsc`-SHA256 geprüft; gesamte Quellgruppen samt Debianpatches im Archiv | öffentliches Archiv vor neuer Binärdistribution |
| CPython aus offiziellem Python-Basisimage | PSF-/historische Originaltexte unter `/usr/local/lib/python3.11/LICENSE.txt`, Basisimage per Digest gepinnt, Docker-Library-Buildanleitung verlinkt | keine MIT-Umlizenzierung |

Maßgeblich sind die vollständigen Originaltexte, nicht Metadaten oder aus
Copyright-Dateien extrahierte Stichworte. Eine Quellpaket-Lizenz kann auch nur
Tests/Buildtools betreffen. Keine pauschale Behauptung, jedes erwähnte GPL-/LGPL-
Modul sei eingebaut. Pillow meldet im Prüfbau `raqm=false`, `libimagequant=false`;
deren optionale Hinweise werden nicht als tatsächlich aktivierte GPL-Features gewertet.

Primärquellen: [LGPL-2.1](https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html),
[GCC Runtime Library Exception](https://www.gnu.org/licenses/gcc-exception-3.1.html),
[MPL-Verteilung](https://www.mozilla.org/en-US/MPL/2.0/FAQ/),
[ODbL §§4.2–4.6](https://opendatacommons.org/licenses/odbl/1-0/),
[Python-Image-Build](https://github.com/docker-library/python).

## Passende GCC/libquadmath-Quellen

[Maschinenlesbarer Nachweis](../licenses/native-sources.json): zwei verschiedene
Payloads, drei Dateien in NumPy/SciPy. Für beide stimmen Build-ID, `.text`,
`.rodata` und `.eh_frame` bytegenau mit dem Original-Binärpaket überein.

| Wheel-Payload SHA256 | Original | Exaktes Quellpaket-SHA256 |
| --- | --- | --- |
| `6ed5137f412781ad7863439fb543613f620b43c32b63292a0029246162f5bbc6` | CentOS GCC 4.8.5-44.el7 | `642c4085f6af9565e39583e54a9d7a5d9e6b93dd8c8e9474aec8a892d6c7aa36` |
| `71bdc2ec57ab2fc939360597968f73230426b1c6764048e62a2cb6c8d8c3a1fd` | AlmaLinux GCC 8.5.0-26.el8_10.alma.1 | `0911864c260a75ae030f3144616e7e5e1359e04ce1c9730ab83906486e3bc79f` |

Nicht nur eine ähnliche GCC-Versionsnummer: die vollständigen SRPMs wurden
privat heruntergeladen und enthalten `gcc.spec`, Originaltar und Distributorpatches.
Wheel-Umbenennung/ELF-Relokation ändern die obigen ausführbaren Abschnitte nicht.
Ein identischer Gesamt-Wheel-Rebuild wird dadurch nicht behauptet. Ein neuer
libquadmath-Hash sperrt den Build, bis seine Zuordnung erneut geprüft wurde.
Für einen nativen Rebuild das jeweilige SRPM in einer passenden isolierten
RPM-Buildumgebung mit `rpmbuild --rebuild` und dem enthaltenen `gcc.spec` verwenden.

## lxml und statisch eingebettetes libiconv

`_libiconv_version=0x112` in beiden Erweiterungen belegt Version 1.18.
Erfasst sind ebenfalls libxml2 2.14.6, libxslt 1.1.43 und zlib 1.3.2.
[Binärhashes und Quellen](../licenses/embedded-sources.json) stimmen mit den im
originalen lxml-sdist hinterlegten Archivhashes überein. Dieses sdist enthält
`buildlibxml.py`, `patch_lxml_deplibs.py` und den libxslt-Backportpatch.
Unbekannte lxml-Binärhashes sperren den Build. Die statische Einbettung verlangt
mehr als eine Lizenzdatei: Empfänger müssen eine geänderte iconv einbinden können.

Rebuild/Relink auf separatem Rechner, niemals im produktiven Helfer: Quellen aus
dem geprüften Archiv entpacken, die vier nativen Archive in lxmls `libs/`
Downloadverzeichnis legen; bei Änderungen deren Hashprüfung im eigenen Fork
bewusst aktualisieren. Compiler, Make, Python-Header und Setuptools bereitstellen.
Aus dem lxml-Quellverzeichnis:

```sh
STATIC_DEPS=true LIBICONV_VERSION=1.18 LIBXML2_VERSION=2.14.6 \
LIBXSLT_VERSION=1.1.43 ZLIB_VERSION=1.3.2 CFLAGS="-O2 -fPIC" \
python setup.py bdist_wheel
```

`buildlibxml.py` baut die lokalen Quellen mit `--disable-shared` und wendet den
mitgelieferten libxslt-Patch an. Die vollständigen erzeugten C-Quellen sind im
sdist vorhanden; Empfänger sind nicht auf unveränderliche proprietäre Objekte
angewiesen. Für vollständig netzlose Wiederholung auch die Verzeichnisabfrage
in `http_find_latest_version_directory` auf das bereits festgelegte lokale
Cache-Verzeichnis beschränken; die Dateihashprüfung selbst bleibt erhalten.
Den eigenen Wheel-Build in einem eigenen Helferimage installieren;
keine Signatur-/Installationsschlüssel nötig. Der bereitgestellte Rebuildpfad
ist auch unabhängig geprüft: isolierter lokaler Compilercontainer, `network=none`,
geändertes `_libiconv_version=0x7e01` im Original-Quellcode, kompletter nativer
Rebuild und Neuinstallation des Wheels. Ein frischer Interpreter bestätigt
den geänderten Exportwert und erfolgreiches XML-Parsing. Test-Wheel-SHA256:
`299ad1acf61e5eac62c04088123d718f33e14f1de8b2cfa7ee182c418908f6c7`.
Dies ist ein privater Änderungs-/Relink-Test, kein Release-Wheel oder Eingriff
in den Kandidaten. Die Distributionsfreigabe bleibt getrennt und gesperrt.

## Quellenbereitstellung und Grenzen

`scripts/source_bundle.py` erzeugt privat ein deterministisches, SHA256-indexiertes
Archiv und verifiziert alle erwarteten Quellen gegen die tatsächliche
`inventory.json`. Weder Repository noch Laufzeitimage müssen die über 300 MB
OS-Quellen enthalten. Vor der ersten neuen öffentlichen Image-Verteilung muss
**dasselbe geprüfte Archiv** als versionierter Release-Asset anonym abrufbar sein.
`publication.py` prüft URL, Archivhash, jeden Payload und Inventarzugehörigkeit.
Keine Veröffentlichung wurde vorgenommen; reine Vorbereitung ersetzt die
anschließende Freigabe und tatsächliche Bereitstellung nicht.

Debian-Snapshot-SHA1 dient nur als Dateiadresse; entscheidend sind SHA256 aus den
Quelldateibeschreibungen. Deren Signaturschlüssel wurden nicht unabhängig
validiert. Die Prüfung belegt Hashkonsistenz mit offiziellen Distributionen,
keinen eigenständigen Supply-Chain-Sicherheitsaudit. Veröffentlichung bleibt
an realen Doctor, Quellmaterialprüfung, Betreiberfreigabe und exakten Digest gebunden.

## Vollständige Komponentenliste

Die nachfolgenden Einträge sind eine überprüfbare Bestandsliste des lokalen
Prüfbaus. Originalnotices/Hashes bleiben im Inventar; die SPDX-Kurzformen sind
keine erschöpfende Lizenzierung verschachtelter Bestandteile. Abweichungen eines
abschließenden Kandidaten sind erneut zu bewerten, nicht stillschweigend freigegeben.

### Python (110 Distributionen)

| Name | Version im Pr?fbau | Lizenz / erg?nzender Nachweis |
| --- | --- | --- |
| akkudoktor-eos | 0.0.0 | Apache-2.0 |
| annotated-doc | 0.0.5 | MIT |
| annotated-types | 0.8.0 | MIT |
| anyio | 4.15.1 | MIT |
| astral | 3.2 | Apache-2.0 |
| babel | 2.18.0 | BSD-3-Clause |
| beautifulsoup4 | 4.15.0 | MIT License |
| bokeh | 3.9.2 | BSD-3-Clause |
| cachebox | 6.2.8 | MIT |
| certifi | 2026.10.23 | MPL-2.0; exaktes sdist erhalten |
| cffi | 2.1.1 | MIT-0 |
| charset-normalizer | 3.5.2 | MIT |
| click | 8.5.0 | BSD-3-Clause |
| contourpy | 1.3.3 | BSD 3-Clause License |
| cycler | 0.12.1 | BSD-3-Clause |
| deap | 1.4.4 | LGPL-3.0; exaktes sdist erhalten |
| dnspython | 2.9.1 | ISC |
| email-validator | 2.3.0 | Unlicense |
| eos-pv-helper | 0.1.0 | MIT |
| fastapi | 0.143.3 | MIT |
| fastapi-cli | 0.0.32 | MIT |
| fastcore | 2.2.35 | Apache-2.0 |
| fonttools | 4.68.0 | MIT |
| formulaic | 1.2.2 | MIT |
| googleapis-common-protos | 1.76.0 | Apache-2.0 |
| h11 | 0.16.0 | MIT |
| h5py | 3.16.0 | BSD-3-Clause |
| httpcore | 1.0.9 | BSD-3-Clause |
| httpcore2 | 2.16.0 | BSD-3-Clause |
| httptools | 0.9.0 | MIT |
| httpx | 0.28.1 | BSD-3-Clause |
| httpx2 | 2.16.0 | BSD-3-Clause |
| idna | 3.20 | BSD-3-Clause |
| interface_meta | 2.0.1 | MIT |
| itsdangerous | 2.2.0 | BSD-3-Clause |
| Jinja2 | 3.1.6 | BSD-3-Clause |
| kiwisolver | 1.5.1 | BSD-3-Clause |
| linkify-it-py | 2.2.0 | MIT |
| lmdb | 3.0.0 | OLDAP-2.8 |
| loguru | 0.7.3 | MIT; exaktes sdist erhalten |
| lxml | 6.1.3 | BSD-3-Clause; libiconv LGPL-2.1-or-later |
| markdown-it-py | 4.2.0 | MIT |
| MarkupSafe | 3.0.4 | BSD-3-Clause |
| matplotlib | 3.11.2 | Matplotlib/PSF-derived + font notices |
| mdit-py-plugins | 0.6.1 | MIT |
| mdurl | 0.1.2 | MIT |
| mistlefoot | 0.0.13 | Apache-2.0 |
| mistletoe | 1.6.0 | MIT |
| monsterui | 1.0.47 | Apache-2.0 |
| moocore | 0.3.2 | LGPL-2.1-or-later; exaktes sdist erhalten |
| narwhals | 2.28.0 | MIT |
| numpy | 2.4.6 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| numpydantic | 1.10.0 | MIT |
| oauthlib | 4.0.0 | BSD-3-Clause |
| opentelemetry-api | 1.45.2 | Apache-2.0 |
| opentelemetry-exporter-http-transport | 0.66b2 | Apache-2.0 |
| opentelemetry-exporter-otlp-common | 0.66b2 | Apache-2.0 |
| opentelemetry-exporter-otlp-proto-common | 1.45.2 | Apache-2.0 |
| opentelemetry-exporter-otlp-proto-http | 1.45.2 | Apache-2.0 |
| opentelemetry-proto | 1.45.2 | Apache-2.0 |
| opentelemetry-sdk | 1.45.2 | Apache-2.0 |
| opentelemetry-semantic-conventions | 0.66b2 | Apache-2.0 |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |
| pandas | 3.0.6 | BSD 3-Clause License |
| patsy | 1.0.3 | 2-clause BSD |
| pendulum | 3.3.0 | MIT License |
| pillow | 13.0.0 | MIT-CMU |
| pip | 24.0 | MIT |
| platformdirs | 4.13.5 | MIT |
| protobuf | 7.36.2 | 3-Clause BSD License |
| psutil | 7.2.2 | BSD-3-Clause |
| pvlib | 0.16.1 | BSD-3-Clause |
| pycparser | 3.12 | BSD-3-Clause |
| pydantic | 2.14.1 | MIT |
| pydantic-extra-types | 2.11.2 | MIT |
| pydantic-settings | 2.16.0 | MIT |
| pydantic_core | 2.50.1 | MIT |
| Pygments | 2.21.0 | BSD-2-Clause |
| pyparsing | 3.3.3 | MIT |
| python-dateutil | 3.0.0 | Apache-2.0 OR BSD-3-Clause |
| python-dotenv | 1.2.4 | BSD-3-Clause |
| python-fasthtml | 0.14.13 | Apache-2.0 |
| python-multipart | 0.0.32 | Apache-2.0 |
| pytz | 2026.6 | MIT |
| PyYAML | 6.0.3 | MIT |
| requests | 2.34.2 | Apache-2.0 |
| rich | 15.0.0 | MIT |
| rich-toolkit | 0.20.6 | MIT |
| scipy | 1.17.1 | BSD + vendor/GCC/LGPL notices; exaktes sdist erhalten |
| setuptools | 79.0.1 | MIT + vendor notices |
| shellingham | 1.5.4 | ISC License |
| six | 1.17.0 | MIT |
| soupsieve | 3.0.4 | MIT |
| starlette | 1.10.0 | BSD-3-Clause |
| statsmodels | 0.15.0 | BSD-3-Clause |
| tornado | 6.6 | Apache-2.0 |
| truststore | 0.10.5 | MIT |
| typer | 0.27.3 | MIT |
| typing-inspection | 0.4.4 | MIT |
| typing_extensions | 4.16.0 | PSF-2.0 |
| tzdata | 2025.2 | Apache-2.0 |
| tzfpy | 2.1.1 | MIT + ODbL data + Rust notices; exaktes sdist erhalten |
| urllib3 | 2.8.0 | MIT |
| uvicorn | 0.54.0 | BSD-3-Clause |
| uvloop | 0.23.0 | MIT License |
| watchfiles | 1.3.0 | MIT |
| websockets | 17.3 | BSD-3-Clause |
| wheel | 0.46.3 | MIT |
| wrapt | 2.5.2 | BSD-2-Clause |
| xyzservices | 2026.9.1 | BSD-3-Clause |

### Debian (105 Bin?rpakete, 73 Quellpakete)

License-Tags stammen aus den originalen paketbezogenen Copyright-Dateien, auch
f?r optionale Quellbestandteile. Bei leeren Tags ist der vollst?ndige Text ma?geblich.
Alle hier gelisteten Versionen m?ssen dem exakten Kandidaten entsprechen.

| Paket | Bin?rversion | Quellidentit?t | Lizenzhinweise |
| --- | --- | --- | --- |
| adduser | 3.134 | adduser | GPL-2+ |
| apt | 2.6.1 | apt | BSD-3-clause, Expat, GPL-2, GPL-2+ |
| base-files | 12.4+deb12u15 | base-files | vollst?ndiger Copyright-Text |
| base-passwd | 3.6.1 | base-passwd | GPL-2, public-domain |
| bash | 5.2.15-2+b13 | bash (5.2.15-2) | BSD-4-clause-UC, BSD-4-clause-UC and MIT-like, GFDL-NIV-1.3, GPL-2+, GPL-3+, GPL-3+ with Bison exception, Latex2e, MIT-like, permissive |
| bsdutils | 1:2.38.1-5+deb12u3 | util-linux (2.38.1-5+deb12u3) | BSD-3-clause, BSD-4-clause, BSLA, GPL-2, GPL-2+, GPL-3+, LGPL, LGPL-2+, LGPL-2.1+, LGPL-3+, MIT, public-domain |
| ca-certificates | 20250419~deb12u2 | ca-certificates | GPL-2+, MPL-2.0 |
| coreutils | 9.1-1 | coreutils | BSD-4-clause-UC, FSFULLR, GFDL-NIV-1.3, GPL-3+, GPL-3+ and BSD-4-clause-UC, GPL-3+ and ISC, ISC |
| dash | 0.5.12-2 | dash | BSD-3-Clause, BSD-3-clause, GPL-2+, public-domain |
| debconf | 1.5.82 | debconf | BSD-2-clause |
| debian-archive-keyring | 2023.3+deb12u2 | debian-archive-keyring | vollst?ndiger Copyright-Text |
| debianutils | 5.7-0.5~deb12u1 | debianutils | GPL-2+, SMAIL-GPL, public-domain |
| diffutils | 1:3.8-4 | diffutils | FSFAP, FSFULLR, GFDL-NIV-1.3, GPL-2+, GPL-3+, GPL-3+ and FSFULLR, GPL-3+ with autoconf exception, GPL-3+ with texinfo exception, LGPL-2.0+, LGPL-2.1+, LGPL-3.0+, LGPL-3.0+ or GPL-2+, X11, public-domain |
| dpkg | 1.21.23 | dpkg | BSD-2-clause, GPL-2, GPL-2+, public-domain-s-s-d |
| e2fsprogs | 1.47.0-2+b2 | e2fsprogs (1.47.0-2) | Apache-2, BSD-3-Clause, GPL or MIT-US-export, GPL-2, GPL-2+ with Texinfo exception, ISC, Kazlib, LGPL-2, Latex2e |
| findutils | 4.9.0-4 | findutils | BSD-3-clause, BSD-3-clause and/or GPL-3+, FSFAP, FSFULLR, GFDL-NIV-1.3+, GPL with automake exception, GPL-2+, GPL-2+ with Autoconf-data exception, GPL-3+, GPL-3+ with Autoconf-data exception, GPL-3+ with Bison-2.2 exception, ISC, ISC and/or LGPL-2.1+, LGPL-2+, LGPL-2.1+, LGPL-3, LGPL-3+, X11, public-domain |
| gcc-12-base | 12.2.0-14+deb12u1 | gcc-12 | vollst?ndiger Copyright-Text |
| gpgv | 2.2.40-1.1+deb12u2 | gnupg2 | BSD-3-clause, CC0-1.0, Expat, GPL-3+, GPL-3+ or BSD-3-clause, LGPL-2.1+, LGPL-3+, RFC-Reference, TinySCHEME, permissive |
| grep | 3.8-5 | grep | GPL-3+ |
| gzip | 1.12-1 | gzip | FSF-manpages, GFDL-1.3+-no-invariant, GPL-3+ |
| hostname | 3.23+nmu1 | hostname | GPL-2 |
| init-system-helpers | 1.65.2+deb12u1 | init-system-helpers | BSD-3-clause, GPL-2+ |
| libacl1 | 2.3.1-3 | acl | GPL-2+, LGPL-2+ |
| libapt-pkg6.0 | 2.6.1 | apt | BSD-3-clause, Expat, GPL-2, GPL-2+ |
| libattr1 | 1:2.5.1-4 | attr | GPL-2+, LGPL-2+ |
| libaudit-common | 1:3.0.9-1 | audit | GPL-2, LGPL-2.1 |
| libaudit1 | 1:3.0.9-1 | audit | GPL-2, LGPL-2.1 |
| libblkid1 | 2.38.1-5+deb12u3 | util-linux | BSD-3-clause, BSD-4-clause, BSLA, GPL-2, GPL-2+, GPL-3+, LGPL, LGPL-2+, LGPL-2.1+, LGPL-3+, MIT, public-domain |
| libbz2-1.0 | 1.0.8-5+b1 | bzip2 (1.0.8-5) | BSD-variant, GPL-2 |
| libc-bin | 2.36-9+deb12u14 | glibc | vollst?ndiger Copyright-Text |
| libc6 | 2.36-9+deb12u14 | glibc | vollst?ndiger Copyright-Text |
| libcap-ng0 | 0.8.3-1+b3 | libcap-ng (0.8.3-1) | GPL-2+, GPL-3, LGPL-2.1+ |
| libcap2 | 1:2.66-4+deb12u3+b1 | libcap2 (1:2.66-4+deb12u3) | BSD-3-clause, BSD-3-clause or GPL-2, BSD-3-clause or GPL-2+, GPL-2, GPL-2+ |
| libcom-err2 | 1.47.0-2+b2 | e2fsprogs (1.47.0-2) | Apache-2, BSD-3-Clause, GPL or MIT-US-export, GPL-2, GPL-2+ with Texinfo exception, ISC, Kazlib, LGPL-2, Latex2e |
| libcrypt1 | 1:4.4.33-2 | libxcrypt | vollst?ndiger Copyright-Text |
| libdb5.3 | 5.3.28+dfsg2-1 | db5.3 | Artistic or BSD-3-clause, BSD-3-clause, BSD-3-clause-fjord, GPL, GPL or Artistic, GPL-3, MIT-old, Ms-PL, Sleepycat, Sleepycat and BSD-3-clause, TCL-like, X11, zlib |
| libdebconfclient0 | 0.270 | cdebconf | BSD-2-Clause, BSD-2-clause, GPL-2+ |
| libext2fs2 | 1.47.0-2+b2 | e2fsprogs (1.47.0-2) | Apache-2, BSD-3-Clause, GPL or MIT-US-export, GPL-2, GPL-2+ with Texinfo exception, ISC, Kazlib, LGPL-2, Latex2e |
| libffi8 | 3.4.4-1 | libffi | Expat, GPL, GPL-2+, GPL-3+, MPL-1.1 or GPL-2+ or LGPL-2.1+, X11, public-domain |
| libgcc-s1 | 12.2.0-14+deb12u1 | gcc-12 | vollst?ndiger Copyright-Text |
| libgcrypt20 | 1.10.1-3+deb12u1 | libgcrypt20 | vollst?ndiger Copyright-Text |
| libgdbm6 | 1.23-3 | gdbm | GFDL-NIV-1.3+, GPL-2+, GPL-3+ |
| libgmp10 | 2:6.2.1+dfsg1-1.1 | gmp | GPL-2+, GPL-2+ or LGPL-3+, GPL-3+, GPL-3+ with Bison exception, LGPL-3+ |
| libgnutls30 | 3.7.9-2+deb12u7 | gnutls28 | Apache-2.0, BSD-3-Clause, CC0 license, Expat, GPLv3+, LGPLv2.1+, LGPLv3+_or_GPLv2+, The main library is licensed under GNU Lesser |
| libgpg-error0 | 1.46-1 | libgpg-error | BSD-3-clause, GPL-3+, LGPL-2.1+, LGPL-2.1+ or BSD-3-clause, g10-permissive |
| libgssapi-krb5-2 | 1.20.1-2+deb12u5 | krb5 | vollst?ndiger Copyright-Text |
| libhogweed6 | 3.8.1-2 | nettle | Expat, GAP, GPL-2, GPL-2+, GPL-3+, GPL-3+ with Autoconf exception, LGPL-2+, LGPL-3+, LGPL-3+ or GPL-2+, public-domain |
| libidn2-0 | 2.3.3-1+b1 | libidn2 (2.3.3-1) | GPL-2+, GPL-3+, LGPL-3+, LGPL-3+ or GPL-2+, Unicode |
| libk5crypto3 | 1.20.1-2+deb12u5 | krb5 | vollst?ndiger Copyright-Text |
| libkeyutils1 | 1.6.3-2 | keyutils | GPL-2+, LGPL-2+ |
| libkrb5-3 | 1.20.1-2+deb12u5 | krb5 | vollst?ndiger Copyright-Text |
| libkrb5support0 | 1.20.1-2+deb12u5 | krb5 | vollst?ndiger Copyright-Text |
| liblz4-1 | 1.9.4-1 | lz4 | BSD-2-clause, GPL-2+, GPL-2+ or BSD-2-clause |
| liblzma5 | 5.4.1-1+deb12u2 | xz-utils | Autoconf, GPL-2, GPL-2+, LGPL-2.1+, PD, PD-debian, config-h, noderivs, none, permissive-fsf, permissive-nowarranty, probably-PD |
| libmd0 | 1.0.4-2 | libmd | BSD-2-clause, BSD-2-clause-NetBSD, BSD-3-clause, BSD-3-clause-Aaron-D-Gifford, Beerware, ISC, public-domain-md4, public-domain-md5, public-domain-sha1 |
| libmount1 | 2.38.1-5+deb12u3 | util-linux | BSD-3-clause, BSD-4-clause, BSLA, GPL-2, GPL-2+, GPL-3+, LGPL, LGPL-2+, LGPL-2.1+, LGPL-3+, MIT, public-domain |
| libncursesw6 | 6.4-4 | ncurses | BSD-3-clause, MIT/X11, X11 |
| libnettle8 | 3.8.1-2 | nettle | Expat, GAP, GPL-2, GPL-2+, GPL-3+, GPL-3+ with Autoconf exception, LGPL-2+, LGPL-3+, LGPL-3+ or GPL-2+, public-domain |
| libnsl2 | 1.3.0-2 | libnsl | BSD-3-clause, GPL-2+-autoconf-exception, GPL-2+-libtool-exception, GPL-3+-autoconf-exception, LGPL-2.1, LGPL-2.1+, MIT, permissive-autoconf-m4, permissive-autoconf-m4-no-warranty, permissive-configure, permissive-fsf, permissive-makefile-in |
| libp11-kit0 | 0.24.1-2 | p11-kit | Apache-2.0, BSD-3-Clause, ISC, ISC+IBM, LGPL-2.1+, permissive-like-automake-output, same-as-rest-of-p11kit |
| libpam-modules | 1.5.2-6+deb12u2 | pam | BSD-3-clause or GPL, BSD-tcp_wrappers, Beerware, GPL-2, GPL-2+, GPL-3, GPL-3+ with Bison exception, LGPL-2+, public-domain |
| libpam-modules-bin | 1.5.2-6+deb12u2 | pam | BSD-3-clause or GPL, BSD-tcp_wrappers, Beerware, GPL-2, GPL-2+, GPL-3, GPL-3+ with Bison exception, LGPL-2+, public-domain |
| libpam-runtime | 1.5.2-6+deb12u2 | pam | BSD-3-clause or GPL, BSD-tcp_wrappers, Beerware, GPL-2, GPL-2+, GPL-3, GPL-3+ with Bison exception, LGPL-2+, public-domain |
| libpam0g | 1.5.2-6+deb12u2 | pam | BSD-3-clause or GPL, BSD-tcp_wrappers, Beerware, GPL-2, GPL-2+, GPL-3, GPL-3+ with Bison exception, LGPL-2+, public-domain |
| libpcre2-8-0 | 10.42-1+deb12u2 | pcre2 | BSD-2-clause, BSD-3-clause, BSD-3-clause-Cambridge with BINARY LIBRARY-LIKE PACKAGES exception, X11, public-domain |
| libreadline8 | 8.2-1.3 | readline | GFDL-NIV-1.3+, GPL-2+, GPL-3, GPL-3+, ISC-no-attribution |
| libseccomp2 | 2.5.4-1+deb12u1 | libseccomp | LGPL-2.1 |
| libselinux1 | 3.4-1+b6 | libselinux (3.4-1) | vollst?ndiger Copyright-Text |
| libsemanage-common | 3.4-1 | libsemanage | vollst?ndiger Copyright-Text |
| libsemanage2 | 3.4-1+b5 | libsemanage (3.4-1) | vollst?ndiger Copyright-Text |
| libsepol2 | 3.4-2.1 | libsepol | GPL-2, GPL-2+, LGPL-2.1+, Zlib |
| libsmartcols1 | 2.38.1-5+deb12u3 | util-linux | BSD-3-clause, BSD-4-clause, BSLA, GPL-2, GPL-2+, GPL-3+, LGPL, LGPL-2+, LGPL-2.1+, LGPL-3+, MIT, public-domain |
| libsqlite3-0 | 3.40.1-2+deb12u2 | sqlite3 | GPL-2+, public-domain |
| libss2 | 1.47.0-2+b2 | e2fsprogs (1.47.0-2) | Apache-2, BSD-3-Clause, GPL or MIT-US-export, GPL-2, GPL-2+ with Texinfo exception, ISC, Kazlib, LGPL-2, Latex2e |
| libssl3 | 3.0.22-1~deb12u2 | openssl | Apache-2.0, Artistic, Artistic or GPL-1+, GPL-1+ |
| libstdc++6 | 12.2.0-14+deb12u1 | gcc-12 | vollst?ndiger Copyright-Text |
| libsystemd0 | 252.39-1~deb12u2 | systemd | CC0-1.0, Expat, GPL-2 with Linux-syscall-note exception, GPL-2+, LGPL-2.1+, public-domain |
| libtasn1-6 | 4.19.0-2+deb12u1 | libtasn1-6 | vollst?ndiger Copyright-Text |
| libtinfo6 | 6.4-4 | ncurses | BSD-3-clause, MIT/X11, X11 |
| libtirpc-common | 1.3.3+ds-1 | libtirpc |  BSD-2-Clause, BSD-3-Clause, BSD-4-Clause, LGPL-2.1+, PERMISSIVE, __AUTO_PERMISSIVE__, BSD-3-Clause, GPL-2 |
| libtirpc3 | 1.3.3+ds-1 | libtirpc |  BSD-2-Clause, BSD-3-Clause, BSD-4-Clause, LGPL-2.1+, PERMISSIVE, __AUTO_PERMISSIVE__, BSD-3-Clause, GPL-2 |
| libudev1 | 252.39-1~deb12u2 | systemd | CC0-1.0, Expat, GPL-2 with Linux-syscall-note exception, GPL-2+, LGPL-2.1+, public-domain |
| libunistring2 | 1.0-2 | libunistring | FreeSoftware, GFDL-1.2+, GPL-2+, GPL-2+ with distribution exception, GPL-3+, GPL-3+ or GFDL-1.2+, LGPL-3+, LGPL-3+ or GPL-2+, MIT |
| libuuid1 | 2.38.1-5+deb12u3 | util-linux | BSD-3-clause, BSD-4-clause, BSLA, GPL-2, GPL-2+, GPL-3+, LGPL, LGPL-2+, LGPL-2.1+, LGPL-3+, MIT, public-domain |
| libxxhash0 | 0.8.1-1 | xxhash | BSD-2-clause, GPL-2 |
| libzstd1 | 1.5.4+dfsg2-5 | libzstd | BSD-3-clause, BSD-3-clause or GPL-2, Expat, GPL-2, zlib |
| login | 1:4.13+dfsg1-1+deb12u2 | shadow | BSD-3-clause, GPL-1, GPL-2+, public-domain |
| logsave | 1.47.0-2+b2 | e2fsprogs (1.47.0-2) | Apache-2, BSD-3-Clause, GPL or MIT-US-export, GPL-2, GPL-2+ with Texinfo exception, ISC, Kazlib, LGPL-2, Latex2e |
| mawk | 1.3.4.20200120-3.1 | mawk | CC-BY-3.0, GPL-2, X11 |
| mount | 2.38.1-5+deb12u3 | util-linux | BSD-3-clause, BSD-4-clause, BSLA, GPL-2, GPL-2+, GPL-3+, LGPL, LGPL-2+, LGPL-2.1+, LGPL-3+, MIT, public-domain |
| ncurses-base | 6.4-4 | ncurses | BSD-3-clause, MIT/X11, X11 |
| ncurses-bin | 6.4-4 | ncurses | BSD-3-clause, MIT/X11, X11 |
| netbase | 6.4 | netbase | GPL-2 |
| openssl | 3.0.22-1~deb12u2 | openssl | Apache-2.0, Artistic, Artistic or GPL-1+, GPL-1+ |
| passwd | 1:4.13+dfsg1-1+deb12u2 | shadow | BSD-3-clause, GPL-1, GPL-2+, public-domain |
| perl-base | 5.36.0-7+deb12u4 | perl |  CC0-1.0, Artistic, Artistic or GPL-1+ or Artistic-dist, Artistic-2, Artistic-dist, BSD-3-clause, BSD-3-clause-GENERIC, BSD-3-clause-with-weird-numbering, BSD-4-clause-POWERDOG, BZIP, DONT-CHANGE-THE-GPL, Expat, Expat or GPL-1+ or Artistic, GPL-1+, GPL-1+ or Artistic, GPL-1+ or Artistic or Artistic-dist, GPL-1+ or Artistic, and BSD-3-clause-GENERIC, GPL-1+ or Artistic, and BSD-4-clause-POWERDOG, GPL-1+ or Artistic, and Expat, GPL-1+ or Artistic, and Unicode, GPL-2+, GPL-2+ or Artistic, GPL-3+-WITH-BISON-EXCEPTION, HSIEH-BSD, HSIEH-DERIVATIVE, LGPL-2.1, REGCOMP, REGCOMP, and GPL-1+ or Artistic, RRA-KEEP-THIS-NOTICE, SDBM-PUBLIC-DOMAIN, TEXT-TABS, Unicode, ZLIB |
| readline-common | 8.2-1.3 | readline | GFDL-NIV-1.3+, GPL-2+, GPL-3, GPL-3+, ISC-no-attribution |
| sed | 4.9-1+deb12u1 | sed | BSD-4-clause-UC, BSL-1, GFDL-NIV-1.3+, GPL-3+, GPL-3+ and ISC, ISC, X11, pcre |
| sysvinit-utils | 3.06-4 | sysvinit | GPL-2.0, GPL-2.0+, GPL-3.0 |
| tar | 1.34+dfsg-1.2+deb12u1 | tar | GPL-2+, GPL-3+, GPL-3+ with Bison exception, LGPL-3+ |
| tzdata | 2026e-0+deb12u1 | tzdata | public-domain |
| usr-is-merged | 37~deb12u1 | usrmerge | GPL-2+ |
| util-linux | 2.38.1-5+deb12u3 | util-linux | BSD-3-clause, BSD-4-clause, BSLA, GPL-2, GPL-2+, GPL-3+, LGPL, LGPL-2+, LGPL-2.1+, LGPL-3+, MIT, public-domain |
| util-linux-extra | 2.38.1-5+deb12u3 | util-linux | BSD-3-clause, BSD-4-clause, BSLA, GPL-2, GPL-2+, GPL-3+, LGPL, LGPL-2+, LGPL-2.1+, LGPL-3+, MIT, public-domain |
| zlib1g | 1:1.2.13.dfsg-1 | zlib | Zlib |
