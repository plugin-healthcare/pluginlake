import polars as pl
from plugindb.utils import file_utils as fu
import yaml

class AIOC:
    """class for aioc related datalake functions"""
    def __init__(self, data_path: str, dir_config_path: str):
        self.dir_config = self._import_config(dir_config_path)
        self.data_path = data_path

    def _import_config(self, config_path: str) -> pl.DataFrame:
        """Import the configuration file"""
        config_path = fu.validate_path(config_path)
        with open(config_path) as file:
            config = yaml.safe_load(file)
        return config

    @property
    def import_paths(self) -> dict:
        """Get the import paths from the configuration"""
        return {key: fu.validate_path(Path(self.data_path, self.dir_config["folders"][key]['input'])) for key in self.dir_config["folders"]}

    @property
    def export_paths(self) -> dict:
        """Get the export paths from the configuration"""
        return {key: fu.validate_path(Path(self.data_path, self.dir_config["folders"][key]['output'])) for key in self.dir_config["folders"]}
