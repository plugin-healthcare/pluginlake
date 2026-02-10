import os
import yaml
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime
from typing import Optional
from pluginlake.utils.logger import setup_logger

class DataLakeSetup:
    def __init__(self, config_file: str, db_path: Optional[str] = None):
        self.logger = self.setup_logger()
        self.config_file = config_file
        self.config = self.load_config()
        self.db_path = db_path if db_path else os.getenv('DB_PATH')
        self.folders = []

    def setup_logger(self):
        # get datetime int 
        dt_int = datetime.now().strftime('%Y%m%d%H%M%S')
        print(os.getenv("LOG_PATH"))
        log_file = Path(os.getenv("LOG_PATH"), f'{dt_int}_datalake_setup.log')
        # make logfile if not exists
        log_file.touch(exist_ok=False)
        return setup_logger(log_file, verbose=True)
    
    def load_config(self):
        self.logger.info(f"Loading config from {self.config_file}")
        with open(self.config_file, 'r') as file:
            return yaml.safe_load(file)

    def select_lakes(self, selected_lakes=None):
        
        self.folders = []
        system_folders = self.config.get('system', [])
        self.logger.debug(f"Selecting system folders {system_folders}")
        self.folders.extend(system_folders)

        self.logger.info(f"Selecting lakes: {selected_lakes}")
        lakes = self.config.get('lakes', {})
        if selected_lakes:
            for lake in selected_lakes:
                if lake not in lakes:
                    self.logger.error(f"Lake {lake} not found in config. skipping...")
                else:
                    self.logger.debug(f"Adding folders from lake {lake}")
                    self.folders.extend(lakes[lake])
        print(self.folders)
        return self.folders


    def check_folders(self, raise_error_if_exists=False):
        existing_folders = []
        for folder in self.folders:
            path = Path(self.db_path, folder['path'])
            print("WHY NO WORK", path)
            if os.path.exists(path):
                num_files = len(os.listdir(path))
                print(f"Folder exists: {path} | Files: {num_files}")
                if num_files > 0:
                    existing_folders.append(folder['path'])
            else:
                print(f"Folder does not exist: {path}")
        if existing_folders and raise_error_if_exists:
            raise FileExistsError(f"These non empty folders already exist: {existing_folders}")

    def create_folders(self):
        for folder in self.folders:
            path = Path(self.db_path, folder['path'])
            if not os.path.exists(path):
                os.makedirs(path)
                print(f"Created folder: {path}")
            else:
                print(f"Folder already exists: {path}")

    def setup_pipeline(self, selected_lakes=None, overwrite=False):
        self.select_lakes(selected_lakes)
        self.check_folders(raise_error_if_exists=not overwrite)
        self.create_folders()

if __name__ == '__main__':
    load_dotenv(override=True)
    config_file = f"{os.getenv('CONFIG_PATH')}/lakes-config.yaml"
    print("DB_PATH", os.getenv("DB_PATH"))
    setup = DataLakeSetup(config_file)
    setup.setup_pipeline(selected_lakes=['aioc-v1'], overwrite=False)
