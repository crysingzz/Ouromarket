FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea
COPY src/adaptive_alpha/runner/supervisor.py /runner/supervisor.py
LABEL org.ouromarket.runner.protocol="native-tool-v1"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 0:0
ENTRYPOINT ["python", "-I", "-S", "-B", "/runner/supervisor.py"]
