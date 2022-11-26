FROM python:3.11-slim-bullseye
RUN apt update
RUN apt-get -y install cargo 
RUN apt-get -y install libpq-dev 
RUN apt-get -y install g++ 
RUN apt-get -y install python3-dev
WORKDIR /usr/src/app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]