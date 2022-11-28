FROM python:3.11-slim-bullseye
RUN echo "deb http://security.debian.org/debian-security bullseye-security main contrib non-free" >> /etc/apt/sources.list
RUN apt-get update && apt-get upgrade -y
# RUN apt-get -y install cargo #sec vulns
RUN apt-get -y install g++ 
RUN apt-get -y install python3-dev
RUN apt-get -y install libpq-dev
RUN apt-get -y install nano
RUN apt-get -y install curl
RUN curl https://sh.rustup.rs -sSf | sh -s -- -y --profile minimal
WORKDIR /usr/src/app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
#sec vulns
RUN apt remove -y python3-dev
RUN apt remove -y libtiff5
RUN apt remove -y libsqlite3-0
RUN apt remove -y libpq-dev # Makes libpq5 autoremovable, but that is still a PG runtime requirement
RUN apt-get -y install libpq5 # Still need this, running to mark as manual install so it is not auto removed
RUN apt remove -y curl
RUN apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false
RUN rm -rf /var/lib/apt/lists/*
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]