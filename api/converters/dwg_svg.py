from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response

from converters.dwg_to_svg.converter import ConversionError, convert

router = APIRouter()

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


@router.post("/convert")
async def convert_dwg_to_svg(file: UploadFile = File(...)):
    """Accept a .dwg or .dxf upload and return an SVG."""
    contents = await file.read()

    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="Le fichier uploadé est vide.")

    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="Fichier trop grand. Maximum 50 Mo.")

    try:
        result = convert(contents, file.filename or "upload.dxf")
    except ConversionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erreur interne : {exc}")

    headers = {}
    if result.warnings:
        headers["X-Conversion-Warnings"] = "; ".join(result.warnings)

    return Response(
        content=result.svg_content,
        media_type="image/svg+xml",
        headers=headers,
    )
