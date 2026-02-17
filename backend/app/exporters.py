from io import BytesIO

import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


def build_results_dataframe(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=["player_name", "score", "correct_answers", "answers_submitted"])
    return pd.DataFrame(rows)


def to_csv_bytes(rows: list[dict]) -> bytes:
    df = build_results_dataframe(rows)
    return df.to_csv(index=False).encode("utf-8")


def to_xlsx_bytes(rows: list[dict]) -> bytes:
    df = build_results_dataframe(rows)
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="results")
    return buffer.getvalue()


def to_pdf_bytes(rows: list[dict], title: str = "Quiz Results") -> bytes:
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, height - 40, title)
    c.setFont("Helvetica", 10)
    y = height - 70

    headers = ["Player", "Score", "Correct", "Answers"]
    c.drawString(40, y, " | ".join(headers))
    y -= 15

    for row in rows:
        line = f"{row['player_name']} | {row['score']} | {row['correct_answers']} | {row['answers_submitted']}"
        c.drawString(40, y, line[:110])
        y -= 14
        if y < 40:
            c.showPage()
            y = height - 40

    c.save()
    buffer.seek(0)
    return buffer.getvalue()
