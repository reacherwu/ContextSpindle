# Continuum Academic Research Paper Package

This directory contains the complete publication-ready academic paper assets for **Continuum**:

- **`paper_preprint.md`**: Full-text readable academic preprint in Markdown format. Viewable directly in VS Code, Obsidian, GitHub, or any markdown viewer with full KaTeX math equations, tables, and algorithms.
- **`main.tex`**: Standard IEEE/ACM/arXiv-compatible LaTeX source code with mathematical environments, algorithm pseudo-code boxes, and benchmark tables.
- **`references.bib`**: Curated BibTeX bibliography citing modern foundational work (PagedAttention, FlashAttention, MemGPT, Mamba, RWKV, SWE-bench).

---

## 1. Quick Compilation on Overleaf (Recommended)
1. Go to [Overleaf](https://www.overleaf.com) and create a **New Project -> Upload Project**.
2. Select the `paper/` folder (or zip `main.tex` and `references.bib`).
3. Set the compiler to **pdfLaTeX** or **XeLaTeX** and click **Recompile**.
4. Download the publication-ready PDF.

## 2. Direct Submission to arXiv.org
1. Create a `.tar.gz` archive containing:
   - `main.tex`
   - `references.bib`
2. Submit the archive under categories:
   - `cs.SE` (Software Engineering)
   - `cs.AI` (Artificial Intelligence)
   - `cs.DC` (Distributed, Systems, and Cluster Computing)
