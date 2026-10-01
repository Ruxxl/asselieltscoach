"""Отчёт Grammar Checker в .docx: текст с подчёркнутыми ошибками, исправлением рядом и комментарием ИИ
на полях Word (настоящие комментарии — их видно в панели рецензирования и можно принять/удалить)."""

import io
from datetime import datetime

from docx import Document
from docx.enum.text import WD_UNDERLINE
from docx.shared import Pt, RGBColor

_RED = RGBColor(0xC6, 0x28, 0x28)
_GREEN = RGBColor(0x1B, 0x7F, 0x3B)
_GREY = RGBColor(0x6B, 0x7A, 0x8A)


def build_report(*, text: str, issues: list[dict], result: dict, author: str) -> bytes:
    doc = Document()
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(11)
    initials = "".join(w[0] for w in author.split()[:2]).upper() or "AI"

    doc.add_heading("Проверка текста — Grammar Checker", level=0)
    meta = doc.add_paragraph()
    lang = result.get("detected_language")
    meta.add_run(f"{lang + ' · ' if lang else ''}{len(issues)} правок · {datetime.now():%d.%m.%Y}").italic = True

    assessment = result.get("assessment")
    if assessment:
        p = doc.add_paragraph()
        run = p.add_run(f"Оценка текста: {assessment['score']}/100")
        run.bold, run.font.size = True, Pt(16)
        if assessment.get("level"):
            p.add_run(f"   {assessment['level']}").font.color.rgb = _GREY
        if assessment.get("summary"):
            doc.add_paragraph(assessment["summary"])
        for title, items in (("Сильные стороны", assessment["strengths"]), ("Что улучшить", assessment["improvements"])):
            if items:
                doc.add_heading(title, level=2)
                for item in items:
                    doc.add_paragraph(item, style="List Bullet")
    if result.get("teacher_comment"):
        doc.add_heading("Комментарий преподавателя", level=1)
        doc.add_paragraph(result["teacher_comment"])

    doc.add_heading("Текст с исправлениями", level=1)
    note = doc.add_paragraph("Ошибка подчёркнута красным, исправление — зелёным; пояснения — в комментариях на полях.")
    note.runs[0].font.size, note.runs[0].font.color.rgb = Pt(9), _GREY
    offset = 0
    for line in text.split("\n"):
        start, end = offset, offset + len(line)
        offset = end + 1
        if not line.strip():
            continue
        p = doc.add_paragraph()
        cursor = start
        for issue in issues:
            if issue["start"] < start or issue["end"] > end:
                continue
            p.add_run(text[cursor : issue["start"]])
            wrong = p.add_run(issue["original"])
            wrong.font.color.rgb, wrong.font.underline = _RED, WD_UNDERLINE.WAVY
            fix = p.add_run(f" [{issue['suggestion']}]")
            fix.bold, fix.font.color.rgb = True, _GREEN
            comment = f"→ {issue['suggestion']}"
            if issue.get("explanation"):
                comment += f"\n{issue['explanation']}"
            doc.add_comment([wrong, fix], text=comment, author=author, initials=initials)
            cursor = issue["end"]
        p.add_run(text[cursor:end])

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
