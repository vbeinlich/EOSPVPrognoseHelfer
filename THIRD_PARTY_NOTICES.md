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

Before a stable release, review the exact candidate inventory, nested/vendor
notices and corresponding-source obligations, including bundled native runtimes
and base-OS libraries. The inventory does not discharge those obligations by
itself. Keep this a release gate; do not describe the entire container as MIT.
In particular, SciPy's license identifies bundled GCC runtime libraries under
GPL-3.0 with GCC Runtime Library Exception and **libquadmath under LGPL-2.1-or-later**.
The SciPy source archive alone does not provide libquadmath's corresponding GCC
source. Identifying/preserving the exact bundled build's corresponding source
and satisfying its distribution terms remains an explicit stable-release blocker.
Debian source versions are available from the recorded `dpkg-status`; the pinned
base-image source and rebuild instructions are in the Docker Official Images
[`python` repository](https://github.com/docker-library/python). Do not strip the
original installed notices when slimming an image.

Primary license texts and requirements:
[Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0),
[LGPL-3.0](https://www.gnu.org/licenses/lgpl-3.0.html),
[LGPL-2.1](https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html).
