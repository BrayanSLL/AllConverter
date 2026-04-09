from fastapi import APIRouter

from api.converters import dwg_svg

router = APIRouter()
router.include_router(
    dwg_svg.router,
    prefix="/converters/dwg-to-svg",
    tags=["DWG to SVG"],
)
