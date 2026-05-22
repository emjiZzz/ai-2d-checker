import re
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional
from pypdf import PdfReader
from ...logger import logger
from ...core.security import validate_sandboxed_path

class StandardsParser:
    """
    Safely parses PDF, TXT, and Markdown files inside a sandboxed storage root.
    Extracts structured chunks, metadata, and handles basic format validation.
    """

    @staticmethod
    def parse_file(file_path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Parses a Grounding Standard document based on its extension.
        Returns:
            chunks: List of dictionaries, each containing:
                - content (str)
                - section_header (str or None)
                - metadata (dict with page number, line offsets, etc.)
            metadata: Dict with global properties (author, title, page_count).
        """
        # 1. Enforce sandbox traversal limits
        canonical_path = validate_sandboxed_path(file_path)
        
        ext = canonical_path.suffix.lower()
        if ext == ".pdf":
            return StandardsParser._parse_pdf(canonical_path)
        elif ext in (".txt", ".md"):
            return StandardsParser._parse_text_or_markdown(canonical_path)
        elif ext in (".xlsx", ".xls"):
            return StandardsParser._parse_excel(canonical_path)
        else:
            raise ValueError(f"Unsupported standard file extension: {ext}. Only PDF, TXT, Excel, and Markdown are supported.")

    @staticmethod
    def _get_color_category(rgb_val: str) -> Optional[str]:
        """
        Classifies a cell background hexadecimal color into standard warning/success signals.
        """
        if not rgb_val or not isinstance(rgb_val, str):
            return None
            
        val = rgb_val.upper().lstrip("#")
        if len(val) == 8:
            val = val[2:] # Strip alpha channel
            
        if val in ("00000000", "FFFFFFFF", "000000", "FFFFFF", ""):
            return None
            
        try:
            r = int(val[0:2], 16)
            g = int(val[2:4], 16)
            b = int(val[4:6], 16)
            
            # Danger Red/Pink highlights (e.g. FFC7CE, F8D7DA, EF4444)
            if r > 200 and g < 155 and b < 155:
                return "RED WARNING"
            if r > 220 and g > 180 and b > 180 and r > g + 15 and r > b + 15:
                return "RED WARNING"
                
            # Success Green/Mint highlights (e.g. C6EFCE, D4EDDA, 10B981)
            if g > 170 and r < 210 and b < 210:
                return "GREEN SUCCESS"
            if g > 200 and r > 180 and b > 180 and g > r + 10 and g > b + 10:
                return "GREEN SUCCESS"
                
            # Warning Yellow/Amber highlights (e.g. FFF2CC, FFF3CD, F59E0B)
            if r > 210 and g > 190:
                if b < 170 or (b < 215 and r > b + 30 and g > b + 20):
                    return "YELLOW ATTENTION"
        except (ValueError, IndexError):
            pass
        return None

    @staticmethod
    def _parse_excel(file_path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        logger.info(f"Parsing Style-Aware Excel Engineering Standard: {file_path.name}")
        chunks: List[Dict[str, Any]] = []
        global_metadata: Dict[str, Any] = {
            "title": file_path.stem,
            "page_count": 1
        }
        
        try:
            import openpyxl
            # Load workbook in data_only mode to get calculated values, not raw formulas
            wb = openpyxl.load_workbook(file_path, data_only=True)
            global_metadata["page_count"] = len(wb.sheetnames)
            
            for sheet_name in wb.sheetnames:
                sheet = wb[sheet_name]
                current_chunk = []
                
                # Iterate actual cell objects to extract text, fonts, and background fill highlights
                for row_idx, row in enumerate(sheet.iter_rows(), start=1):
                    row_data = []
                    row_styles = set()
                    
                    for cell in row:
                        if cell.value is not None:
                            val_str = str(cell.value).strip()
                            if val_str:
                                # Apply markdown bold tags if cell font is bold
                                if cell.font and cell.font.bold:
                                    val_str = f"**{val_str}**"
                                    
                                row_data.append(val_str)
                                
                                # Check background solid colors
                                if cell.fill and cell.fill.fill_type == "solid":
                                    color_rgb = getattr(cell.fill.start_color, "rgb", None)
                                    color_cat = StandardsParser._get_color_category(color_rgb)
                                    if color_cat:
                                        row_styles.add(color_cat)
                                        
                    if row_data:
                        content_line = " | ".join(row_data)
                        
                        # Prepend semantic highlights based on dominant cell background colors
                        if "RED WARNING" in row_styles:
                            content_line = f"[INCORRECT / DANGER FLAG] {content_line}"
                        elif "GREEN SUCCESS" in row_styles:
                            content_line = f"[CORRECT / STANDARDS COMPLIANT] {content_line}"
                        elif "YELLOW ATTENTION" in row_styles:
                            content_line = f"[IMPORTANT / ATTENTION REQUIRED] {content_line}"
                            
                        current_chunk.append(content_line)
                        
                        # Chunk roughly every 10 rows
                        if len(current_chunk) >= 10:
                            chunk_text = "\n".join(current_chunk)
                            chunks.append({
                                "content": chunk_text,
                                "section_header": f"Sheet: {sheet_name}",
                                "metadata": {"sheet": sheet_name, "row_end": row_idx, "char_count": len(chunk_text)}
                            })
                            current_chunk = []
                
                # Flush remaining lines in the sheet
                if current_chunk:
                    chunk_text = "\n".join(current_chunk)
                    chunks.append({
                        "content": chunk_text,
                        "section_header": f"Sheet: {sheet_name}",
                        "metadata": {"sheet": sheet_name, "char_count": len(chunk_text)}
                    })
                    
        except Exception as e:
            logger.error(f"Error parsing Excel Standard file {file_path.name}: {str(e)}")
            raise ValueError(f"Failed to read and parse Excel file: {str(e)}")
            
        return chunks, global_metadata

    @staticmethod
    def _parse_pdf(file_path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        logger.info(f"Parsing PDF Engineering Standard: {file_path.name}")
        chunks: List[Dict[str, Any]] = []
        global_metadata: Dict[str, Any] = {}

        try:
            reader = PdfReader(str(file_path))
            global_metadata["page_count"] = len(reader.pages)
            
            # Extract basic PDF info
            if reader.metadata:
                global_metadata["title"] = reader.metadata.title or file_path.stem
                global_metadata["author"] = reader.metadata.author or "Unknown"
                global_metadata["creator"] = reader.metadata.creator or "Unknown"
            else:
                global_metadata["title"] = file_path.stem

            # Extract page-by-page text
            for page_idx, page in enumerate(reader.pages):
                text = page.extract_text()
                if not text:
                    continue

                # Segment text on page by paragraphs or structural lines
                paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
                
                # If paragraph split didn't yield much, try line splits
                if len(paragraphs) <= 1:
                    paragraphs = [p.strip() for p in text.split("\n") if len(p.strip()) > 30]

                # Process each paragraph as a chunk or merge short ones
                current_chunk = ""
                section_header = None

                for p in paragraphs:
                    # Detect headers (lines that are all caps or have section numbering like 1.1, 2.0)
                    header_match = re.match(r"^([A-Z0-9\.\s]{3,40})$|^(\d+\.\d+[\s\w\-]+)$", p)
                    if header_match:
                        section_header = p
                        continue

                    if len(current_chunk) + len(p) < 800:
                        current_chunk += "\n" + p if current_chunk else p
                    else:
                        if current_chunk:
                            chunks.append({
                                "content": current_chunk.strip(),
                                "section_header": section_header,
                                "metadata": {"page_number": page_idx + 1, "char_count": len(current_chunk)}
                            })
                        current_chunk = p

                if current_chunk:
                    chunks.append({
                        "content": current_chunk.strip(),
                        "section_header": section_header,
                        "metadata": {"page_number": page_idx + 1, "char_count": len(current_chunk)}
                    })

        except Exception as e:
            logger.error(f"Error parsing PDF Standard file {file_path.name}: {str(e)}")
            raise ValueError(f"Failed to read and parse PDF file structure: {str(e)}")

        return chunks, global_metadata

    @staticmethod
    def _parse_text_or_markdown(file_path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        logger.info(f"Parsing Text/Markdown Engineering Standard: {file_path.name}")
        chunks: List[Dict[str, Any]] = []
        global_metadata: Dict[str, Any] = {
            "title": file_path.stem,
            "page_count": 1
        }

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            # Split by headers (Markdown style # or capital sections)
            lines = content.splitlines()
            current_chunk = []
            section_header = "General"
            line_start = 1

            for line_idx, line in enumerate(lines):
                line_stripped = line.strip()
                # Markdown headers or numbered section headers
                if line_stripped.startswith("#") or re.match(r"^\d+\.\d+\s+[A-Z]", line_stripped):
                    # Save existing chunk
                    if current_chunk:
                        chunk_text = "\n".join(current_chunk).strip()
                        if chunk_text:
                            chunks.append({
                                "content": chunk_text,
                                "section_header": section_header,
                                "metadata": {"line_start": line_start, "line_end": line_idx, "char_count": len(chunk_text)}
                            })
                    current_chunk = []
                    section_header = line_stripped.lstrip("#").strip()
                    line_start = line_idx + 1
                    continue

                current_chunk.append(line)
                
                # Auto-chunking if block size gets large (approx 1000 characters)
                chunk_len = sum(len(l) for l in current_chunk)
                if chunk_len >= 1000:
                    chunk_text = "\n".join(current_chunk).strip()
                    chunks.append({
                        "content": chunk_text,
                        "section_header": section_header,
                        "metadata": {"line_start": line_start, "line_end": line_idx + 1, "char_count": len(chunk_text)}
                    })
                    current_chunk = []
                    line_start = line_idx + 2

            if current_chunk:
                chunk_text = "\n".join(current_chunk).strip()
                if chunk_text:
                    chunks.append({
                        "content": chunk_text,
                        "section_header": section_header,
                        "metadata": {"line_start": line_start, "line_end": len(lines), "char_count": len(chunk_text)}
                    })

        except Exception as e:
            logger.error(f"Error parsing Text/Markdown Standard file {file_path.name}: {str(e)}")
            raise ValueError(f"Failed to read and parse Text/Markdown file: {str(e)}")

        return chunks, global_metadata
