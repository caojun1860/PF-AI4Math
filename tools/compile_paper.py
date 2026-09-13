#!/usr/bin/env python3
"""Compile LaTeX paper to PDF using xelatex."""
import subprocess
import sys
import os

tex_file = sys.argv[1] if len(sys.argv) > 1 else "paper/symmetric-space-uap.tex"
output_dir = os.path.join(os.path.dirname(tex_file), "build")
os.makedirs(output_dir, exist_ok=True)

base = os.path.splitext(os.path.basename(tex_file))[0]

# Run xelatex twice for references
for i in range(2):
    print(f"\n=== xelatex run {i+1}/2 ===")
    result = subprocess.run(
        ["xelatex", "-interaction=nonstopmode",
         f"-output-directory={output_dir}", tex_file],
        capture_output=True, text=True
    )
    print(result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout)
    if result.returncode != 0:
        # Print errors
        print("\n=== ERRORS ===")
        for line in result.stdout.split("\n"):
            if line.startswith("!"):
                print(line)
        print(f"\nxelatex exited with code {result.returncode}")
        sys.exit(1)

pdf_path = os.path.join(output_dir, base + ".pdf")
print(f"\nPDF generated: {pdf_path}")
print(f"File size: {os.path.getsize(pdf_path)} bytes")
