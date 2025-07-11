"""Abstract and base classes for load predictions.

Notes:
    - Ensure appropriate API keys or configurations are set up if required by external data sources.
"""

from abc import abstractmethod
from typing import List, Optional

from pydantic import Field

from akkudoktoreos.prediction.predictionabc import PredictionProvider, PredictionRecord


class LoadDataRecord(PredictionRecord):
    """Represents a load data record containing various load attributes at a specific datetime."""

    load_mean: Optional[float] = Field(default=None, description="Predicted load mean value (W).")
    load_std: Optional[float] = Field(
        default=None, description="Predicted load standard deviation (W)."
    )
    load_mean_adjusted: Optional[float] = Field(
        default=None, description="Predicted load mean value adjusted by load measurement (W)."
    )


class LoadProvider(PredictionProvider):
    """Abstract base class for load providers.

    LoadProvider is a thread-safe singleton, ensuring only one instance of this class is created.

    Configuration variables:
        provider (str): Prediction provider for load.

    Attributes:
        hours (int, optional): The number of hours into the future for which predictions are generated.
        historic_hours (int, optional): The number of past hours for which historical data is retained.
        latitude (float, optional): The latitude in degrees, must be within -90 to 90.
        longitude (float, optional): The longitude in degrees, must be within -180 to 180.
        start_datetime (datetime, optional): The starting datetime for predictions, defaults to the current datetime if unspecified.
        end_datetime (datetime, computed): The datetime representing the end of the prediction range,
            calculated based on `start_datetime` and `hours`.
        keep_datetime (datetime, computed): The earliest datetime for retaining historical data, calculated
            based on `start_datetime` and `historic_hours`.
    """

    # overload
    records: List[LoadDataRecord] = Field(
        default_factory=list, description="List of LoadDataRecord records"
    )

    @classmethod
    @abstractmethod
    def provider_id(cls) -> str:
        return "LoadProvider"

    def enabled(self) -> bool:
        return self.provider_id() == self.config.load.provider
