import os
import platform
import shutil
import subprocess
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
    """Convert DWG or DXF bytes to an SVG string."""
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
        if suffix == ".dwg":
            svg = _dwg_to_svg(tmp_path, warnings)
        else:
            doc = _load_dxf(tmp_path, warnings)
            svg = _render_to_svg(doc)
        return ConversionResult(svg_content=svg, warnings=warnings)
    finally:
        os.unlink(tmp_path)


def _dwg_to_svg(dwg_path: str, warnings: list[str]) -> str:
    """Convert a DWG file to SVG.

    Strategy 1 — ODA File Converter (cross-platform, best quality):
        ezdxf.addons.odafc reads DWG → DXF in-memory, then we render to SVG.

    Strategy 2 — LibreCAD (Linux/macOS fallback):
        librecad dxf2pdf -a  →  PyMuPDF PDF → SVG.

    If neither tool is available a ConversionError is raised with
    clear installation instructions.
    """
    # --- Strategy 1: ODA File Converter ---
    try:
        from ezdxf.addons import odafc
        if odafc.is_installed():
            doc = odafc.readfile(dwg_path)
            return _render_to_svg(doc)
    except Exception:
        pass  # ODA not installed or failed — try next strategy

    # --- Strategy 2: LibreCAD (subprocess) ---
    if shutil.which("librecad") is not None:
        return _dwg_to_svg_via_librecad(dwg_path, warnings)

    # --- Nothing available ---
    raise ConversionError(
        "Aucun outil de conversion DWG n'est installé sur le serveur. "
        "Installez l'un des outils suivants :\n"
        "• ODA File Converter (recommandé, Windows/Linux/macOS) : "
        "https://www.opendesign.com/guestfiles/oda_file_converter\n"
        "• LibreCAD (Linux/macOS) : https://librecad.org\n\n"
        "Alternative : exportez votre fichier en DXF depuis AutoCAD ou FreeCAD "
        "et uploadez le fichier .dxf."
    )


def _dwg_to_svg_via_librecad(dwg_path: str, warnings: list[str]) -> str:
    """DWG → PDF via LibreCAD, then PDF → SVG via PyMuPDF.

    LibreCAD writes the PDF next to the input file, so we copy the DWG
    into a dedicated temp directory to keep cleanup tidy.
    """
    work_dir = tempfile.mkdtemp(prefix="allconv_")
    try:
        work_dwg = os.path.join(work_dir, Path(dwg_path).name)
        shutil.copy2(dwg_path, work_dwg)
        expected_pdf = Path(work_dwg).with_suffix(".pdf")

        env = {**os.environ}
        if platform.system() != "Windows":
            env.update({"QT_QPA_PLATFORM": "offscreen", "XDG_RUNTIME_DIR": "/tmp"})

        subprocess.run(
            ["librecad", "dxf2pdf", "-a", work_dwg],
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )

        if not expected_pdf.exists():
            raise ConversionError(
                "LibreCAD n'a pas pu ouvrir le fichier DWG. "
                "Vérifiez que le fichier n'est pas corrompu et qu'il utilise "
                "un format DWG supporté (R2000–R2018)."
            )

        return _pdf_to_svg(str(expected_pdf), warnings)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def _pdf_to_svg(pdf_path: str, warnings: list[str]) -> str:
    """Convert the first page of a PDF to an SVG string using PyMuPDF."""
    import fitz  # PyMuPDF

    doc = fitz.open(pdf_path)
    if doc.page_count == 0:
        raise ConversionError("Le PDF généré est vide.")

    page = doc[0]
    svg = page.get_svg_image(matrix=fitz.Identity)

    if doc.page_count > 1:
        warnings.append(
            f"Le fichier DWG contient {doc.page_count} feuilles ; "
            "seule la première a été convertie."
        )

    return svg


def _load_dxf(path: str, warnings: list[str]):
    """Load a DXF document, with recovery fallback for corrupted files."""
    try:
        return ezdxf.readfile(path)
    except Exception:
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
                f"Impossible de lire le fichier DXF : {recovery_err}"
            ) from recovery_err


def _render_to_svg(doc) -> str:
    """Render the model space of a DXF document to an SVG string."""
    msp = doc.modelspace()
    ctx = RenderContext(doc)

    layout_props = LayoutProperties.from_layout(msp)
    layout_props.set_colors(bg="#FFFFFF", fg="#000000")

    backend = SVGBackend()
    Frontend(ctx, backend).draw_layout(msp, finalize=True, layout_properties=layout_props)

    page = layout.Page(0, 0, layout.Units.mm, layout.Margins.all(5))
    return backend.get_string(page)
