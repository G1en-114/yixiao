FROM python:3.12-slim
WORKDIR /app
COPY . .
ENV PYTHONUNBUFFERED=1
EXPOSE 7860
# 零第三方依赖；运行时配置 DASHSCOPE_API_KEY 环境变量
CMD ["python", "web_server.py"]
