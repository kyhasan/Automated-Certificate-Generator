# Optimization Notes

## Overview
This update improves the performance of the certificate generation workflow without changing its output format or business logic.

## What changed

### 1. Parallelized the two tournament data fetches
Previously, the script fetched the ranking page and the crosstable page sequentially.

The code now uses `ThreadPoolExecutor` to request both pages at the same time. This reduces idle time caused by waiting on network latency.

Why it was changed:
- Both fetches are independent.
- The script spends most of its time waiting for chess-results.com responses.
- Running them concurrently cuts the overall startup time significantly for larger tournament pages.

### 2. Parallelized certificate generation
Previously, each certificate PDF was generated one-by-one in a serial loop.

The script now submits each certificate-generation task to a worker pool and waits for all results together using `as_completed`.

Why it was changed:
- PDF generation is the most time-consuming step when many participants are involved.
- Modern CPUs can produce several PDFs simultaneously, which reduces wall-clock time.
- This keeps the same output while speeding up the end-to-end tool.

### 3. Added an optional CSV skip flag
The script previously always saved an intermediate CSV file before generating certificates.

A new `--no-csv` option lets the user skip this file when speed matters more than record keeping.

Why it was changed:
- The CSV is useful for auditing or later processing, but it is not required for generation itself.
- Disabling it can save a noticeable amount of I/O time on large tournaments.

### 4. Kept the functional behavior intact
The certificate layout, HTML index generation, QR code generation, and participant parsing logic remain unchanged.

Why it was changed:
- The goal was performance improvement, not a redesign.
- This makes the optimization safer and easier to integrate without affecting outputs.

### 5. Disabled unnecessary ASCII85 wrapping in generated PDFs
ReportLab was wrapping each embedded image stream in ASCII85 using its pure-Python fallback. The PDF does not need this text encoding, so `rl_config.useA85` is disabled while preserving the original Flate-compressed image data.

Why it was changed:
- Profiling showed image embedding dominated PDF generation time.
- A local two-certificate benchmark improved from 7.456 seconds to 1.856 seconds (about 4x faster).
- The same PDFs decreased from about 7.6 MB to about 6.1 MB each.

## Result
These changes reduce overall execution time primarily in two areas:
- reducing waiting time during page downloads
- reducing the serial delay of PDF rendering
- avoiding repeated pure-Python ASCII85 encoding of certificate images

## Command example
```bash
python cert_generator.py --url "https://example.com/tnr123.aspx?lan=1" --category U10 --rounds 5 --no-csv
```

This keeps the workflow fast while still generating PDF certificates and the final HTML index.
