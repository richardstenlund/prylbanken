FROM python:3.13-alpine
WORKDIR /app
RUN addgroup -S app && adduser -S app -G app && mkdir /data /backups && chown app:app /data /backups
COPY --chown=app:app server.py catalog.py proxmox_catalog.py backend.py library.py workbench.py registry.py linkcheck.py ./
COPY --chown=app:app public ./public
ENV DATA_DIR=/data BACKUP_DIR=/backups PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER app
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health',timeout=3)"
CMD ["python", "server.py"]
