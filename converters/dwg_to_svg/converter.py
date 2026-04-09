import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import ezdxf
from ezdxf import recover
from ezdxf.addons.drawing import Frontend, RenderContext, layout
from ezdxf.addons.drawing.properties import LayoutProperties
from ezdxf.addons.drawing.svg import SVGBackend


class ConversionError(Exception):
    """Raised when a file cannot be converted."""


@dataclass
class ConversionResult:
    svg_content: str
    warnings: list[str] = field(default_factory=list)


def convert(file_bytes: bytes, filename: str) -> ConversionResult:
    """Convert DWG or DXF bytes to an SVG string.

    A temporary file is used because ezdxf requires a real path (not a stream)
    for DWG files. The temp file is always cleaned up, even on error.
    """
    suffix = Path(filename).suffix.lower()
    if suffix not in (".dwg", ".dxf"):
        raise ConversionError(
            f"Type de fichier non supporté : '{suffix}'. "
            "Veuillez fournir un fichier .dwg ou .dxf."
        )

    warnings: list[str] = []

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        doc = _load_document(tmp_path, suffix, warnings)
        svg = _render_to_svg(doc)
        return ConversionResult(svg_content=svg, warnings=warnings)
    finally:
        os.unlink(tmp_path)


def _load_document(path: str, suffix: str, warnings: list[str]):
    """Load a DXF document, falling back to recovery mode for corrupted DXF files."""
    try:
        return ezdxf.readfile(path)
    except ezdxf.DXFError as primary_err:
        if suffix == ".dwg":
            raise ConversionError(
                f"Impossible de lire le fichier DWG : {primary_err}. "
                "Seuls les fichiers DWG compatibles DXF sont supportés. "
                "Essayez d'exporter en DXF R2018 depuis AutoCAD."
            ) from primary_err
        # DXF file: attempt recovery
        try:
            doc, auditor = recover.readfile(path)
            if auditor.has_errors:
                warnings.append(
                    f"Fichier récupéré avec {len(auditor.errors)} erreur(s). "
                    "Le résultat peut être incomplet."
                )
            return doc
        except Exception as recovery_err:
            raise ConversionError(
                f"Impossible de lire ou récupérer le fichier DXF : {recovery_err}"
            ) from recovery_err
    except Exception as err:
        raise ConversionError(f"Erreur inattendue à la lecture : {err}") from err


def _render_to_svg(doc) -> str:
    """Render the model space of a DXF document to an SVG string."""
    msp = doc.modelspace()
    ctx = RenderContext(doc)

    layout_props = LayoutProperties.from_layout(msp)
    layout_props.set_colors(bg="#FFFFFF", fg="#000000")

    backend = SVGBackend()
    Frontend(ctx, backend).draw_layout(msp, finalize=True, layout_properties=layout_props)

    # Page with auto-detect size (width=0, height=0) + 5mm margins
    page = layout.Page(0, 0, layout.Units.mm, layout.Margins.all(5))
    return backend.get_string(page)
