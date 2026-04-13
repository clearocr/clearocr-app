# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import mimetypes
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import requests
from pypdf import PdfReader, PdfWriter

EXTS = {'.jpg', '.jpeg', '.png', '.pdf'}


@dataclass(slots=True)
class OCRSettings:
    api_url: str
    api_key: str
    api_version: str = '0.1'
    search_barcodes: bool = False
    show_pages_separately: bool = False
    max_pages_per_request: int = 2
    http_timeout: int = 300


def normalize_text(text: str) -> str:
    text = (text or '').replace('\r', '')
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+\n', '\n', text)
    text = re.sub(r'\n[ \t]+', '\n', text)
    text = text.strip()
    return text + ('\n' if text else '')


def coerce_to_str(value) -> str:
    if value is None:
        return ''
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return '\n'.join(coerce_to_str(item) for item in value if item is not None).strip()
    if isinstance(value, dict):
        if 'text' in value:
            return coerce_to_str(value.get('text'))
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def extract_text(result: dict, keep_page_separators: bool = True) -> str:
    if not isinstance(result, dict):
        return ''

    pages = result.get('pages')
    if isinstance(pages, list) and pages:
        rendered_pages: list[str] = []
        for index, page in enumerate(pages, start=1):
            if isinstance(page, dict):
                page_text = coerce_to_str(page.get('text'))
            else:
                page_text = coerce_to_str(page)
            page_text = normalize_text(page_text).rstrip()
            if not page_text:
                continue
            if keep_page_separators:
                rendered_pages.append(f'--- PAGE {index} ---\n{page_text}')
            else:
                rendered_pages.append(page_text)
        merged = '\n\n'.join(rendered_pages).strip()
        return merged + ('\n' if merged else '')

    return normalize_text(coerce_to_str(result.get('text')))


def extract_barcodes(result: dict) -> list[str]:
    if not isinstance(result, dict):
        return []

    candidates: list[str] = []

    for key in ('barcodes', 'barcode', 'codes', 'qr_codes', 'detected_barcodes'):
        value = result.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    code_type = str(item.get('type', '')).strip()
                    code_value = str(item.get('value', '')).strip() or str(item.get('text', '')).strip()
                    if code_value:
                        candidates.append(f'{code_type}: {code_value}' if code_type else code_value)
                elif item is not None:
                    text = str(item).strip()
                    if text:
                        candidates.append(text)

    pages = result.get('pages')
    if isinstance(pages, list):
        for page_index, page in enumerate(pages, start=1):
            if not isinstance(page, dict):
                continue
            for key in ('barcodes', 'barcode', 'codes', 'qr_codes', 'detected_barcodes'):
                value = page.get(key)
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            code_type = str(item.get('type', '')).strip()
                            code_value = str(item.get('value', '')).strip() or str(item.get('text', '')).strip()
                            if code_value:
                                prefix = f'PAGE {page_index} | '
                                candidates.append(prefix + (f'{code_type}: {code_value}' if code_type else code_value))
                        elif item is not None:
                            text = str(item).strip()
                            if text:
                                candidates.append(f'PAGE {page_index} | {text}')

    seen = set()
    output: list[str] = []
    for item in candidates:
        if item not in seen:
            seen.add(item)
            output.append(item)
    return output


def build_headers(settings: OCRSettings) -> dict:
    return {
        'CLEAR-OCR-API-KEY': settings.api_key,
        'CLEAR-OCR-API-VERSION': settings.api_version,
    }


def post_file_to_api(path: Path, settings: OCRSettings) -> dict:
    mime_type, _ = mimetypes.guess_type(path.name)
    mime_type = mime_type or 'application/octet-stream'

    with path.open('rb') as file_handle:
        response = requests.post(
            settings.api_url,
            headers=build_headers(settings),
            files={'file': (path.name, file_handle, mime_type)},
            data={
                'search_barcodes': 'true' if settings.search_barcodes else 'false',
                'show_pages_separately': 'true' if settings.show_pages_separately else 'false',
            },
            timeout=settings.http_timeout,
            verify=True,
        )

    if not response.ok:
        snippet = (response.text or '')[:1000]
        raise RuntimeError(f'HTTP {response.status_code}. Body[:1000]={snippet}')

    try:
        payload = response.json()
    except Exception as exc:
        raise RuntimeError(f'API did not return valid JSON: {exc}') from exc

    if not isinstance(payload, dict):
        raise RuntimeError('API returned JSON, but not an object.')

    return payload


def pdf_show_npages(pdf_path: Path) -> int:
    try:
        reader = PdfReader(str(pdf_path))
    except Exception as exc:
        raise RuntimeError(f'Cannot read PDF: {pdf_path} | {exc}') from exc
    return len(reader.pages)


def pdf_extract_pages(pdf_path: Path, start: int, end: int, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        reader = PdfReader(str(pdf_path))
        writer = PdfWriter()
        for i in range(start - 1, end):
            writer.add_page(reader.pages[i])
        with out_path.open('wb') as handle:
            writer.write(handle)
    except Exception as exc:
        raise RuntimeError(f'Failed to create PDF chunk {start}-{end}: {exc}') from exc

    if not out_path.exists() or out_path.stat().st_size < 64:
        raise RuntimeError(f'PDF chunk was not created correctly: {out_path}')


def list_supported_files(directory: Path, recursive: bool = True) -> list[Path]:
    if not directory.exists() or not directory.is_dir():
        raise RuntimeError(f'Not a directory: {directory}')
    iterator = directory.rglob('*') if recursive else directory.glob('*')
    return sorted(path.resolve() for path in iterator if path.is_file() and path.suffix.lower() in EXTS)


def _validate_api_response(response_json: dict, *, context: str = '') -> dict:
    success = bool(response_json.get('success', True))
    if not success:
        prefix = f'{context} | ' if context else ''
        raise RuntimeError(f"{prefix}API success=false | errors={response_json.get('errors')}")
    result = response_json.get('result') or {}
    if not isinstance(result, dict):
        result = {'text': result}
    return result


def _append_barcodes_section(text: str, barcodes: list[str], enabled: bool) -> str:
    text = (text or '').strip()
    if not enabled or not barcodes:
        return text
    block = '--- BARCODES ---\n' + '\n'.join(barcodes)
    return f'{text}\n\n{block}' if text else block


def process_image(path: Path, settings: OCRSettings, output_dir: Optional[Path] = None) -> Path:
    output_dir = output_dir or path.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    txt_path = output_dir / f'{path.stem}.txt'

    result = _validate_api_response(post_file_to_api(path, settings))
    text = extract_text(result, keep_page_separators=settings.show_pages_separately).rstrip()
    barcodes = extract_barcodes(result) if settings.search_barcodes else []
    final_text = _append_barcodes_section(text, barcodes, settings.search_barcodes)
    if not final_text.strip():
        raise RuntimeError('Empty OCR result')

    txt_path.write_text(final_text + '\n', encoding='utf-8')
    return txt_path


def process_pdf(
    path: Path,
    settings: OCRSettings,
    output_dir: Optional[Path] = None,
    logger: Optional[Callable[[str], None]] = None,
) -> Path:
    output_dir = output_dir or path.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    txt_path = output_dir / f'{path.stem}.txt'
    npages = pdf_show_npages(path)

    if npages <= settings.max_pages_per_request:
        result = _validate_api_response(post_file_to_api(path, settings))

        if settings.show_pages_separately:
            pages = result.get('pages')
            if isinstance(pages, list) and pages:
                rendered_pages: list[str] = []
                for page_no, page in enumerate(pages, start=1):
                    page_text = coerce_to_str(page.get('text')) if isinstance(page, dict) else coerce_to_str(page)
                    page_text = normalize_text(page_text).rstrip()
                    if page_text:
                        rendered_pages.append(f'--- PAGE {page_no} ---\n{page_text}')
                final_text = '\n\n'.join(rendered_pages).strip()
            else:
                text = extract_text(result, keep_page_separators=False).strip()
                final_text = f'--- PAGE 1 ---\n{text}' if text else ''
        else:
            final_text = extract_text(result, keep_page_separators=False).strip()

        barcodes = extract_barcodes(result) if settings.search_barcodes else []
        final_text = _append_barcodes_section(final_text, barcodes, settings.search_barcodes)
        if not final_text.strip():
            raise RuntimeError('Empty OCR result')

        txt_path.write_text(final_text + '\n', encoding='utf-8')
        return txt_path

    parts_dir = output_dir / f'{path.stem}.parts'
    parts_dir.mkdir(parents=True, exist_ok=True)

    rendered_blocks: list[str] = []
    chunk_index = 0
    all_barcodes: list[str] = []

    try:
        for start in range(1, npages + 1, settings.max_pages_per_request):
            end = min(start + settings.max_pages_per_request - 1, npages)
            chunk_index += 1
            chunk_pdf = parts_dir / f'{path.stem}__chunk_{chunk_index:03d}__p{start:04d}-{end:04d}.pdf'
            if logger:
                logger(f'PDF chunk {chunk_index}: pages {start}-{end}')

            pdf_extract_pages(path, start, end, chunk_pdf)
            result = _validate_api_response(post_file_to_api(chunk_pdf, settings), context=f'chunk {start}-{end}')

            if settings.search_barcodes:
                all_barcodes.extend(extract_barcodes(result))

            if settings.show_pages_separately:
                pages = result.get('pages')
                if isinstance(pages, list) and pages:
                    for offset, page in enumerate(pages, start=start):
                        page_text = coerce_to_str(page.get('text')) if isinstance(page, dict) else coerce_to_str(page)
                        page_text = normalize_text(page_text).rstrip()
                        if page_text:
                            rendered_blocks.append(f'--- PAGE {offset} ---\n{page_text}')
                else:
                    text = extract_text(result, keep_page_separators=False).rstrip()
                    if text:
                        rendered_blocks.append(f'--- PAGE {start} ---\n{text}')
            else:
                text = extract_text(result, keep_page_separators=False).rstrip()
                if text:
                    rendered_blocks.append(text)

        final_text = '\n\n'.join(rendered_blocks).strip()

        if settings.search_barcodes and all_barcodes:
            seen = set()
            dedup: list[str] = []
            for item in all_barcodes:
                if item not in seen:
                    seen.add(item)
                    dedup.append(item)
            final_text = _append_barcodes_section(final_text, dedup, True)

        if not final_text:
            raise RuntimeError('Empty OCR result for PDF')

        txt_path.write_text(final_text + '\n', encoding='utf-8')
        return txt_path
    finally:
        try:
            if parts_dir.exists():
                shutil.rmtree(parts_dir)
        except Exception:
            pass


def process_file(
    path: Path,
    settings: OCRSettings,
    output_dir: Optional[Path] = None,
    logger: Optional[Callable[[str], None]] = None,
) -> Path:
    if not path.exists():
        raise FileNotFoundError(f'File does not exist: {path}')
    if path.suffix.lower() not in EXTS:
        raise RuntimeError(f'Unsupported extension: {path.suffix}')
    if path.suffix.lower() == '.pdf':
        return process_pdf(path, settings, output_dir=output_dir, logger=logger)
    return process_image(path, settings, output_dir=output_dir)


def process_directory(
    directory: Path,
    settings: OCRSettings,
    output_dir: Optional[Path] = None,
    recursive: bool = True,
    logger: Optional[Callable[[str], None]] = None,
) -> list[Path]:
    files = list_supported_files(directory, recursive=recursive)
    results: list[Path] = []
    for path in files:
        if logger:
            logger(f'Processing: {path}')
        results.append(process_file(path, settings, output_dir=output_dir, logger=logger))
    return results


def save_settings_to_json(path: Path, settings_dict: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings_dict, ensure_ascii=False, indent=2), encoding='utf-8')


def load_settings_from_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}
