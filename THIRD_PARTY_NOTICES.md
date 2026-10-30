# Third-party components

The MIT license in `LICENSE` applies to original EOSPVPrognoseHelfer code and
documentation. It does not relicense EOS, Python, Debian, dependencies or data.
The helper has no bundled frontend at this stage.

The `eos-source` image includes the unmodified Akkudoktor EOS source at the commit
pinned in `Dockerfile`, under Apache-2.0. EOS attribution is preserved at
`/usr/share/eos-pv-helper/licenses/upstream-eos/{LICENSE,NOTICE}`; the complete
Apache-2.0 text is in `texts/Apache-2.0.txt`. Source is at `/opt/eos`, with build
instructions and upstream dependencies retained. No EOS source files are patched.

Every image includes `/usr/share/eos-pv-helper/licenses/inventory.json`, recording
the **actually installed** Python versions, metadata, original notice filenames
and hashes. Original wheel notices (including vendored notices, NumPy/SciPy BLAS
and runtime exceptions) are retained in the installed packages and copied there.
Debian copyright texts and installed package/source versions are recorded under
`system/`; Python's own license remains in `/usr/local/lib/python3.11/LICENSE.txt`.
The manifest is an inventory, **not an automatic legal approval** or complete SBOM.

EOS dependencies include DEAP (LGPL-3.0) and moocore (LGPL-2.1-or-later). These are
independently licensed, dynamically imported libraries; the helper imposes no
restriction on replacing them or debugging modifications. The image retains their
exact matching, SHA256-verified PyPI source archives, notices and build sources
under `python/<name>-<version>/`. GPL/LGPL texts are also under `texts/`.
Rebuild from the public Dockerfile to replace a dependency; neither signature
enforcement nor device installation keys are required. Other components can carry
additional notices and exceptions: inspect the **specific image's** manifest.

Some wheels omit license files (observed: loguru 0.7.3, dnspython 2.9.0). The build
preserves full source archives from the same published version and, where needed,
hash-checked original notices from that exact upstream release (provenance in
`texts/upstream-notices.json`) rather than guessing or silently omitting attribution. No forecast API is
contacted by this build-time inventory step.

Before any new public image distribution, review the exact candidate inventory,
nested/vendor notices and corresponding-source obligations. Automatic main,
preview and tag publishing has been disabled. The inventory is not distribution
approval. [Review and coverage](docs/LICENSE_REVIEW.md),
[publication gates](docs/RELEASE_CHECKLIST.md).
In particular, SciPy's license identifies bundled GCC runtime libraries under
GPL-3.0 with GCC Runtime Library Exception and **libquadmath under LGPL-2.1-or-later**.
The SciPy source archive alone does not provide libquadmath's corresponding GCC
source. The three bundled payloads have now been mapped by SHA256, ELF build-id
and identical `.text`, `.rodata`, `.eh_frame` sections to CentOS GCC 4.8.5-44.el7
and AlmaLinux GCC 8.5.0-26.el8_10.alma.1. The exact source RPMs include distributor
patches and `gcc.spec`; [native-sources.json](licenses/native-sources.json) records
the evidence and source hashes. Unknown replacement binaries fail the build.
This mapping does not claim byte-reproducible upstream wheel builds. Wheel
packaging renames/relocates the libraries; the compared executable sections are
unchanged. Sources and rebuild scripts remain under their original licenses.

All 105 installed Debian packages map to 73 exact source packages in
[debian-sources.json](licenses/debian-sources.json). The 235 source files were
downloaded from Debian Snapshot and verified against their `.dsc` SHA256 lists;
this does not claim independently verified Debian signing keys. The pinned
base-image source and rebuild instructions are in the Docker Official Images
[`python` repository](https://github.com/docker-library/python). Do not strip the
original installed notices when slimming an image.

`certifi` (MPL-2.0) retains its exact PyPI source archive, including the editable
certificate material, in addition to notices. `tzfpy` has MIT code **and** an
ODbL-1.0 timezone database. For the audited 2.1.1 wheel/data 2026e,
[data-sources.json](licenses/data-sources.json) identifies the unchanged `tzf-dist`
database and matching `tzf-rs` reader/exporter. Attribution: timezone-boundary-builder
and OpenStreetMap contributors. ODbL and Unicode-3.0 texts are retained in
`licenses/` and the image, alongside the wheel's compiled dependency notices.

`scripts/source_bundle.py` prepares a separate private, hash-indexed archive:
Debian sources, exact GCC source RPMs, the timezone database/reader, Python source
archives, EOS and project source/rebuild instructions. It verifies completeness
against the exact image inventory. Before public distribution this same reviewed
archive must be available anonymously as a versioned release asset; the promotion
tool checks its SHA256 and contents. No source material or image was published
by preparing this change. Do not publish binaries first and promise sources later.

The audited lxml 6.1.3 wheel also embeds libiconv 1.18 (LGPL-2.1-or-later)
inside its `etree` and `objectify` extensions. Their exact hashes and version
symbol are in [embedded-sources.json](licenses/embedded-sources.json). The image
retains lxml's complete source archive, including `buildlibxml.py` and the
libxslt backport patch. The separate source archive includes exact libiconv,
libxml2, libxslt and zlib build sources so recipients can rebuild/relink lxml
with a modified libiconv. No restriction on this modification or debugging is
imposed. [Rebuild procedure](docs/LICENSE_REVIEW.md#lxml-und-statisch-eingebettetes-libiconv).

Primary license texts and requirements:
[Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0),
[LGPL-3.0](https://www.gnu.org/licenses/lgpl-3.0.html),
[LGPL-2.1](https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html).
