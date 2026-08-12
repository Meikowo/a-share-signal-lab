import pandas as pd

from assl.signals.divergence import confirmed_pivots, find_divergence


def test_pivot_is_not_visible_until_right_window_exists():
    values = pd.Series([10, 9, 8, 9, 10])

    assert confirmed_pivots(values.iloc[:3], "low", window=2) == ()
    assert confirmed_pivots(values, "low", window=2) == (2,)


def test_bottom_divergence_requires_second_price_low_and_higher_dif():
    low = [10.0] * 17
    low[4] = 8.0
    low[12] = 7.9
    dif = [0.0] * 17
    dif[4] = -1.0
    dif[12] = -0.4
    hist = [0.0] * 17
    hist[4] = -1.5
    hist[12] = -0.6
    frame = pd.DataFrame({"low": low, "high": low, "dif": dif, "macd_hist": hist})

    result = find_divergence(frame, "bottom", lookback=60)

    assert result is not None
    assert result.confirmed is True
    assert (result.first_index, result.second_index) == (4, 12)
    assert result.second_price <= result.first_price * 1.01
    assert result.second_indicator > result.first_indicator


def test_top_divergence_is_symmetric_and_uses_confirmed_highs():
    high = [10.0] * 17
    high[4] = 12.0
    high[12] = 12.2
    dif = [0.0] * 17
    dif[4] = 1.0
    dif[12] = 0.5
    frame = pd.DataFrame(
        {"low": high, "high": high, "dif": dif, "macd_hist": dif}
    )

    result = find_divergence(frame, "top", lookback=60)

    assert result is not None
    assert (result.first_index, result.second_index) == (4, 12)
    assert result.second_price >= result.first_price
    assert result.second_indicator < result.first_indicator


def test_divergence_rejects_pivots_more_than_30_sessions_apart():
    low = [10.0] * 45
    low[3] = 8.0
    low[38] = 7.9
    dif = [0.0] * 45
    dif[3] = -1.0
    dif[38] = -0.4
    frame = pd.DataFrame({"low": low, "high": low, "dif": dif, "macd_hist": dif})

    assert find_divergence(frame, "bottom", lookback=60) is None
