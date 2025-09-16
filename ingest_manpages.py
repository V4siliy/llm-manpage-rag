import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
import os
import random
import re
import shutil
import string
import subprocess
import tarfile
from collections import OrderedDict, Counter
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# --------------------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------------------

VERSION = "6.9"

DEFAULT_URLS = [
    "https://www.kernel.org/pub/linux/docs/man-pages/man-pages-{ver}.tar.xz",
    "https://mirrors.edge.kernel.org/pub/linux/docs/man-pages/man-pages-{ver}.tar.xz",
]

DATA_DIR = Path("data")
RAW_DIR = DATA_DIR / "raw" / f"manpages-{VERSION}"
PARSED_JSON_DIR = DATA_DIR / "parsed" / "json"
PARSED_TEXT_DIR = DATA_DIR / "parsed" / "text"
CHUNKS_DIR = DATA_DIR / "chunks"
EVAL_DIR = DATA_DIR / "eval"
TMP_DIR = DATA_DIR / "tmp"

SOURCE_META = RAW_DIR / "source.json"
CHUNKS_PATH = CHUNKS_DIR / "chunks.jsonl"
ALIASES_PATH = PARSED_JSON_DIR / "aliases.json"
SECTION_HINTS_PATH = PARSED_JSON_DIR / "section_hints.json"
DOC_INDEX_PATH = PARSED_JSON_DIR / "documents.index.jsonl"
DOC_SUMMARY_PATH = PARSED_JSON_DIR / "documents.summary.json"
EVAL_SET_PATH = EVAL_DIR / "eval.jsonl"
QUALITY_REPORT_PATH = EVAL_DIR / "report.json"
RAW_TARBALL_PATH = RAW_DIR / f"man-pages-{VERSION}.tar.xz"

RECOGNIZED_SECTIONS = [
    "NAME",
    "SYNOPSIS",
    "DESCRIPTION",
    "OPTIONS",
    "RETURN VALUE",
    "ERRORS",
    "NOTES",
    "EXAMPLES",
    "SEE ALSO",
    "CONFORMING TO",
    "STANDARDS",
    "BUGS",
    "ENVIRONMENT",
    "FILES",
    "VERSIONS",
    "ATTRIBUTES",
    "COLOPHON",
    "CAVEATS",
    "DIAGNOSTICS",
    "HISTORY",
    "COMPATIBILITY",
    "AVAILABILITY",
    "AUTHOR",
    "COPYRIGHT",
    "EXIT STATUS",
]

SECTION_SYNONYMS = {
    "NAME": ["TITLE"],
    "SYNOPSIS": ["USAGE", "INTERFACE", "PROTOTYPE"],
    "DESCRIPTION": ["DETAILS", "OVERVIEW"],
    "OPTIONS": ["ARGUMENTS", "FLAGS", "PARAMETERS"],
    "RETURN VALUE": ["RETURNS"],
    "ERRORS": ["DIAGNOSTICS", "ERRNO"],
    "NOTES": ["NOTE"],
    "EXAMPLES": ["EXAMPLE"],
    "SEE ALSO": ["SEEALSO", "RELATED"],
    "STANDARDS": ["CONFORMING TO", "CONFORMANCE"],
    "BUGS": ["LIMITATIONS", "ISSUES"],
    "ENVIRONMENT": ["ENV", "ENV VARS", "ENVIRONMENT VARIABLES"],
    "FILES": ["FILE"],
    "VERSIONS": ["VERSION", "HISTORY"],
    "ATTRIBUTES": [],
    "COLOPHON": [],
    "CAVEATS": [],
    "DIAGNOSTICS": [],
    "HISTORY": [],
    "COMPATIBILITY": [],
    "AVAILABILITY": [],
    "AUTHOR": ["AUTHORS", "MAINTAINER"],
    "COPYRIGHT": ["LICENSE"],
    "EXIT STATUS": ["EXITSTATUS"],
}

CHUNK_MAX_TOKENS = 700
CHUNK_TARGET_TOKENS = 550
CHUNK_OVERLAP_TOKENS = 60

MANDOC_CMD = shutil.which("mandoc")

# --------------------------------------------------------------------------------------
# Utilities
# --------------------------------------------------------------------------------------

def log(msg: str) -> None:
    ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

def ensure_dirs() -> None:
    for d in [RAW_DIR, PARSED_JSON_DIR, PARSED_TEXT_DIR, CHUNKS_DIR, EVAL_DIR, TMP_DIR]:
        d.mkdir(parents=True, exist_ok=True)

def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def request_download(url: str, dest: Path) -> None:
    try:
        import requests
    except ImportError:
        raise RuntimeError("requests is required to download the tarball. Please pip install requests.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length", 0))
        downloaded = 0
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = min(100, downloaded * 100 // total)
                        print(f"\rDownloading {url} [{pct}%]", end="", flush=True)
    print("")

def extract_tarball(tar_path: Path, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tar_path, mode="r:*") as tar:
        def is_within_directory(directory: str, target: str) -> bool:
            abs_directory = os.path.abspath(directory)
            abs_target = os.path.abspath(target)
            prefix = os.path.commonpath([abs_directory])
            return os.path.commonpath([abs_directory, abs_target]) == prefix
        def safe_extract(tarobj, path=".", members=None, *, numeric_owner=False):
            for member in tarobj.getmembers():
                member_path = os.path.join(path, member.name)
                if not is_within_directory(path, member_path):
                    raise Exception("Attempted Path Traversal in Tar File")
            tarobj.extractall(path, members, numeric_owner=numeric_owner)
        safe_extract(tar, dest_dir)
        top_levels = {Path(m.name).parts[0] for m in tar.getmembers() if m.name and not m.name.startswith("./")}
        if len(top_levels) == 1:
            root = dest_dir / list(top_levels)[0]
        else:
            root = dest_dir
    return root

def slugify(text: str, max_len: int = 64) -> str:
    text = text.strip().lower()
    text = re.sub(r"[—–]", "-", text)
    text = re.sub(r"\s+", "-", text)
    allowed = set(string.ascii_lowercase + string.digits + "-_")
    text = "".join(ch for ch in text if ch in allowed)
    text = re.sub(r"-{2,}", "-", text)
    return text[:max_len].strip("-_")

def find_mandoc_or_fail() -> str:
    if MANDOC_CMD:
        return MANDOC_CMD
    raise RuntimeError("mandoc not found in PATH. Please install mandoc (system prerequisite).")

def normalize_whitespace_preserve_code(text: str) -> str:
    lines = text.splitlines()
    normalized_lines = []
    in_fence = False
    for line in lines:
        if re.match(r"^```", line):
            in_fence = not in_fence
            normalized_lines.append(line.rstrip())
            continue
        if in_fence or line.startswith("    "):
            normalized_lines.append(line.rstrip())
        else:
            s = re.sub(r"\s+", " ", line.strip())
            normalized_lines.append(s)
    out = "\n".join(normalized_lines)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()

def parse_markdown_sections(md_text: str) -> OrderedDict:
    sections = OrderedDict()
    current = None
    buf: List[str] = []
    for line in md_text.splitlines():
        h = re.match(r"^\s{0,3}#{1,6}\s+([^\n#].*?)\s*$", line)
        if h:
            if current is not None:
                sections[current] = "\n".join(buf).strip()
                buf = []
            current = h.group(1).strip().upper()
            continue
        buf.append(line)
    if current is not None:
        sections[current] = "\n".join(buf).strip()
    ordered = OrderedDict()
    for k, v in sections.items():
        ordered[k] = v
    return ordered

def extract_name_title_aliases_from_name_section(text: str) -> Tuple[Optional[str], Optional[str], List[str]]:
    if not text:
        return None, None, []
    first_line = None
    for ln in text.splitlines():
        s = ln.strip()
        if s:
            first_line = s
            break
    if not first_line:
        return None, None, []
    parts = re.split(r"\s+[-—–]\s+", first_line, maxsplit=1)
    left = parts[0].strip()
    title = parts[1].strip() if len(parts) > 1 else None
    names = [n.strip() for n in re.split(r",\s*", left) if n.strip()]
    canonical = names[0] if names else None
    aliases = names[1:] if len(names) > 1 else []
    return canonical, title, aliases

def detect_section_from_filename(path: Path) -> Optional[str]:
    m = re.search(r"\.(\d[a-z]?)$", path.name)
    if m:
        return m.group(1)
    parent = path.parent.name
    pm = re.match(r"man(\d[a-z]?)$", parent)
    if pm:
        return pm.group(1)
    return None

def tokenize_counter():
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return lambda s: enc.encode(s)
    except Exception:
        return lambda s: re.findall(r"\S+", s)

def split_into_paragraphs_preserve_code(text: str) -> List[Tuple[str, bool]]:
    blocks: List[Tuple[str, bool]] = []
    lines = text.splitlines()
    in_fence = False
    fence_lines: List[str] = []
    para_lines: List[str] = []

    def flush_para():
        nonlocal para_lines
        if para_lines and any(ln.strip() for ln in para_lines):
            blocks.append(("\n".join(para_lines).strip(), False))
        para_lines = []

    def flush_fence():
        nonlocal fence_lines
        if fence_lines:
            blocks.append(("\n".join(fence_lines).rstrip(), True))
        fence_lines = []

    for ln in lines:
        if re.match(r"^```", ln):
            if in_fence:
                fence_lines.append(ln)
                flush_fence()
                in_fence = False
            else:
                flush_para()
                in_fence = True
                fence_lines = [ln]
            continue
        if in_fence:
            fence_lines.append(ln)
            continue
        if ln.startswith("    "):
            flush_para()
            blocks.append((ln.rstrip(), True))
            continue
        if ln.strip() == "":
            flush_para()
        else:
            para_lines.append(ln)
    if in_fence:
        flush_fence()
    else:
        flush_para()
    return blocks

def assemble_chunks_from_blocks(
    doc_id: str,
    page_name: str,
    section_num: str,
    section_name: str,
    blocks: List[Tuple[str, bool]],
    encode_fn,
) -> List[Dict]:
    chunks: List[Dict] = []
    sec_slug = slugify(section_name or "section")
    anchor_base = f"{page_name}-{section_num}-{sec_slug}"
    # Build and emit chunks using paragraph/code blocks, aiming at token target
    buffer: List[str] = []
    buffer_tokens = 0
    seq = 1
    for blk_text, _is_code in blocks:
        blk_text_norm = blk_text.strip()
        if not blk_text_norm:
            continue
        tcount = len(encode_fn(blk_text_norm))
        if (buffer_tokens + tcount) <= CHUNK_TARGET_TOKENS or not buffer:
            buffer.append(blk_text_norm)
            buffer_tokens += tcount
            continue
        # Flush current buffer
        chunk_text = "\n\n".join(buffer).strip()
        if chunk_text:
            anchor = f"{anchor_base}-{seq:02d}"
            chunk_tokens = len(encode_fn(chunk_text))
            chunks.append({
                "document_id": doc_id,
                "section_name": section_name,
                "anchor": anchor,
                "text": chunk_text,
                "token_count": chunk_tokens,
                "see_also_refs": extract_see_also_refs(chunk_text),
                "constants": extract_constants(chunk_text),
            })
            seq += 1
            overlap_text = take_last_tokens_text(chunk_text, encode_fn, CHUNK_OVERLAP_TOKENS)
            buffer = [overlap_text] if overlap_text else []
            buffer_tokens = len(encode_fn(overlap_text)) if overlap_text else 0
        # Add current block after flushing
        buffer.append(blk_text_norm)
        buffer_tokens += tcount

    # Flush the rest
    if buffer:
        chunk_text = "\n\n".join(buffer).strip()
        if chunk_text:
            anchor = f"{anchor_base}-{seq:02d}"
            chunk_tokens = len(encode_fn(chunk_text))
            chunks.append({
                "document_id": doc_id,
                "section_name": section_name,
                "anchor": anchor,
                "text": chunk_text,
                "token_count": chunk_tokens,
                "see_also_refs": extract_see_also_refs(chunk_text),
                "constants": extract_constants(chunk_text),
            })
    return chunks

def take_last_tokens_text(text: str, encode_fn, k: int) -> str:
    if k <= 0:
        return ""
    tokens = encode_fn(text)
    if len(tokens) <= k:
        return text
    words = re.findall(r"\S+|\s+", text)
    kept = []
    count = 0
    for w in reversed(words):
        if re.match(r"\s+", w):
            kept.append(w)
            continue
        t = len(encode_fn(w))
        if count + t > k and count > 0:
            break
        kept.append(w)
        count += t
    return "".join(reversed(kept)).lstrip()

def extract_see_also_refs(text: str) -> List[str]:
    refs = set()
    for m in re.finditer(r"\b([a-zA-Z0-9_+.-]+)\((\d[a-z]?)\)", text):
        refs.add(f"{m.group(1)}({m.group(2)})")
    return sorted(refs)

def extract_constants(text: str) -> List[str]:
    constants = set()
    for tok in re.findall(r"\b[A-Z][A-Z0-9_]{2,}\b", text):
        if tok in {"THE", "AND", "FOR"}:
            continue
        constants.add(tok)
    return sorted(constants)

def build_document_id(page_name: str, section_num: str) -> str:
    return f"man:{VERSION}:{page_name}:{section_num}"

@dataclass
class SubSection:
    subsection_name: str
    raw_text: str
    start_offset: int

@dataclass
class ManDoc:
    document_id: str
    version_tag: str
    page_name: str
    section: str
    title: Optional[str]
    aliases: List[str]
    see_also: List[str]
    source_path: str
    license_ref: Optional[str]
    license_text: Optional[str]
    created_at: str
    name_raw: Optional[str]
    synopsis_raw: Optional[str]
    subsections: List[SubSection]

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["subsections"] = [asdict(s) for s in self.subsections]
        return d

# --------------------------------------------------------------------------------------
# Manpage processing
# --------------------------------------------------------------------------------------

def render_with_mandoc(mandoc_path: str, man_source: Path, fmt: str) -> Optional[str]:
    res = subprocess.run([mandoc_path, "-T", fmt, str(man_source)], capture_output=True, text=True)
    if res.returncode == 0 and res.stdout.strip():
        return res.stdout
    return None

def resolve_so_chain(man_source: Path) -> Tuple[bool, Optional[Path], Optional[Path]]:
    """
    Resolve a chain of .so files to find the final target file.
    Returns (is_so_file, temp_file, working_dir)
    """
    visited = set()  # Prevent infinite loops
    current_file = man_source
    started_with_so = False
    
    # Check if we started with a .so file
    try:
        with open(man_source, 'r') as f:
            first_line = f.readline().strip()
            if first_line.startswith('.so '):
                started_with_so = True
    except:
        pass
    
    if not started_with_so:
        return False, None, None
    
    while True:
        if current_file in visited:
            # Circular reference detected
            return False, None, None
        
        visited.add(current_file)
        
        try:
            with open(current_file, 'r') as f:
                first_line = f.readline().strip()
                if first_line.startswith('.so '):
                    so_path = first_line[4:].strip()  # Remove '.so '
                    
                    # Handle path resolution
                    if '/' in so_path:
                        # Cross-directory reference - try to find the file
                        parts = so_path.split('/')
                        if len(parts) == 2:
                            # Format like "man3/getcwd.3"
                            target_dir = current_file.parent.parent / parts[0]  # Go up one level, then into man3
                            target_file = target_dir / parts[1]
                            if target_file.exists():
                                current_file = target_file
                                continue
                        
                        # Fallback: extract just the filename and look in current directory
                        filename = so_path.split('/')[-1]
                        target_file = current_file.parent / filename
                        if target_file.exists():
                            current_file = target_file
                            continue
                        else:
                            # Target doesn't exist, create temp file with corrected path
                            temp_file = man_source.parent / f".temp_{man_source.name}"
                            with open(temp_file, 'w') as tf:
                                tf.write(f".so {filename}\n")
                            return True, temp_file, man_source.parent
                    else:
                        filename = so_path
                        target_file = current_file.parent / filename
                        if target_file.exists():
                            current_file = target_file
                            continue
                        else:
                            # Target doesn't exist, create temp file with corrected path
                            temp_file = man_source.parent / f".temp_{man_source.name}"
                            with open(temp_file, 'w') as tf:
                                tf.write(f".so {filename}\n")
                            return True, temp_file, man_source.parent
                else:
                    # Not a .so file, we're done - use the final resolved file
                    return True, current_file, current_file.parent
        except:
            break
    
    return False, None, None

def render_markdown_with_mandoc(mandoc_path: str, man_source: Path) -> str:
    # Check if this is a .so file that needs special handling
    is_so_file, temp_file, working_dir = resolve_so_chain(man_source)
    
    # Determine file to use and working directory
    if is_so_file:
        if temp_file:
            # Use the resolved file directly
            file_to_process = temp_file
            working_dir = working_dir
        else:
            # This shouldn't happen with the new logic
            file_to_process = man_source
            working_dir = working_dir
    else:
        working_dir = None
        file_to_process = man_source
    
    md = render_with_mandoc(mandoc_path, man_source, "markdown")
    if md:
        return md
    
    # Try pandoc as fallback for man(7) format files
    pandoc = shutil.which("pandoc")
    if pandoc:
        if working_dir:
            res_pandoc = subprocess.run([pandoc, "-f", "man", "-t", "gfm", file_to_process.name], 
                                      capture_output=True, text=True, cwd=working_dir)
        else:
            res_pandoc = subprocess.run([pandoc, "-f", "man", "-t", "gfm", str(file_to_process)], 
                                      capture_output=True, text=True)
        if res_pandoc.returncode == 0 and res_pandoc.stdout.strip():
            # Clean up temporary file if created
            if temp_file and temp_file.exists() and temp_file != file_to_process:
                temp_file.unlink()
            return res_pandoc.stdout
    
    # Fallback to groff for plain text
    groff = shutil.which("groff")
    if groff:
        if working_dir:
            res2 = subprocess.run([groff, "-T", "utf8", "-man", file_to_process.name], 
                                capture_output=True, text=True, cwd=working_dir)
        else:
            res2 = subprocess.run([groff, "-T", "utf8", "-man", str(file_to_process)], 
                                capture_output=True, text=True)
        if res2.returncode == 0 and res2.stdout.strip():
            # Clean up temporary file if created
            if temp_file and temp_file.exists() and temp_file != file_to_process:
                temp_file.unlink()
            return res2.stdout
    
    # Clean up temporary file if created
    if temp_file and temp_file.exists() and temp_file != file_to_process:
        temp_file.unlink()
    raise RuntimeError(f"Failed to render markdown/text for {man_source} using mandoc, pandoc, or groff")

def render_json_ast_with_mandoc(mandoc_path: str, man_source: Path) -> Optional[str]:
    js = render_with_mandoc(mandoc_path, man_source, "json")
    return js

def parse_and_normalize_page(man_path: Path, out_base_dir: Path) -> Tuple[Optional[ManDoc], Optional[Dict], Optional[str]]:
    mandoc_path = find_mandoc_or_fail()
    try:
        md_text = render_markdown_with_mandoc(mandoc_path, man_path)
    except Exception as e:
        log(f"WARN: markdown render failed for {man_path}: {e}")
        return None, None, None

    md_text = md_text.replace("\r\n", "\n")
    md_text_norm = normalize_whitespace_preserve_code(md_text)
    sections_md = parse_markdown_sections(md_text_norm)

    name_section = sections_md.get("NAME", "")
    canonical, title, aliases = extract_name_title_aliases_from_name_section(name_section)
    section_num = detect_section_from_filename(man_path) or "0"
    # Sanitize canonical name to be filesystem-safe
    if canonical:
        # Replace forward slashes and other problematic characters with underscores
        page_name = re.sub(r'[/\\:*?"<>|]', '_', canonical).strip('_')
    else:
        page_name = man_path.stem.split(".")[0]
    doc_id = build_document_id(page_name, section_num)
    created_at = dt.datetime.utcnow().isoformat() + "Z"

    see_also_raw = sections_md.get("SEE ALSO", "")
    see_also_refs = extract_see_also_refs(see_also_raw)

    # License: try to find in COLOPHON or COPYRIGHT sections
    license_text = None
    license_ref = None
    for key in ["COPYRIGHT", "COLOPHON"]:
        t = sections_md.get(key)
        if t:
            license_text = t[:2000]
            break

    # Build subsections list with offsets
    concatenated = ""
    subsections: List[SubSection] = []
    for sec_name, sec_text in sections_md.items():
        start = len(concatenated)
        subsections.append(SubSection(subsection_name=sec_name, raw_text=sec_text, start_offset=start))
        concatenated += (sec_text + "\n\n")

    doc = ManDoc(
        document_id=doc_id,
        version_tag=VERSION,
        page_name=page_name,
        section=section_num,
        title=title,
        aliases=aliases,
        see_also=see_also_refs,
        source_path=str(man_path),
        license_ref=license_ref,
        license_text=license_text,
        created_at=created_at,
        name_raw=name_section or None,
        synopsis_raw=sections_md.get("SYNOPSIS") or None,
        subsections=subsections,
    )

    # Save JSON AST if available
    ast_json = render_json_ast_with_mandoc(mandoc_path, man_path)
    rel_base = f"{page_name}.{section_num}"
    out_json_ast_path = PARSED_JSON_DIR / f"{rel_base}.ast.json"
    if ast_json:
        try:
            out_json_ast_path.write_text(ast_json, encoding="utf-8")
        except Exception as e:
            log(f"WARN: failed writing AST JSON for {man_path}: {e}")

    # Save normalized markdown text
    out_text_path = PARSED_TEXT_DIR / f"{rel_base}.md"
    try:
        out_text_path.write_text(md_text_norm, encoding="utf-8")
    except Exception as e:
        log(f"WARN: failed writing normalized text for {man_path}: {e}")

    # Save structured doc JSON
    doc_json = doc.to_dict()
    out_doc_path = PARSED_JSON_DIR / f"{rel_base}.json"
    try:
        out_doc_path.write_text(json.dumps(doc_json, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        log(f"WARN: failed writing structured doc for {man_path}: {e}")

    return doc, sections_md, md_text_norm

def discover_man_files(root_dir: Path, limit: Optional[int] = None) -> List[Path]:
    patterns = [
        "**/man[1-9]*/**/*.[1-9]",
        "**/man[1-9]*/**/*.[1-9][a-z]",
    ]
    files: List[Path] = []
    for pat in patterns:
        files.extend([p for p in root_dir.glob(pat) if p.is_file()])
        # Deduplicate and sort deterministically
    uniq = sorted(set(files), key=lambda p: (p.suffix, str(p).lower()))
    if limit is not None:
        uniq = uniq[:limit]
    return uniq

    # --------------------------------------------------------------------------------------
    # Dataset acquisition
    # --------------------------------------------------------------------------------------


def acquire_dataset() -> Path:
    """Download man-pages tarball if needed, extract, and write source metadata."""
    ensure_dirs()
    urls = [u.format(ver=VERSION) for u in DEFAULT_URLS]
    used_url = None

    if RAW_TARBALL_PATH.exists():
        log(f"Tarball already present: {RAW_TARBALL_PATH}")
    else:
        for u in urls:
            try:
                log(f"Downloading tarball from {u}")
                request_download(u, RAW_TARBALL_PATH)
                used_url = u
                break
            except Exception as e:
                log(f"WARN: download failed for {u}: {e}")
        if not RAW_TARBALL_PATH.exists():
            raise RuntimeError("Failed to download tarball from default URLs.")

    sha = compute_sha256(RAW_TARBALL_PATH)

    # Extract (idempotent-ish). Track the extracted root with a marker.
    extracted_marker = RAW_DIR / ".extracted_root"
    if extracted_marker.exists():
        root = Path(extracted_marker.read_text(encoding="utf-8").strip())
        if not root.exists():
            # Re-extract if the root disappeared
            log("Extracted root missing, re-extracting tarball...")
            root = extract_tarball(RAW_TARBALL_PATH, RAW_DIR)
            extracted_marker.write_text(str(root), encoding="utf-8")
    else:
        log("Extracting tarball...")
        root = extract_tarball(RAW_TARBALL_PATH, RAW_DIR)
        extracted_marker.write_text(str(root), encoding="utf-8")

    meta = {
        "version": VERSION,
        "urls": urls,
        "used_url": used_url or urls[0],
        "sha256": sha,
        "tarball_path": str(RAW_TARBALL_PATH),
        "extracted_root": str(root),
        "fetched_at": dt.datetime.utcnow().isoformat() + "Z",
    }
    try:
        SOURCE_META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        log(f"WARN: failed writing source meta: {e}")
    return root

    # --------------------------------------------------------------------------------------
    # Parsing and normalization pipeline
    # --------------------------------------------------------------------------------------


def process_all_manpages(root: Path, limit: Optional[int] = None) -> List[ManDoc]:
    """Discover and parse all man pages, saving parsed artifacts. Returns ManDoc list."""
    man_files = discover_man_files(root, limit=limit)
    log(f"Discovered {len(man_files)} man files under {root}")

    docs: List[ManDoc] = []
    failures = 0

    def worker(p: Path):
        try:
            return parse_and_normalize_page(p, PARSED_JSON_DIR)
        except Exception as e:
            return (None, None, None)

    max_workers = min(8, (os.cpu_count() or 4))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        for doc, sections_md, _md_text in ex.map(worker, man_files):
            if doc is None:
                failures += 1
                continue
            docs.append(doc)

    log(f"Parsed {len(docs)} docs. Failures: {failures}")
    return docs

    # --------------------------------------------------------------------------------------
    # Aux assets: indices, aliases, section hints
    # --------------------------------------------------------------------------------------


def write_documents_index_and_summary(docs: List[ManDoc]) -> None:
    # Index JSONL
    with open(DOC_INDEX_PATH, "w", encoding="utf-8") as f:
        for d in docs:
            rec = {
                "document_id": d.document_id,
                "version_tag": d.version_tag,
                "page_name": d.page_name,
                "section": d.section,
                "title": d.title,
                "aliases": d.aliases,
                "see_also": d.see_also,
                "source_path": d.source_path,
                "created_at": d.created_at,
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # Summary
    by_section = Counter(d.section for d in docs)
    with_name = sum(1 for d in docs if d.name_raw)
    with_synopsis = sum(1 for d in docs if d.synopsis_raw)
    with_errors = sum(1 for d in docs if any(s.subsection_name.upper() == "ERRORS" for s in d.subsections))
    summary = {
        "version": VERSION,
        "total_documents": len(docs),
        "documents_by_section": dict(sorted(by_section.items(), key=lambda x: x[0])),
        "with_NAME": with_name,
        "with_SYNOPSIS": with_synopsis,
        "with_ERRORS": with_errors,
        "generated_at": dt.datetime.utcnow().isoformat() + "Z",
    }
    DOC_SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"Wrote index: {DOC_INDEX_PATH}")
    log(f"Wrote summary: {DOC_SUMMARY_PATH}")


def write_aliases_and_section_hints(docs: List[ManDoc]) -> None:
    # aliases: alias -> {canonical, section, document_id}
    alias_map: Dict[str, Dict[str, str]] = {}
    for d in docs:
        canonical = d.page_name
        for a in d.aliases:
            if not a:
                continue
            alias_key = a.strip()
            alias_map[alias_key] = {
                "canonical": canonical,
                "section": d.section,
                "document_id": d.document_id,
            }
    ALIASES_PATH.write_text(json.dumps(alias_map, ensure_ascii=False, indent=2), encoding="utf-8")

    # section hints: both canonical->synonyms and reverse
    canon_to_syn = {k: v for k, v in SECTION_SYNONYMS.items()}
    syn_to_canon: Dict[str, str] = {}
    for canon, syns in canon_to_syn.items():
        for s in syns:
            syn_to_canon[s] = canon
    hints = {
        "canonical_to_synonyms": canon_to_syn,
        "synonym_to_canonical": syn_to_canon,
    }
    SECTION_HINTS_PATH.write_text(json.dumps(hints, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"Wrote aliases: {ALIASES_PATH}")
    log(f"Wrote section hints: {SECTION_HINTS_PATH}")

    # --------------------------------------------------------------------------------------
    # Chunking
    # --------------------------------------------------------------------------------------


def chunk_documents(docs: List[ManDoc]) -> List[Dict]:
    encode_fn = tokenize_counter()
    all_chunks: List[Dict] = []

    for d in docs:
        page = d.page_name
        sec_num = d.section
        # Iterate in original order of parsed sections
        for ss in d.subsections:
            sec_name = ss.subsection_name.strip().upper() if ss.subsection_name else "SECTION"
            text = ss.raw_text or ""
            if not text.strip():
                continue
            blocks = split_into_paragraphs_preserve_code(text)
            chunks = assemble_chunks_from_blocks(
                doc_id=d.document_id,
                page_name=page,
                section_num=sec_num,
                section_name=sec_name,
                blocks=blocks,
                encode_fn=encode_fn,
            )
            all_chunks.extend(chunks)

    # Write as JSONL
    with open(CHUNKS_PATH, "w", encoding="utf-8") as f:
        for ch in all_chunks:
            f.write(json.dumps(ch, ensure_ascii=False) + "\n")
    log(f"Wrote {len(all_chunks)} chunks to {CHUNKS_PATH}")
    return all_chunks

    # --------------------------------------------------------------------------------------
    # Eval set and quality checks
    # --------------------------------------------------------------------------------------


def build_eval_set(docs: List[ManDoc], chunks: List[Dict], max_items: int = 200) -> List[Dict]:
    # Build quick lookup by doc_id and section
    chunks_by_doc: Dict[str, List[Dict]] = {}
    by_doc_section: Dict[Tuple[str, str], List[Dict]] = {}
    for ch in chunks:
        chunks_by_doc.setdefault(ch["document_id"], []).append(ch)
        key = (ch["document_id"], (ch.get("section_name") or "").upper())
        by_doc_section.setdefault(key, []).append(ch)

    eval_items: List[Dict] = []

    # 1) NAME questions
    for d in docs:
        key = (d.document_id, "NAME")
        chs = by_doc_section.get(key, [])
        if not chs:
            continue
        # Use first line from NAME
        name_text = (d.name_raw or "").strip()
        if not name_text:
            continue
        first_line = None
        for ln in name_text.splitlines():
            s = ln.strip()
            if s:
                first_line = s
                break
        if not first_line:
            continue
        target_anchor = chs[0]["anchor"]
        q = f"What is the NAME of {d.page_name}({d.section})?"
        eval_items.append({
            "query": q,
            "expected_substrings": [first_line[:200]],
            "document_id": d.document_id,
            "target_section": "NAME",
            "target_anchor": target_anchor,
        })

    # 2) SYNOPSIS questions
    for d in docs:
        key = (d.document_id, "SYNOPSIS")
        chs = by_doc_section.get(key, [])
        if not chs:
            continue
        syn = (d.synopsis_raw or "").strip()
        if not syn:
            continue
        first_line = None
        for ln in syn.splitlines():
            s = ln.strip()
            if s:
                first_line = s
                break
        if not first_line:
            continue
        q = f"Provide the SYNOPSIS for {d.page_name}({d.section})."
        eval_items.append({
            "query": q,
            "expected_substrings": [first_line[:200]],
            "document_id": d.document_id,
            "target_section": "SYNOPSIS",
            "target_anchor": chs[0]["anchor"],
        })

    # 3) ERRORS and errno constants
    # Extract some common constants from ERRORS chunks
    errno_items = []
    for d in docs:
        key = (d.document_id, "ERRORS")
        chs = by_doc_section.get(key, [])
        for ch in chs:
            consts = ch.get("constants") or []
            for c in consts:
                if re.match(r"E[A-Z0-9_]{2,}$", c):
                    q = f"In {d.page_name}({d.section}), what does {c} mean?"
                    errno_items.append({
                        "query": q,
                        "expected_substrings": [c],
                        "document_id": d.document_id,
                        "target_section": "ERRORS",
                        "target_anchor": ch["anchor"],
                    })
    # Limit per doc to avoid explosion
    random.shuffle(errno_items)
    errno_by_doc = {}
    filtered_errno = []
    for it in errno_items:
        did = it["document_id"]
        cnt = errno_by_doc.get(did, 0)
        if cnt >= 3:
            continue
        errno_by_doc[did] = cnt + 1
        filtered_errno.append(it)

    combined = []
    combined.extend(eval_items)
    combined.extend(filtered_errno)
    # Limit total
    random.shuffle(combined)
    combined = combined[:max_items]

    # Write file
    with open(EVAL_SET_PATH, "w", encoding="utf-8") as f:
        for it in combined:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    log(f"Wrote eval set ({len(combined)} items) to {EVAL_SET_PATH}")
    return combined


def quality_report(docs: List[ManDoc], chunks: List[Dict]) -> Dict:
    total_chunks = len(chunks)
    if total_chunks == 0:
        report = {
            "version": VERSION,
            "generated_at": dt.datetime.utcnow().isoformat() + "Z",
            "total_documents": len(docs),
            "total_chunks": 0,
            "note": "No chunks generated.",
        }
        QUALITY_REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"Wrote quality report: {QUALITY_REPORT_PATH}")
        return report

    token_counts = [ch.get("token_count", 0) for ch in chunks]
    oversized = [tc for tc in token_counts if tc > CHUNK_MAX_TOKENS]
    by_section_name = Counter((ch.get("section_name") or "").upper() for ch in chunks)
    by_document = Counter(ch.get("document_id") for ch in chunks)

    def percentile(sorted_vals: List[int], p: float) -> float:
        if not sorted_vals:
            return 0.0
        if p <= 0:
            return float(sorted_vals[0])
        if p >= 100:
            return float(sorted_vals[-1])
        k = (len(sorted_vals) - 1) * (p / 100.0)
        f = int(k)
        c = min(f + 1, len(sorted_vals) - 1)
        if f == c:
            return float(sorted_vals[f])
        d0 = sorted_vals[f] * (c - k)
        d1 = sorted_vals[c] * (k - f)
        return float(d0 + d1)

    token_counts_sorted = sorted(int(tc) for tc in token_counts if isinstance(tc, int))
    total_tokens = sum(token_counts_sorted)
    avg_tokens = (total_tokens / len(token_counts_sorted)) if token_counts_sorted else 0.0

    # Oversized chunks
    oversized_anchors = [ch["anchor"] for ch in chunks if ch.get("token_count", 0) > CHUNK_MAX_TOKENS]

    # Duplicate anchors check
    anchor_counts = Counter(ch.get("anchor") for ch in chunks)
    duplicate_anchors = [a for a, c in anchor_counts.items() if c > 1]

    # Section coverage per document (what subsections exist)
    sections_present_per_doc: Dict[str, List[str]] = {}
    for d in docs:
        secs = []
        for ss in d.subsections:
            nm = (ss.subsection_name or "").upper()
            if nm:
                secs.append(nm)
        sections_present_per_doc[d.document_id] = sorted(set(secs))

    # Constants and SEE ALSO frequencies
    constants_counter = Counter()
    see_also_counter = Counter()
    for ch in chunks:
        for c in ch.get("constants") or []:
            constants_counter[c] += 1
        for r in ch.get("see_also_refs") or []:
            see_also_counter[r] += 1

    report = {
        "version": VERSION,
        "generated_at": dt.datetime.utcnow().isoformat() + "Z",
        "total_documents": len(docs),
        "total_chunks": total_chunks,
        "tokens": {
            "total": total_tokens,
            "avg": avg_tokens,
            "min": token_counts_sorted[0] if token_counts_sorted else 0,
            "p50": percentile(token_counts_sorted, 50.0),
            "p90": percentile(token_counts_sorted, 90.0),
            "p95": percentile(token_counts_sorted, 95.0),
            "max": token_counts_sorted[-1] if token_counts_sorted else 0,
        },
        "chunks_by_section_name": dict(sorted(by_section_name.items(), key=lambda x: x[0])),
        "chunks_by_document": {
            "min": min(by_document.values()) if by_document else 0,
            "avg": (sum(by_document.values()) / len(by_document)) if by_document else 0.0,
            "max": max(by_document.values()) if by_document else 0,
        },
        "oversized_chunks": {
            "count": len(oversized_anchors),
            "max_allowed_tokens": CHUNK_MAX_TOKENS,
            "examples": oversized_anchors[:20],
        },
        "duplicate_anchors": {
            "count": len(duplicate_anchors),
            "examples": duplicate_anchors[:20],
        },
        "sections_present_per_doc_sample": {
            d_id: sections_present_per_doc[d_id] for d_id in list(sections_present_per_doc.keys())[:50]
        },
        "top_constants": constants_counter.most_common(50),
        "top_see_also_refs": see_also_counter.most_common(50),
    }

    QUALITY_REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"Wrote quality report: {QUALITY_REPORT_PATH}")
    return report


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Man-pages corpus prep: acquisition, parsing, chunking, aux assets, eval.")
    parser.add_argument("--root", type=str, default=None,
                        help="Path to existing extracted man-pages root (skips download).")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of man pages processed (for testing).")
    parser.add_argument("--skip-download", action="store_true",
                        help="Skip downloading; use --root or previously extracted dataset.")
    args = parser.parse_args()

    ensure_dirs()

    if args.root:
        root = Path(args.root).resolve()
        if not root.exists():
            raise SystemExit(f"--root path does not exist: {root}")
        log(f"Using provided root: {root}")
    else:
        if args.skip_download and SOURCE_META.exists():
            # Try to load extracted root from marker
            marker = RAW_DIR / ".extracted_root"
            if marker.exists():
                root = Path(marker.read_text(encoding="utf-8").strip())
                log(f"Using previously extracted root: {root}")
            else:
                raise SystemExit("No extracted root found. Provide --root or remove --skip-download.")
        else:
            root = acquire_dataset()

    # Process and persist structured docs
    docs = process_all_manpages(root, limit=args.limit)
    if not docs:
        raise SystemExit("No documents processed. Aborting.")

    # Aux assets
    write_documents_index_and_summary(docs)
    write_aliases_and_section_hints(docs)

    # Chunking
    chunks = chunk_documents(docs)

    # Eval and quality
    build_eval_set(docs, chunks, max_items=200)
    quality_report(docs, chunks)

    log("All done.")


if __name__ == "__main__":
    main()
