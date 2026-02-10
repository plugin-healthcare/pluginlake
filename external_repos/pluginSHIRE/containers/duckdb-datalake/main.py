from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Security
import duckdb
import io
from fastapi.security.api_key import APIKeyHeader
import polars as pl
import uuid
import os

app = FastAPI()
PARQUET_DIR = '/home/yannick/code/pluginSHIRE/tests/containers/duckdb-datalake/test-db'  # If you still want to save files

# Security setup
API_KEY = "your-secure-api-key"
api_key_header = APIKeyHeader(name="X-API-Key")

async def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API Key")

# Initialize DuckDB connection
con = duckdb.connect(database=':memory:')

@app.post("/upload")
async def upload_parquet_file(file: UploadFile = File(...), api_key: str = Depends(verify_api_key)):
    try:
        # read file content as bytes
        file_content = await file.read()
        buffer = io.BytesIO(file_content)
        
        df = pl.read_parquet(buffer)

        # TODO: add meta data and do checks on the data

        filename = f"{uuid.uuid4()}_{file.filename}"
        file_path = os.path.join(PARQUET_DIR, filename)
        df.write_parquet(file_path)
        if not os.path.exists(file_path):
            raise HTTPException(status_code=500, detail="Failed to save the file.")

        return {"detail": "Parquet data uploaded and processed successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/tables")
async def get_tables(api_key: str = Depends(verify_api_key)):
    "returns a folder structure as dictionary from the parquet files"
    tables = {}
    

    for file in os.listdir(PARQUET_DIR):
        if file.endswith(".parquet"):
            table_name = file.split(".")[0]
            tables[table_name] = table_name

@app.get("/query")
async def query_duckdb(query: str, api_key: str = Depends(verify_api_key)):
    try:
        result = con.execute(query).fetchdf()
        return result.to_parquet()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))