import json
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import pytest
import requests
from loguru import logger

from akkudoktoreos.core.cache import CacheFileStore
from akkudoktoreos.core.ems import get_ems
from akkudoktoreos.prediction.elecpriceakkudoktor import (
    AkkudoktorElecPrice,
    AkkudoktorElecPriceValue,
    ElecPriceAkkudoktor,
)
from akkudoktoreos.prediction.elecpriceenergycharts import (
    ElecPriceEnergyCharts,
    EnergyChartsElecPrice,
)
from akkudoktoreos.utils.datetimeutil import to_datetime

DIR_TESTDATA = Path(__file__).absolute().parent.joinpath("testdata")

FILE_TESTDATA_ELECPRICE_ENERGYCHARTS_JSON = DIR_TESTDATA.joinpath(
    "elecpriceforecast_energycharts.json"
)


@pytest.fixture
def provider(monkeypatch, config_eos):
    """Fixture to create a ElecPriceProvider instance."""
    monkeypatch.setenv("EOS_ELECPRICE__ELECPRICE_PROVIDER", "ElecPriceEnergyCharts")
    config_eos.reset_settings()
    return ElecPriceEnergyCharts()


@pytest.fixture
def sample_energycharts_json():
    """Fixture that returns sample forecast data report."""
    with FILE_TESTDATA_ELECPRICE_ENERGYCHARTS_JSON.open(
        "r", encoding="utf-8", newline=None
    ) as f_res:
        input_data = json.load(f_res)
    return input_data


@pytest.fixture
def cache_store():
    """A pytest fixture that creates a new CacheFileStore instance for testing."""
    return CacheFileStore()


# ------------------------------------------------
# General forecast
# ------------------------------------------------


def test_singleton_instance(provider):
    """Test that ElecPriceForecast behaves as a singleton."""
    another_instance = ElecPriceEnergyCharts()
    assert provider is another_instance


def test_invalid_provider(provider, monkeypatch):
    """Test requesting an unsupported provider."""
    monkeypatch.setenv("EOS_ELECPRICE__ELECPRICE_PROVIDER", "<invalid>")
    provider.config.reset_settings()
    assert not provider.enabled()


# ------------------------------------------------
# Akkudoktor
# ------------------------------------------------


@patch("akkudoktoreos.prediction.elecpriceenergycharts.logger.error")
def test_validate_data_invalid_format(mock_logger, provider):
    """Test validation for invalid Energy-Charts data."""
    invalid_data = '{"invalid": "data"}'
    with pytest.raises(ValueError):
        provider._validate_data(invalid_data)
    mock_logger.assert_called_once_with(mock_logger.call_args[0][0])


@patch("requests.get")
def test_request_forecast(mock_get, provider, sample_energycharts_json):
    """Test requesting forecast from Energy-Charts."""
    # Mock response object
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.content = json.dumps(sample_energycharts_json)
    mock_get.return_value = mock_response

    # Test function
    energy_charts_data = provider._request_forecast()

    assert isinstance(energy_charts_data, EnergyChartsElecPrice)
    assert energy_charts_data.unix_seconds[0] == 1733785200
    assert energy_charts_data.price[0] == 92.85


@patch("requests.get")
def test_update_data(mock_get, provider, sample_energycharts_json, cache_store):
    """Test fetching forecast from Energy-Charts."""
    # Mock response object
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.content = json.dumps(sample_energycharts_json)
    mock_get.return_value = mock_response

    cache_store.clear(clear_all=True)

    # Call the method
    ems_eos = get_ems()
    ems_eos.set_start_datetime(to_datetime("2024-12-11 00:00:00", in_timezone="Europe/Berlin"))
    provider.update_data(force_enable=True, force_update=True)

    # Assert: Verify the result is as expected
    mock_get.assert_called_once()
    assert (
        len(provider) == 73
    )  # we have 48 datasets in the api response, we want to know 48h into the future. The data we get has already 23h into the future so we need only 25h more. 48+25=73

    # Assert we get hours prioce values by resampling
    np_price_array = provider.key_to_array(
        key="elecprice_marketprice_wh",
        start_datetime=provider.start_datetime,
        end_datetime=provider.end_datetime,
    )
    assert len(np_price_array) == provider.total_hours


@patch("requests.get")
def test_update_data_with_incomplete_forecast(mock_get, provider):
    """Test `_update_data` with incomplete or missing forecast data."""
    incomplete_data: dict = {"license_info": "", "unix_seconds": [], "price": [], "unit": "", "deprecated": False}
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.content = json.dumps(incomplete_data)
    mock_get.return_value = mock_response
    logger.info("The following errors are intentional and part of the test.")
    with pytest.raises(ValueError):
        provider._update_data(force_update=True)


@pytest.mark.parametrize(
    "status_code, exception",
    [(400, requests.exceptions.HTTPError), (500, requests.exceptions.HTTPError), (200, None)],
)
@patch("requests.get")
def test_request_forecast_status_codes(
    mock_get, provider, sample_energycharts_json, status_code, exception
):
    """Test handling of various API status codes."""
    mock_response = Mock()
    mock_response.status_code = status_code
    mock_response.content = json.dumps(sample_energycharts_json)
    mock_response.raise_for_status.side_effect = (
        requests.exceptions.HTTPError if exception else None
    )
    mock_get.return_value = mock_response
    if exception:
        with pytest.raises(exception):
            provider._request_forecast()
    else:
        provider._request_forecast()


@patch("akkudoktoreos.core.cache.CacheFileStore")
def test_cache_integration(mock_cache, provider):
    """Test caching of 8-day electricity price data."""
    mock_cache_instance = mock_cache.return_value
    mock_cache_instance.get.return_value = None  # Simulate no cache
    provider._update_data(force_update=True)
    mock_cache_instance.create.assert_called_once()
    mock_cache_instance.get.assert_called_once()


def test_key_to_array_resampling(provider):
    """Test resampling of forecast data to NumPy array."""
    provider.update_data(force_update=True)
    array = provider.key_to_array(
        key="elecprice_marketprice_wh",
        start_datetime=provider.start_datetime,
        end_datetime=provider.end_datetime,
    )
    assert isinstance(array, np.ndarray)
    assert len(array) == provider.total_hours


# ------------------------------------------------
# Development Akkudoktor
# ------------------------------------------------


@pytest.mark.skip(reason="For development only")
def test_akkudoktor_development_forecast_data(provider):
    """Fetch data from real Energy-Charts server."""
    # Preset, as this is usually done by update_data()
    provider.start_datetime = to_datetime("2024-10-26 00:00:00")

    energy_charts_data = provider._request_forecast()

    with FILE_TESTDATA_ELECPRICE_ENERGYCHARTS_JSON.open(
        "w", encoding="utf-8", newline="\n"
    ) as f_out:
        json.dump(energy_charts_data, f_out, indent=4)
