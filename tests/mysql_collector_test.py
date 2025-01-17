"""Tests for interacting with Mysql database locally"""
import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, NoReturn, Union, Optional
from unittest.mock import MagicMock, PropertyMock
import pytest
import mysql.connector.connection
from mysql.connector import errorcode
from driver.collector.mysql_collector import MysqlCollector
from driver.exceptions import MysqlCollectorException
from tests.useful_literals import TABLE_LEVEL_MYSQL_COLUMNS

# pylint: disable=missing-function-docstring,too-many-instance-attributes


@dataclass()
class SqlData:
    """
    Used for providing a set of mock data when collector is collecting metrics
    """

    global_status: List[List[Union[int, str]]]
    innodb_metrics: List[List[Union[int, str]]]
    innodb_status: List[List[str]]
    latency_hist: List[List[float]]
    latency_hist_meta: List[List[str]]
    digest_time: List[List[Union[int, str, float]]]
    digest_time_meta: List[List[str]]
    master_status: List[List[Union[int, str]]]
    master_status_meta: List[List[str]]
    replica_status: List[List[Union[int, str]]]
    replica_status_meta: List[List[str]]
    table_level_stats: List[List[Union[int, str]]]
    table_level_stats_meta: List[List[str]]

    def __init__(self) -> None:
        self.global_status = [
            ["Innodb_buffer_pool_reads", 25],
            ["Innodb_buffer_pool_read_requests", 100],
            ["com_select", 1],
            ["com_insert", 1],
            ["com_update", 1],
            ["com_delete", 1],
            ["com_replace", 1],
        ]
        self.innodb_metrics = [["trx_rw_commits", 0]]
        self.innodb_status = [["ndbcluster", "connection", "cluster_node_id=7"]]
        self.latency_hist = [[2, 1, 5, 3, 1, 0.0588]]
        self.latency_hist_meta = [["bucket_number"], ["bucket_timer_low"],
                                  ["bucket_timer_high"], ["count_bucket"],
                                  ["count_bucket_and_lower"], ["bucket_quantile"]]
        self.digest_time = [["abc", 10, 1.5]]
        self.digest_time_meta = [["queryid"], ["calls"], ["avg_time_ms"]]
        self.master_status = [[1307, "test"]]
        self.master_status_meta = [["Position"], ["Binlog_Do_DB"]]
        self.replica_status = [["localhost", 60]]
        self.replica_status_meta = [["Source_Host"], ["Connect_Retry"]]
        self.table_level_stats = [[
            'mysql',
            'time_zone_transition',
            'BASE TABLE',
            'InnoDB',
            'Dynamic',
            119074,
            39,
            4734976,
            0,
            4194304,
        ]]
        self.table_level_stats_meta = [
            ["TABLE_SCHEMA"],
            ["TABLE_NAME"],
            ["TABLE_TYPE"],
            ["ENGINE"],
            ["ROW_FORMAT"],
            ["TABLE_ROWS"],
            ["AVG_ROW_LENGTH"],
            ["DATA_LENGTH"],
            ["INDEX_LENGTH"],
            ["DATA_FREE"],
        ]

    def expected_default_result(self) -> Dict[str, Any]:
        """
        The expected default format of the metrics dictionary based on the data above
        (assuming mysql > 8.0 and that there is master and replica status information)
        """
        return {
            "global": {
                # pyre-ignore[16] we know first element is string
                "global": {x[0].lower(): x[1] for x in self.global_status},
                "innodb_metrics": {"trx_rw_commits": 0},
                "engine": {
                    "innodb_status": "cluster_node_id=7",
                    "master_status": json.dumps(
                        {
                            "Position": 1307,
                            "Binlog_Do_DB": "test",
                        }
                    ),
                    "replica_status": json.dumps(
                        {"Source_Host": "localhost", "Connect_Retry": 60}
                    ),
                },
                "derived": {
                    "buffer_miss_ratio": 25.0,
                    "read_write_ratio": 0.25,
                },
                "performance_schema": {
                    "events_statements_summary_by_digest": json.dumps(
                        [
                            {
                                "queryid": "abc",
                                "calls": 10,
                                "avg_time_ms": 1.5
                            }
                        ]
                    ),
                    "events_statements_histogram_global": json.dumps(
                        [
                            {
                                "bucket_number": 2,
                                "bucket_timer_low": 1,
                                "bucket_timer_high": 5,
                                "count_bucket": 3,
                                "count_bucket_and_lower": 1,
                                "bucket_quantile": 0.0588,
                            }
                        ]
                    )
                },
            },
            "local": None,
        }


class Result:
    def __init__(self) -> None:
        self.value: Optional[List[Any]] = None
        self.meta: List[List[str]] = []


@pytest.fixture(name="mock_conn")
def _mock_conn() -> MagicMock:
    return MagicMock(spec=mysql.connector.connection.MySQLConnection)


def get_sql_api(data: SqlData, result: Result) -> Callable[[str], NoReturn]:
    """
    Used for providing a fake sql endpoint so we can return test data
    """

    def sql_fn(sql: str) -> NoReturn:
        if sql == MysqlCollector.METRICS_SQL:
            result.value = data.global_status
        elif sql == MysqlCollector.METRICS_INNODB_SQL:
            result.value = data.innodb_metrics
        elif sql == MysqlCollector.ENGINE_INNODB_SQL:
            result.value = data.innodb_status
        elif sql == MysqlCollector.METRICS_LATENCY_HIST_SQL:
            result.value = data.latency_hist
            result.meta = data.latency_hist_meta
        elif sql == MysqlCollector.QUERY_DIGEST_TIME:
            result.value = data.digest_time
            result.meta = data.digest_time_meta
        elif sql == MysqlCollector.ENGINE_MASTER_SQL:
            result.value = data.master_status
            result.meta = data.master_status_meta
        elif sql in ("SHOW REPLICA STATUS;", "SHOW SLAVE STATUS;"):
            result.value = data.replica_status
            result.meta = data.replica_status_meta
        elif "information_schema.TABLES" in sql:
            result.value = data.table_level_stats
            result.meta = data.table_level_stats_meta

    return sql_fn


def test_collect_knobs_success(mock_conn: MagicMock) -> NoReturn:
    collector = MysqlCollector(mock_conn, "5.7.3")
    mock_cursor = mock_conn.cursor.return_value
    expected = [["bulk_insert_buffer_size", 5000], ["tmpdir", "/tmp"]]
    mock_cursor.fetchall.return_value = expected
    result = collector.collect_knobs()
    assert result == {
        "global": {"global": dict(expected)},  # pyre-ignore[6] we know size of list
        "local": None,
    }


def test_get_version(mock_conn: MagicMock) -> NoReturn:
    collector = MysqlCollector(mock_conn, "5.7.3")
    version = collector.get_version()
    assert version == "5.7.3"


def test_collect_knobs_sql_failure(mock_conn: MagicMock) -> NoReturn:
    mock_cursor = mock_conn.cursor.return_value
    mock_cursor.fetchall.side_effect = mysql.connector.ProgrammingError("bad query")
    collector = MysqlCollector(mock_conn, "5.7.3")
    with pytest.raises(MysqlCollectorException) as ex:
        collector.collect_knobs()
    assert "Failed to execute sql" in ex.value.message


def test_collect_metrics_success_with_latency_hist(mock_conn: MagicMock) -> NoReturn:
    mock_cursor = mock_conn.cursor.return_value
    data = SqlData()
    res = Result()
    mock_cursor.execute.side_effect = get_sql_api(data, res)
    mock_cursor.fetchall.side_effect = lambda: res.value
    type(mock_cursor).description = PropertyMock(side_effect=lambda: res.meta)
    collector = MysqlCollector(mock_conn, "8.0.0")
    metrics = collector.collect_metrics()
    assert metrics == data.expected_default_result()


def test_collect_metrics_success_no_latency_hist(mock_conn: MagicMock) -> NoReturn:
    mock_cursor = mock_conn.cursor.return_value
    data = SqlData()
    res = Result()
    mock_cursor.execute.side_effect = get_sql_api(data, res)
    mock_cursor.fetchall.side_effect = lambda: res.value
    type(mock_cursor).description = PropertyMock(side_effect=lambda: res.meta)
    collector = MysqlCollector(mock_conn, "7.9.9")
    metrics = collector.collect_metrics()
    result = data.expected_default_result()
    result["global"]["performance_schema"].pop('events_statements_histogram_global')
    assert metrics == result


def test_collect_metrics_success_no_master_status(mock_conn: MagicMock) -> NoReturn:
    mock_cursor = mock_conn.cursor.return_value
    data = SqlData()
    data.master_status = []
    res = Result()
    mock_cursor.execute.side_effect = get_sql_api(data, res)
    mock_cursor.fetchall.side_effect = lambda: res.value
    type(mock_cursor).description = PropertyMock(side_effect=lambda: res.meta)
    collector = MysqlCollector(mock_conn, "8.0.0")
    metrics = collector.collect_metrics()
    result = data.expected_default_result()
    result["global"]["engine"]["master_status"] = ""
    assert metrics == result


def test_collect_metrics_success_no_replica_status(mock_conn: MagicMock) -> NoReturn:
    mock_cursor = mock_conn.cursor.return_value
    data = SqlData()
    data.replica_status = []
    res = Result()
    mock_cursor.execute.side_effect = get_sql_api(data, res)
    mock_cursor.fetchall.side_effect = lambda: res.value
    type(mock_cursor).description = PropertyMock(side_effect=lambda: res.meta)
    collector = MysqlCollector(mock_conn, "8.0.0")
    metrics = collector.collect_metrics()
    result = data.expected_default_result()
    result["global"]["engine"]["replica_status"] = ""
    assert metrics == result


def test_collect_metrics_sql_failure(mock_conn: MagicMock) -> NoReturn:
    mock_cursor = mock_conn.cursor.return_value
    mock_cursor.fetchall.side_effect = mysql.connector.ProgrammingError("bad query")
    collector = MysqlCollector(mock_conn, "5.7.3")
    with pytest.raises(MysqlCollectorException) as ex:
        collector.collect_metrics()
    assert "Failed to execute sql" in ex.value.message


def test_check_permissions_success(mock_conn: MagicMock) -> NoReturn:
    collector = MysqlCollector(mock_conn, "8.0.0")
    assert collector.check_permission() == (True, [], "")


# pyre-ignore[56]
@pytest.mark.parametrize(
    "code",
    [
        errorcode.ER_SPECIFIC_ACCESS_DENIED_ERROR,
        errorcode.ER_ACCESS_DENIED_ERROR,  # cannot infer type w/pytest
        errorcode.ER_TABLEACCESS_DENIED_ERROR,
        errorcode.ER_UNKNOWN_ERROR,
    ],
)
def test_check_permissions_specific_access_denied(
    mock_conn: MagicMock, code: int
) -> NoReturn:
    mock_cursor = mock_conn.cursor.return_value
    mock_cursor.fetchall.side_effect = mysql.connector.Error(errno=code)
    collector = MysqlCollector(mock_conn, "8.0.0")
    success, results, _ = collector.check_permission()
    assert not success
    for info in results:
        assert not info["success"]
        if code in [
            errorcode.ER_SPECIFIC_ACCESS_DENIED_ERROR,
            errorcode.ER_ACCESS_DENIED_ERROR,
            errorcode.ER_TABLEACCESS_DENIED_ERROR,
        ]:
            assert "GRANT" in info["example"]
        else:
            assert "unknown" in info["example"]

def test_collect_table_level_metrics_success(mock_conn: MagicMock) -> NoReturn:
    mock_cursor = mock_conn.cursor.return_value
    data = SqlData()
    res = Result()
    mock_cursor.execute.side_effect = get_sql_api(data, res)
    mock_cursor.fetchall.side_effect = lambda: res.value
    type(mock_cursor).description = PropertyMock(side_effect=lambda: res.meta)
    collector = MysqlCollector(mock_conn, "7.9.9")
    assert collector.collect_table_level_metrics(num_table_to_collect_stats=1) == {
        "information_schema_TABLES": {
            "columns":TABLE_LEVEL_MYSQL_COLUMNS,
            "rows": [
                [
                    'mysql',
                    'time_zone_transition',
                    'BASE TABLE',
                    'InnoDB',
                    'Dynamic',
                    119074,
                    39,
                    4734976,
                    0,
                    4194304,
                ],
            ],
        },
    }

def test_collect_table_level_metrics_failure(mock_conn: MagicMock) -> NoReturn:
    mock_cursor = mock_conn.cursor.return_value
    mock_cursor.fetchall.side_effect = mysql.connector.ProgrammingError("bad query")
    collector = MysqlCollector(mock_conn, "5.7.3")
    with pytest.raises(MysqlCollectorException) as ex:
        collector.collect_table_level_metrics(10)
    assert "Failed to execute sql" in ex.value.message
