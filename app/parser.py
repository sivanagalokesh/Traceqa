"""CT-200-focused PDF extraction. Uses text extraction first; exposes OCR limitation clearly."""
import hashlib, re
from dataclasses import dataclass, field
from pathlib import Path

HEADING_PATTERNS = [
    re.compile(r'^\s*(\d+(?:\.\d+){0,5})\s*[.)]?\s+(.{2,180}?)\s*$'),
    re.compile(r'^\s*(APPENDIX\s+[A-Z0-9]+\s*[:.-]?\s*.{1,160})\s*$', re.I),
]

@dataclass
class ParsedNode:
    heading: str
    level: int
    body_text: str = ""
    parent_index: int | None = None
    order_index: int = 0
    logical_key: str = ""
    content_hash: str = ""
    children: list = field(default_factory=list)

def sha256(text: str) -> str:
    return hashlib.sha256(re.sub(r'\s+', ' ', text).strip().encode('utf-8')).hexdigest()

def classify_heading(line: str):
    s = line.strip()
    for pat in HEADING_PATTERNS:
        m = pat.match(s)
        if m:
            if len(m.groups()) == 2 and m.group(1)[0].isdigit():
                number, title = m.group(1), m.group(2).strip()
                # Single-number list items (e.g. "1. Normal: ...") are body content,
                # not section headings. In this manual, section titles do not use a colon.
                if '.' not in number and ':' in title:
                    continue
                return number.count('.') + 1, f"{number} {title}".strip()
            return 1, s
    # Common uppercase headings are useful in manuals, but avoid treating long prose as headings.
    letters = [c for c in s if c.isalpha()]
    if 3 <= len(s) <= 90 and letters and sum(c.isupper() for c in letters) / len(letters) > .82 and not s.endswith(('.', ';', ',')):
        return 1, s.title()
    return None

def parse_text(text: str) -> list[ParsedNode]:
    lines = [re.sub(r'\s+', ' ', x).strip() for x in text.splitlines()]
    nodes: list[ParsedNode] = []
    stack: list[int] = []
    body_buffer: list[str] = []
    def flush_body():
        if body_buffer and nodes:
            nodes[-1].body_text = (nodes[-1].body_text + "\n" + "\n".join(body_buffer)).strip()
        elif body_buffer and not nodes:
            nodes.append(ParsedNode("Document introduction", 1, "\n".join(body_buffer), None, 0))
        body_buffer.clear()
    for line in lines:
        if not line:
            continue
        # Page sentinels are extraction metadata, never document headings.
        if re.fullmatch(r'\[\s*PAGE\s+\d+\s*\]', line, re.I):
            continue
        heading = classify_heading(line)
        if heading:
            flush_body()
            level, title = heading
            # Keep the actual numbered depth. If an intermediate number is missing
            # (e.g. 2.1.1.1 with no 2.1.1 heading), attach to the nearest existing
            # ancestor rather than falsifying the section's level.
            while stack and nodes[stack[-1]].level >= level:
                stack.pop()
            parent = stack[-1] if stack else None
            node = ParsedNode(title, level, "", parent, len(nodes))
            nodes.append(node)
            stack.append(len(nodes) - 1)
        else:
            body_buffer.append(line)
    flush_body()
    if not nodes:
        chunks = [text[i:i+1200].strip() for i in range(0, len(text), 1200) if text[i:i+1200].strip()]
        nodes = [ParsedNode("Extracted content", 1, "\n".join(chunks), None, 0)]
    # Parent/child path + occurrence makes duplicate headings distinct and stable within a version.
    occurrences: dict[str, int] = {}
    for i, n in enumerate(nodes):
        parent_path = nodes[n.parent_index].logical_key if n.parent_index is not None else "root"
        base = f"{parent_path}/{re.sub(r'[^a-z0-9]+','-',n.heading.lower()).strip('-')}"
        occurrences[base] = occurrences.get(base, 0) + 1
        n.logical_key = f"{base}#{occurrences[base]}"
        n.content_hash = sha256(n.heading + "\n" + n.body_text)
    return nodes

def _normalize_table_cell(value: object) -> str:
    """Normalize whitespace artifacts in PDF table cells without changing values.

    PDF extraction can insert spaces around numeric range dashes (for example,
    ``0 –299``). Keep range notation compact so exact-value checks and diffs are stable.
    """
    cell = re.sub(r"\s+", " ", str(value or "")).strip()
    cell = re.sub(r"(?<=\d)\s*[–—-]\s*(?=\d)", "–", cell)
    return cell


def _markdown_table(rows: list[list[object]]) -> str:
    """Render a detected PDF table as Markdown while preserving cell boundaries."""
    cleaned = [[_normalize_table_cell(cell) for cell in row] for row in rows]
    cleaned = [row for row in cleaned if any(row)]
    if not cleaned:
        return ""
    width = max(len(row) for row in cleaned)
    cleaned = [row + [""] * (width - len(row)) for row in cleaned]
    header = cleaned[0]
    separator = ["---"] * width
    body = cleaned[1:]
    render = lambda row: "| " + " | ".join(cell.replace("|", "\\|") for cell in row) + " |"
    return "\n".join([render(header), render(separator), *(render(row) for row in body)])


def extract_pdf(path: str | Path) -> tuple[str, str]:
    """Extract selectable PDF text and reconstruct substantial detected tables.

    PyMuPDF's layout blocks keep the table near its original section. Only tables
    with at least four rows and two columns are promoted to Markdown; small
    false-positive fragments from table borders are ignored. Scanned PDFs fall
    back to Tesseract when its OS dependencies are installed.
    """
    try:
        import pymupdf
        document = pymupdf.open(str(path))
        page_texts = []
        detected_table_count = 0
        for page in document:
            table_entries = []
            try:
                for table in page.find_tables().tables:
                    rows = table.extract()
                    if len(rows) >= 4 and rows and max(len(row) for row in rows) >= 2:
                        rendered = _markdown_table(rows)
                        if rendered:
                            x0, y0, x1, y1 = table.bbox
                            table_entries.append((x0, y0, x1, y1, rendered))
            except Exception:
                # Text extraction should still work when table detection fails.
                table_entries = []
            detected_table_count += len(table_entries)
            blocks = []
            for block in page.get_text("blocks", sort=True):
                if len(block) < 5:
                    continue
                x0, y0, x1, y1, raw = block[:5]
                value = str(raw).strip()
                if not value:
                    continue
                # Remove text blocks that belong to a reconstructed table so cells
                # are not duplicated as an unstructured second copy.
                overlap = False
                block_area = max(1.0, (x1 - x0) * (y1 - y0))
                for tx0, ty0, tx1, ty1, _ in table_entries:
                    ix0, iy0, ix1, iy1 = max(x0, tx0), max(y0, ty0), min(x1, tx1), min(y1, ty1)
                    intersection = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
                    if intersection / block_area > 0.25:
                        overlap = True
                        break
                if not overlap:
                    blocks.append((y0, x0, value))
            for x0, y0, x1, y1, rendered in table_entries:
                blocks.append((y0, x0, rendered))
            blocks.sort(key=lambda item: (round(item[0], 1), item[1]))
            page_texts.append("\n".join(value for _, _, value in blocks))
        text = "\n".join(page_texts).strip()
        if text:
            method = "PyMuPDF text + table extraction" if detected_table_count else "PyMuPDF text extraction"
            return text, method
    except Exception as exc:
        # Try pypdf as a secondary selectable-text extractor before OCR.
        try:
            from pypdf import PdfReader
            text = "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages).strip()
            if text:
                return text, "pypdf text extraction (PyMuPDF fallback)"
        except Exception:
            pass
        if not Path(path).exists():
            raise ValueError(f"PDF not found: {path}") from exc
    # OCR fallback is optional because Tesseract/poppler must be installed at OS level.
    try:
        import pytesseract
        from pdf2image import convert_from_path
        pages = convert_from_path(str(path))
        return "\n".join(pytesseract.image_to_string(p) for p in pages), "Tesseract OCR"
    except Exception:
        raise ValueError("This PDF has no extractable text. Install Tesseract OCR and pdf2image (plus Poppler) to process scanned PDFs.")
