FROM python:3.11-slim-bullseye
RUN echo "deb http://security.debian.org/debian-security bullseye-security main contrib non-free" >> /etc/apt/sources.list
RUN apt-get update && apt-get upgrade -y
# RUN apt-get -y install cargo 
RUN apt-get -y install curl
RUN curl https://sh.rustup.rs -sSf | sh -s -- -y
RUN apt-get -y install libpq-dev 
RUN apt-get -y install g++ 
RUN apt-get -y install python3-dev
WORKDIR /usr/src/app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN apt remove -y python3.9
RUN apt remove -y libtiff5
RUN apt autoremove -y
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]