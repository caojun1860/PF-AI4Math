#!/bin/bash
# 编译对称空间UAP论文
cd "$(dirname "$0")"
xelatex -interaction=nonstopmode -output-directory=paper/build paper/symmetric-space-uap.tex
xelatex -interaction=nonstopmode -output-directory=paper/build paper/symmetric-space-uap.tex
echo "完成。PDF位于 paper/build/symmetric-space-uap.pdf"
open paper/build/symmetric-space-uap.pdf 2>/dev/null
