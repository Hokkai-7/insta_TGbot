# Dockerfile
FROM python:3.12-slim

# Установка ffmpeg (критически важно для yt-dlp и ffprobe)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Создаем пользователя без root-прав (жесткое требование безопасности Hugging Face Spaces)
RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH"
WORKDIR /home/user/app

# Копируем зависимости и устанавливаем их
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем основной код
COPY --chown=user main.py .

# Запуск
CMD ["python", "main.py"]