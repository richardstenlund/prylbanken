FROM python:3.13-alpine
WORKDIR /app
RUN addgroup -S app && adduser -S app -G app && mkdir /data && chown app:app /data
COPY --chown=app:app server.py .
COPY --chown=app:app public ./public
ENV DATA_DIR=/data PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER app
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import os,urllib.request; r=urllib.request.Request('http://127.0.0.1:8080/api/items'); import base64; r.add_header('Authorization','Basic '+base64.b64encode(('admin:'+os.environ['APP_PASSWORD']).encode()).decode()); urllib.request.urlopen(r,timeout=3)"
CMD ["python", "server.py"]
