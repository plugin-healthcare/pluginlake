from pathlib import Path

import cbsodata
import dagster as dg
from dagster_polars import PolarsParquetIOManager


root = Path(__file__).parent.parent.parent.parent


class CBSResource(dg.ConfigurableResource):
    get_info = cbsodata.get_info
    get_data = cbsodata.get_data


@dg.definitions
def resources() -> dg.Definitions:
    return dg.Definitions(
        resources={
            "cbs": CBSResource,
            "cbs_polars_parquet_io_manager": PolarsParquetIOManager(
                base_dir=(root / "datalake" / "cbs").as_posix()
            ),
            "vocab_polars_parquet_io_manager": PolarsParquetIOManager(
                base_dir=(root / "datalake" / "vocabularies").as_posix()
            ),
        }
    )
