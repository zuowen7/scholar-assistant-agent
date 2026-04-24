# Notes

## Compile Method
Successful smoke test on 2026-04-22 after package installation and reruns:
- `bibtex main`
- `pdflatex -interaction=nonstopmode -halt-on-error main.tex`
- `pdflatex -interaction=nonstopmode -halt-on-error main.tex`

## Dependencies
At minimum:
- standard LaTeX `article` class
- `geometry`
- `graphicx`
- `amsmath`
- `booktabs`
- `hyperref`

## Collected Files
### Source
- `main.tex`
- `refs.bib`

### Sample PDF
- `main.pdf`

### Assets
- None yet

## Known Issues
- `bibtex main` reports no citation commands because `main.tex` has no citations.

## TODO
- None.
