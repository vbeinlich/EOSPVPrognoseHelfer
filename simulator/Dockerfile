# Code-only offline service. No EOS runtime, MQTT client or production sync code.
FROM python:3.11-slim-bookworm@sha256:0a310eeecf4e1f5a0743f9a6520c90c88d089c903ca5fd283f501e3a805f5f89
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
WORKDIR /app
COPY simulator/requirements.txt /tmp/simulation-requirements.txt
COPY simulator/.wheels/ /wheels/
RUN --network=none pip install --no-cache-dir --no-index --require-hashes --find-links=/wheels -r /tmp/simulation-requirements.txt
COPY src/ems_maxxicharge/ /app/ems_maxxicharge/
COPY src/eos_pv_helper/__init__.py src/eos_pv_helper/plan_actual.py src/eos_pv_helper/dashboard_view.py /app/eos_pv_helper/
COPY LICENSE THIRD_PARTY_NOTICES.md /app/licenses/
USER 10001:10001
ENTRYPOINT ["python", "-m", "ems_maxxicharge"]
