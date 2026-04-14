# 🚀 clearOCR Client

Extract clean, well-ordered text from PDFs and images using the **clearOCR API**.

Desktop application with batch processing, PDF chunking and optional barcode detection.

---

## ✨ Features

* 🔑 API key authentication
* 📂 Batch OCR for files and folders
* 📄 PDF support with automatic chunking (**pypdf**, no system dependencies)
* 🔍 Optional barcode detection
* 🧾 Clean text output with proper reading order
* 📑 Optional page markers in TXT output (`--- PAGE N ---`)
* 🌍 Automatic UI language detection:

  * Polish 🇵🇱 if system language starts with `pl`
  * English 🇬🇧 otherwise
* ⚙️ Local settings (stored on user's machine)

---

## 🎁 Free Tier

New users receive:

* **1,000 free OCR runs**
* valid for **30 days**

To get started:

* create an account at **https://clearocr.com**
* generate your **API key**
* use it in the application

---

## 📸 Screenshot

![clearOCR screenshot](assets/clearocr-app-screenshot.png)

---

## ⚡ Quick Start

1. Start the application
2. Enter your **API KEY**
3. Run OCR on your files

---

## 📦 Installation

### Option 1 — Install from GitHub Release

Download the latest `.whl` file from the **Releases** section.

#### Linux / macOS

```bash
python -m venv env
source env/bin/activate
pip install -U pip
pip install clearocr_app-0.1.1-py3-none-any.whl
```

#### Windows (PowerShell)

```powershell
python -m venv env
env\Scripts\activate
pip install -U pip
pip install clearocr_app-0.1.1-py3-none-any.whl
```

Run:

```bash
clearocr-app
```

---

### Option 2 — Install from source

```bash
git clone https://github.com/clearocr/clearocr-app.git
cd clearocr-app
```

#### Linux / macOS

```bash
python -m venv env
source env/bin/activate
pip install -U pip
pip install .
```

#### Windows (PowerShell)

```powershell
python -m venv env
env\Scripts\activate
pip install -U pip
pip install .
```

Run:

```bash
clearocr-app
```

---

## ⚙️ API Configuration

The client is preconfigured to work with the clearOCR API:

```text
https://clearocr.teamquest.pl:60213/extract-document-parser
```

You only need to provide:

* **API KEY**

No username or additional setup required.

---

## 📄 Output

* Output is saved as `.txt`
* Optional page separators:

```text
--- PAGE 1 ---
```

* Barcode results (when enabled) are appended at the end:

```text
--- BARCODES ---
```

---

## 🧠 How it works

* Files are sent to the clearOCR API
* Large PDFs are automatically split into chunks
* Results are merged into a single clean text output
* Temporary files are removed after processing

---

## 📊 OCR Benchmarks (Polish documents)

Performance benchmarks on real-world Polish documents:

👉 https://huggingface.co/collections/Lukaszl/polish-ocr-benchmarks-results

---

## ⚠️ Disclaimer

This application is provided **"AS IS"**, without any guarantees or support.

* No technical support is provided for this client
* Use at your own risk
* For production use, rely on the **clearOCR API directly**

---

## ⚠️ Requirements

* Python **3.10+**
* No external system dependencies (uses `pypdf`)

---

## 🛠 Development

```bash
pip install build
python -m build
```

Build output:

```text
dist/
```

---

## 📜 License

Apache License 2.0
