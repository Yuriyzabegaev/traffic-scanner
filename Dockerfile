FROM python:latest

COPY src/main.py /
COPY src/traffic_scanner /traffic_scanner
COPY requirements.txt /

RUN pip install -r requirements.txt
CMD [ "python", "./main.py" ]