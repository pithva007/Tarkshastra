"""
PDF Report Generator for TS-11 Stampede Predictor
Generates incident reports when CRITICAL alerts fire.
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
import os
from datetime import datetime
from pathlib import Path

REPORTS_DIR = Path("reports")
REPORTS_DIR.mkdir(exist_ok=True)

def generate_alert_report(
    alert_id: str,
    corridor: str,
    cpi: float,
    flow_rate: float,
    transport_burst: float,
    chokepoint_density: float,
    surge_type: str,
    ttb_minutes: float,
    ml_confidence: int,
    historical_data: list = None
) -> str:
    """Generate PDF incident report.
    Returns file path of generated PDF."""
    
    filename = f"reports/alert_{alert_id}.pdf"
    doc = SimpleDocTemplate(
        filename,
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm
    )
    
    story = []
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=colors.HexColor('#DC2626'),
        spaceAfter=6,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#6B7280'),
        alignment=TA_CENTER,
        spaceAfter=4
    )
    
    section_style = ParagraphStyle(
        'Section',
        parent=styles['Heading2'],
        fontSize=11,
        textColor=colors.HexColor('#1F2937'),
        spaceBefore=12,
        spaceAfter=6,
        fontName='Helvetica-Bold'
    )
    
    body_style = ParagraphStyle(
        'Body',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#374151'),
        spaceAfter=4
    )
    
    critical_style = ParagraphStyle(
        'Critical',
        parent=styles['Normal'],
        fontSize=12,
        textColor=colors.HexColor('#DC2626'),
        fontName='Helvetica-Bold',
        alignment=TA_CENTER,
        spaceAfter=6
    )
    
    # Title
    story.append(Paragraph("STAMPEDE PREDICTOR — INCIDENT ALERT", title_style))
    story.append(Paragraph("Gujarat Pilgrimage Safety System — TS-11", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#DC2626')))
    story.append(Spacer(1, 0.3*cm))
    
    # Critical status banner
    story.append(Paragraph("⚠ CRITICAL ALERT — IMMEDIATE ACTION REQUIRED", critical_style))
    story.append(Spacer(1, 0.3*cm))
    
    # Alert metadata table
    now = datetime.now().strftime("%d %b %Y, %I:%M %p IST")
    meta_data = [
        ["Alert ID", alert_id],
        ["Generated At", now],
        ["Corridor", corridor],
        ["Surge Type", surge_type],
        ["Status", "CRITICAL — ACTION REQUIRED"],
    ]
    
    meta_table = Table(meta_data, colWidths=[4*cm, 12*cm])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (0,-1), colors.HexColor('#F3F4F6')),
        ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 10),
        ('TEXTCOLOR', (0,0), (0,-1), colors.HexColor('#374151')),
        ('TEXTCOLOR', (1,4), (1,4), colors.HexColor('#DC2626')),
        ('FONTNAME', (1,4), (1,4), 'Helvetica-Bold'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#D1D5DB')),
        ('PADDING', (0,0), (-1,-1), 6),
        ('ROWBACKGROUNDS', (0,0), (-1,-1), [colors.HexColor('#F9FAFB'), colors.white]),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 0.4*cm))
    
    # Current readings section
    story.append(Paragraph("CURRENT READINGS", section_style))
    
    readings_data = [
        ["Metric", "Value", "Status"],
        ["Corridor Pressure Index (CPI)", f"{cpi:.3f}", "CRITICAL" if cpi >= 0.85 else "WARNING"],
        ["Flow Rate", f"{int(flow_rate):,} pax/min", "—"],
        ["Transport Burst Factor", f"{transport_burst:.2f}", "—"],
        ["Chokepoint Density", f"{chokepoint_density:.2f}", "—"],
        ["Predicted Time to Breach", f"{int(ttb_minutes)} min {int((ttb_minutes%1)*60)} sec", "URGENT"],
        ["ML Confidence", f"{ml_confidence}%", "High"],
    ]
    
    readings_table = Table(readings_data, colWidths=[7*cm, 5*cm, 4*cm])
    readings_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1F2937')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 10),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#D1D5DB')),
        ('PADDING', (0,0), (-1,-1), 6),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor('#F9FAFB'), colors.white]),
        ('TEXTCOLOR', (2,1), (2,1), colors.HexColor('#DC2626')),
        ('FONTNAME', (2,1), (2,1), 'Helvetica-Bold'),
        ('TEXTCOLOR', (2,5), (2,5), colors.HexColor('#DC2626')),
        ('FONTNAME', (2,5), (2,5), 'Helvetica-Bold'),
    ]))
    story.append(readings_table)
    story.append(Spacer(1, 0.4*cm))
    
    # Required actions per agency
    story.append(Paragraph("REQUIRED ACTIONS — ALL AGENCIES", section_style))
    
    agency_actions = {
        "POLICE": {
            "unit": f"{corridor} Police Station",
            "action": "Deploy officers to Choke Point B immediately. Estimated crowd: 4,200 pax. ETA needed: 8 min.",
            "priority": "CRITICAL"
        },
        "TEMPLE TRUST": {
            "unit": f"{corridor} Temple Authority", 
            "action": "Activate darshan hold at inner gate NOW. Redirect overflow pilgrims to Queue C.",
            "priority": "CRITICAL"
        },
        "GSRTC TRANSPORT": {
            "unit": "Zone Transport Control",
            "action": "Hold ALL incoming buses at 3km checkpoint. Do not dispatch additional vehicles.",
            "priority": "CRITICAL"
        }
    }
    
    for agency, info in agency_actions.items():
        agency_data = [
            [f"{agency} — {info['unit']}", ""],
            ["Required Action:", info["action"]],
            ["Priority:", info["priority"]],
            ["Response Window:", "90 seconds from alert"],
        ]
        
        agency_table = Table(agency_data, colWidths=[4*cm, 12*cm])
        agency_table.setStyle(TableStyle([
            ('SPAN', (0,0), (-1,0)),
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#7F1D1D')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTNAME', (0,1), (0,-1), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 9),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#D1D5DB')),
            ('PADDING', (0,0), (-1,-1), 6),
            ('BACKGROUND', (0,1), (-1,-1), colors.HexColor('#FEF2F2')),
            ('TEXTCOLOR', (1,2), (1,2), colors.HexColor('#DC2626')),
            ('FONTNAME', (1,2), (1,2), 'Helvetica-Bold'),
        ]))
        story.append(agency_table)
        story.append(Spacer(1, 0.25*cm))
    
    # Historical context
    if historical_data:
        story.append(Paragraph("HISTORICAL CONTEXT", section_style))
        hist_rows = [["Year", "Peak CPI", "Surge Type", "Resolution"]]
        for h in historical_data[:3]:
            hist_rows.append([
                str(h.get("year", "")),
                str(h.get("peak_cpi", "")),
                h.get("surge_type", ""),
                f"{h.get('resolution_time_minutes',0)} min"
            ])
        
        hist_table = Table(hist_rows, colWidths=[3*cm, 3*cm, 5*cm, 5*cm])
        hist_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1F2937')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 9),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#D1D5DB')),
            ('PADDING', (0,0), (-1,-1), 5),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor('#F9FAFB'), colors.white]),
        ]))
        story.append(hist_table)
    
    # Footer
    story.append(Spacer(1, 0.5*cm))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#D1D5DB')))
    story.append(Paragraph(
        f"Auto-generated by Stampede Window Predictor — TS-11 | Gujarat Pilgrimage Safety System | {now}",
        ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontSize=8,
            textColor=colors.HexColor('#9CA3AF'),
            alignment=TA_CENTER
        )
    ))
    
    doc.build(story)
    print(f"[PDF] Generated: {filename}")
    return filename