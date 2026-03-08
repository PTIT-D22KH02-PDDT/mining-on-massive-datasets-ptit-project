# FROM spark:4.0.1-java21-python3
# WORKDIR /opt/app
# COPY requirements.txt /opt/app/requirements.txt
# ENV HOME=/tmp
# RUN python3 -m pip install --no-cache-dir -r /opt/app/requirements.txt
# COPY . /opt/app
# ENV PYSPARK_PYTHON=/usr/bin/python3
# CMD ["python3", "/opt/app/main.py"]
FROM spark:4.0.1-java21-python3

USER root

RUN useradd -m -u 1001 sparkuser
RUN pip install kaggle pandas pyarrow boto3
RUN apt update && \
    apt install -y nano && \
    rm -rf /var/lib/apt/lists/*

USER sparkuser
WORKDIR /home/sparkuser