FROM python:3.11-slim-bookworm@sha256:94a8fee35252d06ab75856f15f12c7bae67b10e8a6da93c7fded82b2610926cd AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    EOS_DIR=/tmp/eos EOS_CONFIG_DIR=/tmp/eos MPLBACKEND=Agg HOME=/tmp \
    PYTHONPATH=/opt/eos/src
WORKDIR /app
COPY replay-worker/constraints.txt /app/constraints.txt
# Public source acquisition is build-time only. Runtime has no network.
RUN python -c "import urllib.request,hashlib; raw=urllib.request.urlopen('https://github.com/Akkudoktor-EOS/EOS/archive/8a8cd43a1915668927eda5504b7de039c2e762b4.tar.gz',timeout=120).read(); assert hashlib.sha256(raw).hexdigest()=='500975e7ba614db6481e8762b51649dd9e0ad8f226753b7b9fa5cb980f51472e'; open('/tmp/eos.tar.gz','wb').write(raw)" \
    && mkdir -p /opt/eos \
    && tar -xzf /tmp/eos.tar.gz --strip-components=1 -C /opt/eos \
    && pip install --no-cache-dir -c /app/constraints.txt /tmp/eos.tar.gz
COPY pyproject.toml LICENSE README.md THIRD_PARTY_NOTICES.md ./
COPY src ./src
COPY licenses ./licenses
COPY scripts/license_inventory.py scripts/native_sources.py ./scripts/
RUN pip install --no-cache-dir -c /app/constraints.txt . \
    && python scripts/native_sources.py --mapping-only --output /usr/share/eos-pv-helper/licenses/native \
    && python scripts/license_inventory.py --output /usr/share/eos-pv-helper/licenses --eos /opt/eos \
    && python -c "from pathlib import Path; import akkudoktoreos; from eos_pv_helper.economics_native import fingerprint; fingerprint(Path(akkudoktoreos.__path__[0]))" \
    && useradd --uid 10001 --no-create-home replay \
    && mkdir /archive /replays && chown 10001:10001 /replays
LABEL org.opencontainers.image.title="EMS native offline replay worker" \
    org.opencontainers.image.source="https://github.com/vbeinlich/EOSPVPrognoseHelfer" \
    org.eos.native-revision="8a8cd43a1915668927eda5504b7de039c2e762b4"
USER 10001:10001
HEALTHCHECK NONE
ENTRYPOINT ["python", "-B", "-m", "eos_pv_helper.replay_worker"]
CMD ["--watch", "--poll-seconds", "60"]

FROM runtime AS test
USER root
RUN pip install --no-cache-dir -c /app/constraints.txt '.[test]'
COPY tests ./tests
COPY scripts ./scripts
COPY replay-worker ./replay-worker
COPY docs ./docs
COPY .github/workflows ./.github/workflows
COPY deploy ./deploy
COPY templates ./templates
COPY config.example.toml ./
USER 10001:10001
ENV PYTHONPATH=/app/src:/app/scripts:/app/tests:/opt/eos/src
ENTRYPOINT ["python", "-m", "pytest"]
CMD ["-q", "-p", "no:cacheprovider", "tests/test_replay_worker.py", "tests/integration/test_replay_worker_native.py"]
