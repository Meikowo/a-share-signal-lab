from datetime import date

from assl.market.sohu import SohuMarketActivityClient


def test_client_combines_shanghai_and_shenzhen_daily_turnover():
    payloads = {
        "zs_000001": [
            {
                "status": 0,
                "hq": [
                    [
                        "2026-08-21",
                        "3891.18",
                        "3905.20",
                        "1.48",
                        "0.04%",
                        "3883.79",
                        "3912.13",
                        "446895872",
                        "88342352.00",
                        "-",
                    ],
                    [
                        "2026-08-20",
                        "3907.21",
                        "3903.72",
                        "9.30",
                        "0.24%",
                        "3888.10",
                        "3925.06",
                        "506633954",
                        "101856835.32",
                        "-",
                    ],
                ],
            }
        ],
        "zs_399106": [
            {
                "status": 0,
                "hq": [
                    [
                        "2026-08-21",
                        "2516.44",
                        "2539.50",
                        "12.34",
                        "0.49%",
                        "2496.13",
                        "2545.19",
                        "543953920",
                        "99584096.00",
                        "-",
                    ],
                    [
                        "2026-08-20",
                        "2533.26",
                        "2527.16",
                        "19.91",
                        "0.79%",
                        "2510.40",
                        "2548.07",
                        "596570236",
                        "106079488.69",
                        "-",
                    ],
                ],
            }
        ],
    }

    def fetch_json(url, params):
        assert url.startswith("https://q.stock.sohu.com/")
        return payloads[params["code"]]

    client = SohuMarketActivityClient(fetch_json=fetch_json)

    rows = client.fetch_daily(date(2026, 8, 21), count=120)

    assert [row.trade_date for row in rows] == [date(2026, 8, 20), date(2026, 8, 21)]
    assert rows[-1].shanghai_amount == 883_423_520_000.0
    assert rows[-1].shenzhen_amount == 995_840_960_000.0
    assert rows[-1].total_amount == 1_879_264_480_000.0


def test_client_rejects_a_market_date_missing_from_one_exchange():
    def fetch_json(url, params):
        code = params["code"]
        shared = ["2026-08-20", "1", "1", "0", "0%", "1", "1", "1", "20000000", "-"]
        missing_in_shenzhen = [
            "2026-08-21",
            "1",
            "1",
            "0",
            "0%",
            "1",
            "1",
            "1",
            "10000000",
            "-",
        ]
        rows = [shared, missing_in_shenzhen] if code == "zs_000001" else [shared]
        return [{"status": 0, "hq": rows}]

    client = SohuMarketActivityClient(fetch_json=fetch_json)

    try:
        client.fetch_daily(date(2026, 8, 21), count=120)
    except ValueError as error:
        assert "exchange turnover dates do not align" in str(error)
    else:
        raise AssertionError("unaligned exchange dates must be rejected")


def test_client_retries_a_transient_disconnect_before_parsing():
    attempts = []

    def fetch_json(url, params):
        attempts.append(params["code"])
        if len(attempts) == 1:
            raise OSError("remote disconnected")
        return [
            {
                "status": 0,
                "hq": [["2026-08-21", "1", "1", "0", "0%", "1", "1", "1", "10000000", "-"]],
            }
        ]

    delays = []
    client = SohuMarketActivityClient(fetch_json=fetch_json, sleep=delays.append)

    rows = client.fetch_daily(date(2026, 8, 21), count=120)

    assert rows[0].total_amount == 200_000_000_000
    assert attempts == ["zs_000001", "zs_000001", "zs_399106"]
    assert delays == [0.7, 0.25]
