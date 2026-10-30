FROM python:3.11-slim-bookworm@sha256:94a8fee35252d06ab75856f15f12c7bae67b10e8a6da93c7fded82b2610926cd
ARG EOS_REF=8a8cd43a1915668927eda5504b7de039c2e762b4
ENV EOS_DIR=/tmp/eos-test EOS_CONFIG_DIR=/tmp/eos-test \
    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MPLBACKEND=Agg \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN pip install --no-cache-dir \
    "https://github.com/Akkudoktor-EOS/EOS/archive/${EOS_REF}.tar.gz"
# The upstream wheel currently omits subpackages. Keep the pinned source tree
# on PYTHONPATH rather than silently testing a different PyPI version.
RUN mkdir -p /opt/eos && python -c \
    "import urllib.request; urllib.request.urlretrieve('https://github.com/Akkudoktor-EOS/EOS/archive/${EOS_REF}.tar.gz', '/tmp/eos.tar.gz')" \
    && tar -xzf /tmp/eos.tar.gz --strip-components=1 -C /opt/eos
ENV PYTHONPATH=/opt/eos/src
COPY pyproject.toml LICENSE README.md THIRD_PARTY_NOTICES.md ./
COPY licenses ./licenses
COPY docs/GENETIC_ACCEPTANCE.json ./docs/GENETIC_ACCEPTANCE.json
COPY src ./src
COPY tests ./tests
COPY templates ./templates
COPY scripts ./scripts
COPY config.example.toml ./
COPY .github/workflows ./.github/workflows
RUN pip install --no-cache-dir '.[test]'
ENTRYPOINT ["pytest"]
CMD ["-q", "tests"]
