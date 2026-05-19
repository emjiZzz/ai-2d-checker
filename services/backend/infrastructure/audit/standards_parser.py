import re
from pathlib import Path
from typing import Any, Dict, List, Tuple
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
        else:
            raise ValueError(f"Unsupported standard file extension: {ext}. Only PDF, TXT, and Markdown are supported.")

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
