# Data Ingestion for RAG Vector Project

This document outlines the process by which raw data is acquired, processed, and prepared for ingestion into the Qdrant vector database, forming the knowledge base for our RAG application.

## 1. Data Source

The core dataset for this RAG project is the **`man-pages 6.9` documentation**. This comprises the official manual pages for various commands and functionalities available on Unix-like operating systems. This version provides a stable and comprehensive collection of technical documentation.

## 2. Data Acquisition

The `man-pages 6.9` documentation is typically available in `.tar.gz` archives or as part of system installations. For this project, the data is acquired by:

*   **Downloading the official `man-pages 6.9` source archive:** This ensures we have the most accurate and complete raw data. The archive usually contains individual manual pages in their source format (e.g., nroff, groff).
*   **Extracting the archive:** Once downloaded, the archive is extracted into a designated directory within the project structure, making the individual `.man` or `.txt` files accessible for further processing.

## 3. Data Generation/Parsing Script (`ingest_manpages.py`)

A Python script, `ingest_manpages.py` is responsible for processing the raw `man-pages` data. This script performs the following key steps:

### 3.1. Iterating through Man Pages

The script traverses the extracted `man-pages` directory, identifying all relevant manual page files. It typically focuses on files with extensions like `.1`, `.2`, ..., `.8`, or those without extensions depending on the `man` page structure.

### 3.2. Parsing Man Page Content

Each manual page file often contains formatting directives (e.g., `groff`/`nroff` syntax). To extract clean, readable text suitable for RAG, the script employs a parsing strategy:

*   **Using `man` utility (recommended):** The most robust approach is to leverage the `man` command-line utility itself to render the manual pages into plain text. This handles all formatting and cross-references correctly. The script executes commands like `man -P cat <man_page_path> > output.txt` for each page.
*   **Direct parsing (alternative):** If direct `man` utility usage is not feasible or desired, custom parsing logic can be implemented using regular expressions or specialized libraries to strip out formatting directives and extract the core textual content. However, this is more complex and prone to errors compared to using the `man` utility.

### 3.3. Chunking

Large manual pages are unlikely to fit within the token limits of most Language Models (LLMs) and can also dilute the relevance of embeddings. Therefore, the parsed text is divided into smaller, coherent chunks. The chunking strategy considers:

*   **Section-based chunking:** Manual pages are typically structured with sections like `NAME`, `SYNOPSIS`, `DESCRIPTION`, `OPTIONS`, `EXAMPLES`, `SEE ALSO`. The script attempts to identify these section headers and chunk the text accordingly, ensuring each chunk retains contextual integrity.
*   **Fixed-size or a combination:** A hybrid approach might be used, where sections are preferred, but if a section is too long, it's further split into fixed-size chunks (e.g., 500-1000 tokens) with a configurable overlap to maintain context across chunks.
*   **Metadata extraction:** During chunking, relevant metadata is extracted for each chunk, such as:
    *   `man_page_name`: The name of the command (e.g., `ls`, `grep`).
    *   `section`: The section of the man page (e.g., `DESCRIPTION`, `OPTIONS`).
    *   `source_file`: The original man page file path.
    *   `version`: `6.9` in this case.
