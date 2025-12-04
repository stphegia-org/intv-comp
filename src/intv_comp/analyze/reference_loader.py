"""
追加資料（参考資料）の読み込みモジュール。

法制審議会の議事録等の追加資料をファイルシステムから読み込み、
LLMに提供するための機能を提供する。
"""
from __future__ import annotations

from pathlib import Path
from typing import List

from intv_comp.logger import logger

# Optional imports for document processing
try:
    from pypdf import PdfReader
    HAS_PDF = True
except ImportError:
    HAS_PDF = False

try:
    from docx import Document
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

try:
    from openpyxl import load_workbook
    HAS_XLSX = True
except ImportError:
    HAS_XLSX = False

try:
    from pptx import Presentation
    HAS_PPTX = True
except ImportError:
    HAS_PPTX = False

try:
    from PIL import Image
    import pytesseract
    HAS_OCR = True
except ImportError:
    HAS_OCR = False


def _extract_text_from_pdf(file_path: Path) -> str:
    """PDFファイルからテキストを抽出する。"""
    if not HAS_PDF:
        logger.warning(f"PDF処理ライブラリが利用できません: {file_path.name}")
        return ""
    
    try:
        reader = PdfReader(file_path)
        text_parts = []
        for page_num, page in enumerate(reader.pages, 1):
            text = page.extract_text()
            if text.strip():
                text_parts.append(f"[ページ {page_num}]\n{text}")
        return "\n\n".join(text_parts)
    except Exception as exc:
        logger.warning(f"PDF読み込みエラー: {file_path.name} - {exc}")
        return ""


def _extract_text_from_docx(file_path: Path) -> str:
    """Wordファイルからテキストを抽出する。"""
    if not HAS_DOCX:
        logger.warning(f"Word処理ライブラリが利用できません: {file_path.name}")
        return ""
    
    try:
        doc = Document(str(file_path))
        paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
        return "\n\n".join(paragraphs)
    except Exception as exc:
        logger.warning(f"Word読み込みエラー: {file_path.name} - {exc}")
        return ""


def _extract_text_from_xlsx(file_path: Path) -> str:
    """Excelファイルからテキストを抽出する。"""
    if not HAS_XLSX:
        logger.warning(f"Excel処理ライブラリが利用できません: {file_path.name}")
        return ""
    
    try:
        wb = load_workbook(file_path, read_only=True, data_only=True)
        text_parts = []
        for sheet_name in wb.sheetnames:
            sheet = wb[sheet_name]
            rows = []
            for row in sheet.iter_rows(values_only=True):
                row_text = "\t".join(str(cell) if cell is not None else "" for cell in row)
                if row_text.strip():
                    rows.append(row_text)
            if rows:
                text_parts.append(f"[シート: {sheet_name}]\n" + "\n".join(rows))
        wb.close()
        return "\n\n".join(text_parts)
    except Exception as exc:
        logger.warning(f"Excel読み込みエラー: {file_path.name} - {exc}")
        return ""


def _extract_text_from_pptx(file_path: Path) -> str:
    """PowerPointファイルからテキストを抽出する。"""
    if not HAS_PPTX:
        logger.warning(f"PowerPoint処理ライブラリが利用できません: {file_path.name}")
        return ""
    
    try:
        prs = Presentation(str(file_path))
        text_parts = []
        for slide_num, slide in enumerate(prs.slides, 1):
            slide_texts = []
            for shape in slide.shapes:
                if hasattr(shape, "text") and shape.text.strip():
                    slide_texts.append(shape.text)
            if slide_texts:
                text_parts.append(f"[スライド {slide_num}]\n" + "\n".join(slide_texts))
        return "\n\n".join(text_parts)
    except Exception as exc:
        logger.warning(f"PowerPoint読み込みエラー: {file_path.name} - {exc}")
        return ""


def _extract_text_from_image(file_path: Path) -> str:
    """画像ファイルからOCRでテキストを抽出する。"""
    if not HAS_OCR:
        logger.warning(f"OCR処理ライブラリが利用できません: {file_path.name}")
        return ""
    
    try:
        image = Image.open(file_path)
        text = str(pytesseract.image_to_string(image, lang='jpn+eng'))
        return text.strip()
    except Exception as exc:
        logger.warning(f"画像OCR処理エラー: {file_path.name} - {exc}")
        return ""


def load_reference_materials(references_dir: Path) -> str:
    """
    指定されたディレクトリから追加資料を読み込み、結合したテキストを返す。

    Args:
        references_dir: 追加資料が格納されているディレクトリのパス

    Returns:
        読み込んだ全ての資料を結合したテキスト。資料がない場合は空文字列。
    """
    if not references_dir.exists():
        logger.info(f"追加資料のディレクトリが存在しません: {references_dir}")
        return ""

    if not references_dir.is_dir():
        logger.warning(f"指定されたパスはディレクトリではありません: {references_dir}")
        return ""

    # サポートされる拡張子と対応する抽出関数
    file_processors = {
        ".txt": lambda p: p.read_text(encoding="utf-8"),
        ".md": lambda p: p.read_text(encoding="utf-8"),
        ".pdf": _extract_text_from_pdf,
        ".docx": _extract_text_from_docx,
        ".xlsx": _extract_text_from_xlsx,
        ".pptx": _extract_text_from_pptx,
        ".jpg": _extract_text_from_image,
        ".jpeg": _extract_text_from_image,
        ".png": _extract_text_from_image,
    }

    # ファイルを収集
    reference_files: List[Path] = []
    for ext in file_processors.keys():
        reference_files.extend(references_dir.glob(f"*{ext}"))

    if not reference_files:
        logger.info(f"追加資料が見つかりませんでした: {references_dir}")
        return ""

    # ファイルを読み込んで結合
    materials: List[str] = []
    for file_path in sorted(reference_files):
        try:
            ext = file_path.suffix.lower()
            processor = file_processors.get(ext)
            
            if processor is None:
                logger.warning(f"未対応のファイル形式です: {file_path.name}")
                continue
            
            content = processor(file_path)
            if content and content.strip():
                materials.append(f"# {file_path.name}\n\n{content}")
                logger.info(f"追加資料を読み込みました: {file_path.name}")
            else:
                logger.warning(f"ファイルからテキストを抽出できませんでした: {file_path.name}")
        except (UnicodeDecodeError, OSError, PermissionError) as exc:
            logger.warning(f"資料の読み込みに失敗しました: {file_path.name} - {exc}")
            continue

    if not materials:
        logger.info("読み込み可能な追加資料がありませんでした")
        return ""

    combined_text = "\n\n---\n\n".join(materials)
    logger.info(f"{len(materials)}件の追加資料を読み込みました")
    return combined_text
