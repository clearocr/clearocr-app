# clearOCR Client

Desktop client for running OCR on PDF and image files using the **clearOCR API**.

## Features

- API key authentication
- batch OCR for files and folders
- barcode search (optional)
- optional page markers in TXT output
- automatic desktop language detection:
  - **Polish UI** if the system language starts with `pl`
  - **English UI** for all other system languages
- PDF chunking with **pypdf** (no system `qpdf` required)
- PyPI-ready package structure

## Installation from source

```bash
python -m venv venv
source venv/bin/activate
pip install -U pip
pip install .
```

## Run

```bash
clearocr-app
```

or

```bash
clearocr
```

## API configuration

The application uses:

- **API URL**
- **API KEY**

No API username is required.

## Build and publish to PyPI

```bash
pip install build twine
python -m build
python -m twine check dist/*
twine upload dist/*
```

## Notes

- TXT output can include page separators like `--- PAGE 1 ---` when enabled in settings.
- Barcode results are appended to TXT output only when barcode scanning is enabled in the UI.
- Temporary PDF chunk files are removed automatically after processing.
