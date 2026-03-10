# Используем официальный образ Python
FROM python:3.11-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файл с зависимостями
COPY requirements.txt .

# Устанавливаем зависимости. Сборка будет внутри контейнера, где можно писать.
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь код бота
COPY bot.py .

# Команда для запуска
CMD ["python", "bot.py"]
