"""Branded Sri Chaitanya A4 PDF for records already saved by the OMR portal."""
from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path
from re import sub
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable, Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

BRAND = colors.HexColor('#BF234C')
DARK = colors.HexColor('#17283D')
GREY = colors.HexColor('#66758A')
LIGHT = colors.HexColor('#F9EEF2')
FAINT = colors.HexColor('#F1F4F8')
BORDER = colors.HexColor('#DEE4EA')


def _text(value: object) -> str:
    return escape(str(value if value is not None else '').strip())


def _num(value: object) -> str:
    try:
        val = float(value)
    except (TypeError, ValueError):
        return '-'
    return str(int(val)) if val.is_integer() else f'{val:.2f}'.rstrip('0').rstrip('.')


def _date(value: object) -> str:
    s = str(value or '').strip()
    try:
        return datetime.strptime(s[:10], '%Y-%m-%d').strftime('%d %b %Y')
    except ValueError:
        return s or '-'


def result_pdf_filename(payload: dict) -> str:
    exam = sub(r'[^A-Za-z0-9_-]+', '_', str(payload.get('exam_type', 'Exam')))
    roll = sub(r'[^A-Za-z0-9_-]+', '_', str(payload.get('roll_number', 'Student')))
    cls = sub(r'[^A-Za-z0-9_-]+', '_', str(payload.get('class_name', 'Class')))
    return f'SriChaitanya_{exam}_{cls}_{roll}_Result.pdf'


def generate_result_pdf(payload: dict, logo_path: str | Path | None = None) -> bytes:
    """Build a PDF from the *saved* result payload; never rerun marking here.

    No API keys, phone numbers, answer key, original OMR photos or Gemini
    diagnostics are included in the student-facing PDF.
    """
    if not payload.get('student_name') or not payload.get('roll_number'):
        raise ValueError('Saved student name and roll number are required for the PDF.')
    total = float(payload['total'])
    maximum = float(payload['maximum'])
    percentage = 100 * total / maximum if maximum else 0.0
    subjects = payload.get('subjects') or {}
    if not isinstance(subjects, dict) or not subjects:
        raise ValueError('Saved subjectwise marks are missing.')

    out = BytesIO()
    page_w, page_h = A4
    margin = 42
    usable = page_w - 2 * margin
    doc = SimpleDocTemplate(
        out, pagesize=A4, leftMargin=margin, rightMargin=margin,
        topMargin=30, bottomMargin=43, title=f'{payload.get("exam_type", "Exam")} - Result',
        author='Sri Chaitanya', subject='OMR Examination Result',
        pageCompression=1,
    )
    heading = ParagraphStyle('Heading', fontName='Helvetica-Bold', fontSize=16, leading=21,
                             textColor=DARK, spaceAfter=6)
    subheading = ParagraphStyle('Subheading', fontName='Helvetica-Bold', fontSize=10.5, leading=15,
                                textColor=DARK, spaceAfter=6)
    detail_label = ParagraphStyle('DetailLabel', fontName='Helvetica', fontSize=8, leading=12, textColor=GREY)
    detail_value = ParagraphStyle('DetailValue', fontName='Helvetica-Bold', fontSize=10.2, leading=15, textColor=DARK)
    body = ParagraphStyle('Body', fontName='Helvetica', fontSize=9, leading=13.5, textColor=DARK)
    white_title = ParagraphStyle('WhiteHeader', fontName='Helvetica-Bold', fontSize=9,
                                 leading=13, textColor=colors.white)
    small = ParagraphStyle('Small', fontName='Helvetica', fontSize=8.5, leading=12, textColor=GREY)
    center_small = ParagraphStyle('CenterSmall', parent=small, alignment=TA_CENTER)
    center_num = ParagraphStyle('CenterNum', fontName='Helvetica-Bold', fontSize=23, leading=30,
                                alignment=TA_CENTER, textColor=BRAND)
    center_unit = ParagraphStyle('CenterUnit', fontName='Helvetica', fontSize=9, leading=13,
                                 alignment=TA_CENTER, textColor=GREY)

    story = []
    logo = Path(logo_path) if logo_path is not None else Path(__file__).resolve().parent / 'assets' / 'sri_chaitanya_logo.png'
    if logo.exists():
        logo_obj = Image(str(logo), width=228, height=228 * 129 / 575)
        logo_obj.hAlign = 'LEFT'
        header_left = logo_obj
    else:
        header_left = Paragraph('<font color="#BF234C"><b>SRI CHAITANYA</b></font>', heading)
    hdr_right = Paragraph('<b>RESULT REPORT</b><br/><font size="8">ACADEMIC EVALUATION</font>',
                          ParagraphStyle('HeadRight', fontName='Helvetica', fontSize=10, leading=15,
                                         alignment=TA_RIGHT, textColor=DARK))
    hdr = Table([[header_left, hdr_right]], colWidths=[usable * .64, usable * .36], hAlign='CENTER')
    hdr.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(hdr)
    story.append(HRFlowable(width='100%', thickness=2, color=BRAND, spaceBefore=5, spaceAfter=17))

    exam_name = _text(payload.get('exam_type', 'EXAMINATION')).upper()
    story.append(Paragraph(f'{exam_name} Examination Result', heading))
    story.append(Paragraph('Student performance summary', small))
    story.append(Spacer(1, 11))

    def field(label: str, value: object):
        return [Paragraph(_text(label).upper(), detail_label),
                Paragraph(_text(value) if str(value or '').strip() else '-', detail_value)]

    detail_rows = [
        [field('Student Name', payload.get('student_name')), field('Roll Number', payload.get('roll_number'))],
        [field('Present Class', payload.get('class_name')), field('Exam Date', _date(payload.get('exam_date')))],
        [field('Paper Code', payload.get('paper_code')), field('Paper Version', payload.get('paper_version'))],
    ]
    school = payload.get('school')
    city = payload.get('school_city')
    if school or city:
        detail_rows.append([field('School', school), field('School City', city)])
    details = Table(detail_rows, colWidths=[usable / 2, usable / 2], hAlign='CENTER')
    details.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), FAINT),
        ('BOX', (0, 0), (-1, -1), .4, BORDER),
        ('LINEBEFORE', (1, 0), (1, -1), .5, BORDER),
        ('LINEBELOW', (0, 0), (-1, -2), .5, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
    ]))
    story.append(details)
    story.append(Spacer(1, 12))

    def score_card(label: str, value: str):
        return [Paragraph(value, center_num), Paragraph(label.upper(), center_unit)]

    hero = Table([[score_card('Marks Obtained', _num(total)),
                   score_card('Maximum Marks', _num(maximum)),
                   score_card('Percentage', f'{percentage:.2f}%')]],
                 colWidths=[usable/3]*3)
    hero.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), LIGHT),
        ('BOX', (0, 0), (-1, -1), 0.65, colors.HexColor('#EDC8D3')),
        ('LINEBEFORE', (1, 0), (-1, 0), 0.6, colors.HexColor('#EDC8D3')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
    ]))
    story.append(hero)
    story.append(Spacer(1, 15))
    story.append(Paragraph('Subjectwise Performance', subheading))

    headings = ['SUBJECT', 'OBTAINED', 'MAXIMUM', 'PERCENTAGE']
    table_rows = [[Paragraph(_text(x), white_title) for x in headings]]
    for subject, data in subjects.items():
        m = float(data.get('marks', 0))
        mx = float(data.get('maximum', 0))
        pct = f'{m / mx * 100:.1f}%' if mx else '-'
        table_rows.append([Paragraph(_text(subject), body), _num(m), _num(mx), pct])
    table_rows.append([
        Paragraph('TOTAL', ParagraphStyle('TotalTitle', parent=body, fontName='Helvetica-Bold')),
        _num(total), _num(maximum), f'{percentage:.2f}%',
    ])
    scores = Table(table_rows, colWidths=[usable * .46, usable * .18, usable * .18, usable * .18],
                   repeatRows=1, hAlign='CENTER')
    scores.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), DARK),
        ('BACKGROUND', (0, -1), (-1, -1), LIGHT),
        ('TEXTCOLOR', (0, 1), (-1, -1), DARK),
        ('FONTNAME', (1, 1), (-1, -1), 'Helvetica'),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LINEBELOW', (0, 0), (-1, -2), .4, BORDER),
        ('LINEBELOW', (0, -1), (-1, -1), 1.1, BRAND),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
    ]))
    story.append(scores)
    story.append(Spacer(1, 11))

    evaluations = payload.get('question_evaluation') or []
    if evaluations:
        status_counts = {}
        for question in evaluations:
            status = str(question.get('Status', ''))
            status_counts[status] = status_counts.get(status, 0) + 1
        summary = '    |    '.join(f'{label}: {status_counts[label]}'
                                   for label in ('Correct', 'Incorrect', 'Unattempted', 'Invalid', 'Bonus')
                                   if status_counts.get(label, 0))
        if summary:
            story.append(Paragraph('<b>Question summary</b>', subheading))
            story.append(Paragraph(_text(summary), body))
            story.append(Spacer(1, 7))
    story.append(Paragraph('This is a computer-generated examination result based on the evaluated OMR sheet.', small))

    def decoration(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(BORDER)
        canvas.setLineWidth(.6)
        canvas.line(margin, 35, page_w - margin, 35)
        canvas.setFont('Helvetica', 7.5)
        canvas.setFillColor(GREY)
        canvas.drawString(margin, 22, 'Sri Chaitanya  |  IIT-JEE  |  Medical  |  Foundation')
        canvas.drawRightString(page_w - margin, 22, f'Page {doc.page}')
        canvas.restoreState()

    doc.build(story, onFirstPage=decoration, onLaterPages=decoration)
    return out.getvalue()
