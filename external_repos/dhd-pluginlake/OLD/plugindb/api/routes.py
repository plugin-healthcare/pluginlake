from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from plugindb.core.security import extract_and_validate_token
from plugindb.core.parquet import save_parquet_file, list_files_and_folders

router = APIRouter()


@router.get("/")
def get_root():
    return {"message": "Hello, World! This is the plugin local datalake API"}


@router.post("/upload", summary="Upload a Parquet file")
async def upload_parquet_file(file: UploadFile = File(...), token: str = Depends(extract_and_validate_token)):
    try:
        # Read the file content efficiently
        file_content = await file.read()

        # Save the file using the helper function
        new_filename = save_parquet_file(file_content, file.filename, PARQUET_DIR)

        return {"detail": "File uploaded successfully", "filename": new_filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/files", summary="List all Parquet files and folders")
def get_files_list(token: str = Depends(extract_and_validate_token)):
    try:
        dir_structure = list_files_and_folders(PARQUET_DIR)
        return dir_structure
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/download/{filename}", summary="Download a Parquet file")
def download_parquet_file(filename: str, token: str = Depends(extract_and_validate_token)):
    file_path = os.path.join(PARQUET_DIR, filename)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(path=file_path, filename=filename, media_type="application/octet-stream")
