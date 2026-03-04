FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV FLASK_APP=app.py
ENV DB_PATH=/app/data/portfolio.db

EXPOSE 5000

CMD ["flask", "run", "--host=0.0.0.0", "--port=5000"]
