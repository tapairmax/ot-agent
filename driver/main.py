"""
The main entrypoint for the driver. The driver will poll for new configurations and schedule
executions of monitoring and tuning pipeline.
"""

import argparse
import logging
import sys

from apscheduler.schedulers.background import BlockingScheduler

from driver.driver_config_builder import DriverConfigBuilder, Overrides
from driver.pipeline import (
    schedule_or_update_job,
    DB_LEVEL_MONITOR_JOB_ID,
    TABLE_LEVEL_MONITOR_JOB_ID,
)

# Setup the scheduler that will poll for new configs and run the core pipeline
scheduler = BlockingScheduler()


def _get_args(myargs) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Provide driver configuration")
    parser.add_argument(
        "--log-verbosity",
        type=str,
        default="INFO",
        help="Logging level, DEBUG,INFO,WARNING, etc.",
    )
    parser.add_argument(
        "--config",
        type=str,
        help="Path to configuration file.",
        required=True
    )
    parser.add_argument(
        "--aws-region",
        type=str,
        default="INFO",
        help="aws region, eg: us-east-2",
        required=True
    )
    parser.add_argument(
        "--db-identifier",
        type=str,
        help="AWS rds database identifier",
        required=True
    )
    parser.add_argument(
        "--db-username",
        type=str,
        help="Username used for db connection",
        required=True
    )
    parser.add_argument(
        "--db-password",
        type=str,
        help="Password used for db connection",
        required=True
    )
    parser.add_argument(
        "--api-key",
        type=str,
        help="API key used to identify OtterTune user",
        required=True
    )
    parser.add_argument(
        "--db-key",
        type=str,
        help="Key used to identify database to OtterTune",
        required=True
    )
    parser.add_argument(
        "--organization-id",
        type=str,
        help="Organization Id in Ottertune",
        required=True
    )
    parser.add_argument(
        "--disable-table-level-stats",
        type=str,
        default="False",
        help="Whether to collect stats for table level analysis or not.",
    )
    '''Arguments to provide when RDS is not used or available (AWS region set to none)'''
    parser.add_argument(
        "--db-host",
        type=str,
        help="Database hostname used when AWS region is none",
    )
    parser.add_argument(
        "--db-port",
        type=int,
        help="Database port number used when AWS region is none",
    )
    parser.add_argument(
        "--db-version",
        type=str,
        help="Database version used when AWS region is none",
    )
    parser.add_argument(
        "--db-type",
        type=str,
        default="undef",
        help="Database type (mysql or postgres) used when AWS region is none",
    )
    
    '''Override arguments normaly set in config file'''
    parser.add_argument(
        "--override-monitor-interval",
        type=int,
        help="Override file setting for how often to collect new data (in seconds)",
    )
    parser.add_argument(
        "--override-server-url",
        type=str,
        help="Override file setting for endpoint to post observation data",
    )
    parser.add_argument(
        "--override-num-table-to-collect-stats",
        type=int,
        help="Override file setting for how many tables to collect table level stats",
    )
    parser.add_argument(
        "--override-table-level-monitor-interval",
        type=int,
        help="Override file setting for how often to collect table level data (in seconds)",
    )

    return parser.parse_args(args=myargs)


def schedule_db_level_monitor_job(config) -> None:
    """
    The outer polling loop for the driver
    """
    schedule_or_update_job(scheduler, config, DB_LEVEL_MONITOR_JOB_ID)

def schedule_table_level_monitor_job(config) -> None:
    """
    The polling loop for table level statistics
    """
    schedule_or_update_job(scheduler, config, TABLE_LEVEL_MONITOR_JOB_ID)


def get_config(args):
    """
    Build configuration from file, command line overrides, rds info,
    """
    config_builder = DriverConfigBuilder(args.aws_region)
    overrides = Overrides(
        monitor_interval=args.override_monitor_interval,
        server_url=args.override_server_url,
        num_table_to_collect_stats=args.override_num_table_to_collect_stats,
        table_level_monitor_interval=args.override_table_level_monitor_interval,
    )

    config_builder.from_file(args.config)\
                  .from_overrides(overrides)\
                  .from_rds(args.db_identifier)\
                  .from_cloudwatch_metrics(args.db_identifier)\
                  .from_command_line(args)\
                  .from_env_vars()\
                  .from_overrides(overrides)

    config = config_builder.get_config()

    return config

def _run_from_namespace(args: argparse.Namespace):
    loglevel = args.log_verbosity
    numeric_level = getattr(logging, loglevel.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"Invalid log level: {loglevel}")
    logging.basicConfig(level=numeric_level)

    config = get_config(args)

    schedule_db_level_monitor_job(config)
    if not config.disable_table_level_stats:
        schedule_table_level_monitor_job(config)
    scheduler.start()

    
def run(argslist=[]) -> None:
    """
    The main entrypoint for the driver
    """
    if len(argslist) == 0:
        args = _get_args(sys.argv[1:])
    else:
        args = _get_args(argslist)
        
    _run_from_namespace(args)


if __name__ == "__main__":
    run()
