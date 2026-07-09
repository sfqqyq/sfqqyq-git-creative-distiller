FROM python:3.11-slim

WORKDIR /app

RUN sed -i 's#http://deb.debian.org/debian#https://mirrors.aliyun.com/debian#g; s#http://security.debian.org/debian-security#https://mirrors.aliyun.com/debian-security#g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends git nodejs npm fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

RUN npm config set registry https://registry.npmmirror.com \
    && npm install -g @anthropic-ai/claude-code@latest

COPY requirements.txt .
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt

COPY app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
