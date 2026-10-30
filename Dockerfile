FROM python:3.12-slim
WORKDIR /app
COPY . .
ENV PYTHONUNBUFFERED=1
EXPOSE 7860
# zero third-party dependencies; set the DASHSCOPE_API_KEY environment variable at runtime
CMD ["python", "web_server.py"]
