"""
spark.py
~~~~~~~~

Module containing helper function for use with Apache Spark
"""
import os
import json
from typing import Optional, List, Dict, Tuple, Any

from dotenv import load_dotenv
from pyspark import SparkFiles
from pyspark.sql import SparkSession
from dependencies import logging
load_dotenv()

def start_spark(app_name: str = 'my_spark_app',
                master: Optional[str] = None,
                jar_packages: Optional[List[str]] = None,
                files: Optional[List[str]] = None,
                spark_config: Optional[Dict[str, Any]] = None) -> Tuple[SparkSession, logging.Log4j, Optional[Dict[str, Any]]]:
    """
    Start Spark session, get Spark logger and load config files.
    """
    if jar_packages is None: jar_packages = []
    if files is None: files = []
    if spark_config is None: spark_config = {}

    # If master is not provided, try to get from environment or default to local[*]
    if master is None:
        master = os.getenv('SPARK_MASTER', 'local[*]')

    spark_builder = (
        SparkSession
        .builder
        .master(master)
        .appName(app_name))

    # Add JVM options for Java 17+ compatibility
    # These are required to handle internal API changes in newer JDKs
    jvm_flags = (
        "--add-opens=java.base/java.lang=ALL-UNNAMED "
        "--add-opens=java.base/java.lang.invoke=ALL-UNNAMED "
        "--add-opens=java.base/java.lang.reflect=ALL-UNNAMED "
        "--add-opens=java.base/java.io=ALL-UNNAMED "
        "--add-opens=java.base/java.net=ALL-UNNAMED "
        "--add-opens=java.base/java.nio=ALL-UNNAMED "
        "--add-opens=java.base/java.util=ALL-UNNAMED "
        "--add-opens=java.base/java.util.concurrent=ALL-UNNAMED "
        "--add-opens=java.base/java.util.concurrent.atomic=ALL-UNNAMED "
        "--add-opens=java.base/sun.nio.ch=ALL-UNNAMED "
        "--add-opens=java.base/sun.nio.cs=ALL-UNNAMED "
        "--add-opens=java.base/sun.security.action=ALL-UNNAMED "
        "--add-opens=java.base/sun.util.calendar=ALL-UNNAMED "
        "--add-opens=java.security.jgss/sun.security.krb5=ALL-UNNAMED"
    )
    spark_builder.config("spark.driver.extraJavaOptions", jvm_flags)
    spark_builder.config("spark.executor.extraJavaOptions", jvm_flags)

    # Add JAR packages
    if jar_packages:
        spark_builder.config('spark.jars.packages', ','.join(jar_packages))

    # Add extra files
    if files:
        spark_builder.config('spark.files', ','.join(files))

    # Add custom Spark configuration
    for key, val in spark_config.items():
        spark_builder.config(key, val)

    # Create session and logger
    spark_sess = spark_builder.getOrCreate()
    spark_logger = logging.Log4j(spark_sess)

    # Load configuration from config.json (if it exists)
    config_dict = _load_config(spark_logger)

    return spark_sess, spark_logger, config_dict


def _load_config(logger: logging.Log4j) -> Optional[Dict[str, Any]]:
    """Private helper to load config from SparkFiles root directory."""
    spark_files_dir = SparkFiles.getRootDirectory()
    config_files = [filename
                    for filename in os.listdir(spark_files_dir)
                    if filename.endswith('config.json')]

    if config_files:
        path_to_config_file = os.path.join(spark_files_dir, config_files[0])
        try:
            with open(path_to_config_file, 'r') as config_file:
                config_dict = json.load(config_file)
            logger.info(f'Loaded config from {config_files[0]}')
            return config_dict
        except Exception as e:
            logger.error(f'Failed to load config file: {str(e)}')
            return None
    else:
        logger.warn('No config file found (*config.json)')
        return None