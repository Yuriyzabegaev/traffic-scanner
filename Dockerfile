FROM python:latest

COPY src/main.py /
COPY src/traffic_scanner /traffic_scanner
COPY requirements.txt /

ENV TIMEZONE=3
ENV DATABASE_URL sqlite:///db_test
ENV TELEGRAM_BOT_TOKEN 672100742:AAHStOe9E2ls1EmbL6-JSvHNtvVzeqPDaBU

RUN pip install -r requirements.txt
CMD [ "python", "./main.py" ]