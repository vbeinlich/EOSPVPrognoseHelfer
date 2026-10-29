FROM python:3.11-slim-bookworm@sha256:94a8fee35252d06ab75856f15f12c7bae67b10e8a6da93c7fded82b2610926cd AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 DRY_RUN=true
WORKDIR /app
COPY pyproject.toml LICENSE README.md THIRD_PARTY_NOTICES.md ./
COPY src ./src
COPY scripts/license_inventory.py /app/scripts/license_inventory.py
COPY licenses /app/licenses
RUN pip install --no-cache-dir . && useradd --uid 10001 --create-home helper \
    && mkdir /output && chown helper:helper /output \
    && python scripts/license_inventory.py --output /usr/share/eos-pv-helper/licenses
USER 10001:10001
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=2 \
  CMD ["python", "-m", "eos_pv_helper", "health"]
ENTRYPOINT ["python", "-m", "eos_pv_helper"]
CMD ["run"]

FROM runtime AS test
USER root
RUN pip install --no-cache-dir '.[test]'
COPY tests ./tests
COPY templates ./templates
COPY scripts ./scripts
COPY config.example.toml ./
COPY .github/workflows ./.github/workflows
COPY docs/GENETIC_ACCEPTANCE.json ./docs/GENETIC_ACCEPTANCE.json
HEALTHCHECK NONE
ENTRYPOINT ["pytest"]
CMD ["-q", "/app/tests"]

FROM runtime AS normalizer

FROM runtime AS eos-source
USER root
ARG EOS_REF=8a8cd43a1915668927eda5504b7de039c2e762b4
RUN pip install --no-cache-dir \
    "https://github.com/Akkudoktor-EOS/EOS/archive/${EOS_REF}.tar.gz" \
    && mkdir -p /opt/eos && python -c \
    "import urllib.request; urllib.request.urlretrieve('https://github.com/Akkudoktor-EOS/EOS/archive/${EOS_REF}.tar.gz', '/tmp/eos.tar.gz')" \
    && tar -xzf /tmp/eos.tar.gz --strip-components=1 -C /opt/eos
RUN python scripts/license_inventory.py --output /usr/share/eos-pv-helper/licenses --eos /opt/eos
ENV PYTHONPATH=/opt/eos/src OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
USER 10001:10001
