from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import io
import re


MONEY_RE = re.compile(r"(?:\$\s*)?([0-9][0-9,]*\.\d{2})")
DATE_RE = re.compile(r"\b(0?[1-9]|[12]\d|3[01])[-/]([01]?\d)\b")


def movement_fingerprint(account: str, movement_date: str, amount: Decimal, description: str) -> str:
    raw = "|".join((account.strip(), movement_date, f"{amount:.2f}", " ".join(description.upper().split())))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def parse_bbva_rows(rows: list[dict], year: int, account: str = "", direction: str = "credit") -> list[dict]:
    """Convierte renglones OCR posicionados de un estado BBVA en abonos bancarios."""
    movements: list[dict] = []
    for row in rows:
        columns = row.get("columns") if isinstance(row.get("columns"), dict) else {}
        date_text = str(columns.get("date") or "")
        match = DATE_RE.search(date_text)
        if not match:
            continue
        credit_text = str(columns.get(direction) or "")
        money = MONEY_RE.search(credit_text.replace(" ", ""))
        if not money:
            continue
        try:
            amount = Decimal(money.group(1).replace(",", "")).quantize(Decimal("0.01"))
            movement_date = date(year, int(match.group(2)), int(match.group(1))).isoformat()
        except (InvalidOperation, ValueError):
            continue
        description = " ".join(str(columns.get("description") or "").split())[:500]
        movements.append({
            "movement_date": movement_date,
            "description": description,
            "amount": float(amount),
            # El esquema persistente usa ``reference_note``. Mantener el
            # nombre de la columna aquí evita que PostgREST reciba un campo
            # inexistente al guardar el movimiento.
            "reference_note": description,
            "fingerprint": movement_fingerprint(account, movement_date, amount, description),
        })
    return movements


def _ocr_lines_from_pdf(content: bytes) -> list[dict]:
    try:
        import pymupdf  # type: ignore
        from PIL import Image
        from rapidocr import RapidOCR  # type: ignore
    except ImportError as exc:
        raise RuntimeError("El servidor no tiene habilitado el motor OCR para estados de cuenta.") from exc

    engine = RapidOCR()
    grouped: list[dict] = []
    with pymupdf.open(stream=content, filetype="pdf") as document:
        if len(document) > 20:
            raise ValueError("El estado de cuenta excede el máximo de 20 páginas.")
        for page_index, page in enumerate(document):
            pixmap = page.get_pixmap(dpi=180, alpha=False)
            image = Image.open(io.BytesIO(pixmap.tobytes("png"))).convert("RGB")
            result = engine(image)
            boxes = list(result.boxes) if result.boxes is not None else []
            texts = list(result.txts) if result.txts is not None else []
            tokens = []
            for box, text in zip(boxes, texts):
                xs = [point[0] for point in box]
                ys = [point[1] for point in box]
                tokens.append({"x": sum(xs) / len(xs), "y": sum(ys) / len(ys), "text": str(text)})
            tokens.sort(key=lambda item: (item["y"], item["x"]))
            lines: list[list[dict]] = []
            for token in tokens:
                line = next((candidate for candidate in reversed(lines[-4:])
                             if abs(sum(x["y"] for x in candidate) / len(candidate) - token["y"]) <= 9), None)
                if line is None:
                    line = []
                    lines.append(line)
                line.append(token)
            width = float(image.width)
            for line in lines:
                line.sort(key=lambda item: item["x"])
                columns = {"date": [], "description": [], "debit": [], "credit": [], "balance": []}
                for token in line:
                    ratio = token["x"] / width
                    key = "date" if ratio < .13 else "description" if ratio < .50 else "debit" if ratio < .63 else "credit" if ratio < .75 else "balance"
                    columns[key].append(token["text"])
                grouped.append({"page": page_index + 1, "y": min(item["y"] for item in line),
                                "columns": {key: " ".join(value) for key, value in columns.items()}})
    # Las descripciones BBVA suelen ocupar la línea posterior a la fecha.
    for index, row in enumerate(grouped):
        if DATE_RE.search(row["columns"]["date"]):
            descriptions = [row["columns"]["description"]]
            cursor = index + 1
            while cursor < len(grouped) and not DATE_RE.search(grouped[cursor]["columns"]["date"]):
                if grouped[cursor]["page"] != row["page"] or grouped[cursor]["y"] - row["y"] > 55:
                    break
                descriptions.append(grouped[cursor]["columns"]["description"])
                cursor += 1
            row["columns"]["description"] = " ".join(x for x in descriptions if x)
    return grouped


def extract_bank_statement(content: bytes, filename: str, year: int, direction: str = "credit") -> dict:
    if not filename.lower().endswith(".pdf"):
        raise ValueError("Por ahora carga el estado de cuenta en PDF.")
    rows = _ocr_lines_from_pdf(content)
    flat_text = " ".join(value for row in rows for value in row["columns"].values())
    account_match = re.search(r"(?:N[uú]mero\s+de\s+cuenta|Cuenta)\D{0,20}(\d{6,20})", flat_text, re.I)
    account = account_match.group(1) if account_match else ""
    movements = parse_bbva_rows(rows, year, account, direction)
    if not movements:
        raise ValueError("No se detectaron abonos. Revisa que el PDF muestre las columnas Fecha, Concepto, Cargo y Abono.")
    return {"bank": "BBVA", "account": account, "movements": movements, "ocr_rows": len(rows)}
