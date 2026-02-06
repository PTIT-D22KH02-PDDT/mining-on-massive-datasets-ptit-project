# Setup Guide

## PySpark helper files

References from this repository: https://github.com/AlexIoannides/pyspark-example-project

## Prerequisites
- JDK 17 (to run Spark)
- Python 3.11+
- Docker , docker-compose installed
## Docker compose file
```yaml
services:
  spark-master:
    image: spark:4.0.1-java21-python3
    container_name: spark-master
    environment:
      - SPARK_MODE=master
      - SPARK_MASTER_HOST=spark-master
    ports:
      - "7077:7077"
      - "8080:8080"
    # Run in foreground to keep container alive and show logs
    command: /opt/spark/bin/spark-class org.apache.spark.deploy.master.Master
    networks:
      - spark-net
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 1g

  spark-worker:
    image: spark:4.0.1-java21-python3
    container_name: spark-worker
    depends_on:
      - spark-master
    environment:
      - SPARK_MODE=worker
      - SPARK_MASTER=spark://spark-master:7077
      - SPARK_WORKER_CORES=2
      - SPARK_WORKER_MEMORY=2g
    volumes:
      - ./:/opt/app:ro
    # Run in foreground to keep container alive
    command: /opt/spark/bin/spark-class org.apache.spark.deploy.worker.Worker spark://spark-master:7077
    networks:
      - spark-net
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 1g

  spark-app:
    build: .
    container_name: spark-app
    depends_on:
      - spark-master
    volumes:
      - ./:/opt/app:ro
    working_dir: /opt/app
    environment:
      - PYSPARK_PYTHON=/usr/bin/python3
      - SPARK_MASTER=spark://spark-master:7077
    networks:
      - spark-net
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 1g

networks:
  spark-net:
    driver: bridge
```

When run project locally, you can comment the spark-app service to run only spark master and worker node
## Create .env file to store secret
Create .env file based on the .env.example file

## Run Project

### 1. Install dependencies
To install dependencies, in the root project directory, run this command:
```bash
pip install -r requirements.txt
```
### 2. Run Spark master and worker nodes

In the root project directory, run this bash command:

```bash
docker compose up -d
```
### 3. Run `main.py` (optional)
Then you can run `main.py` locally or as a service in docker-compose file already