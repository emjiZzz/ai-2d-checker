from pathlib import Path
from typing import Any

from ...logger import logger


class PDFComplianceExporter:
    """
    Generates standard engineering compliance audit reports in PDF format using ReportLab
    with fallback options if dependencies are missing.
    """
    @staticmethod
    def generate_pdf(output_path: Path, session: Any, drawing: Any, standard: Any, violations: list[Any]) -> Path:
        logger.info(f"Generating PDF compliance report to: {output_path}")
        
        # Enforce parent directories
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
            from reportlab.platypus import (
                PageBreak,
                Paragraph,
                SimpleDocTemplate,
                Spacer,
                Table,
                TableStyle,
            )
            
            doc = SimpleDocTemplate(str(output_path), pagesize=letter, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
            styles = getSampleStyleSheet()
            
            # Custom styled palette (harmonious dark/light engineering branding)
            title_style = ParagraphStyle(
                'TitleStyle',
                parent=styles['Heading1'],
                fontSize=20,
                textColor=colors.HexColor('#0f172a'),
                spaceAfter=15
            )
            
            h2_style = ParagraphStyle(
                'H2Style',
                parent=styles['Heading2'],
                fontSize=14,
                textColor=colors.HexColor('#1e293b'),
                spaceBefore=12,
                spaceAfter=8
            )
            
            body_style = ParagraphStyle(
                'BodyStyle',
                parent=styles['BodyText'],
                fontSize=10,
                textColor=colors.HexColor('#334155'),
                leading=14
            )
            
            bold_style = ParagraphStyle(
                'BoldStyle',
                parent=body_style,
                fontName='Helvetica-Bold'
            )

            story = []
            
            # 1. Header Banner
            story.append(Paragraph("AI-2D-CHECKER COMPLIANCE AUDIT", title_style))
            story.append(Paragraph(f"<b>Drawing:</b> {drawing.file_name if drawing else 'Unknown'}", body_style))
            story.append(Paragraph(f"<b>Standard Guide:</b> {standard.name if standard else 'Default Engineering Standard'}", body_style))
            story.append(Paragraph(f"<b>Compliance Score:</b> {session.compliance_score}%", bold_style))
            story.append(Paragraph(f"<b>Confidence Level:</b> {session.confidence_score}%", body_style))
            story.append(Paragraph(f"<b>Execution Completed:</b> {session.completed_at.isoformat() if session.completed_at else 'N/A'}", body_style))
            story.append(Spacer(1, 15))
            
            # 2. Executive Summary
            story.append(Paragraph("Executive Summary", h2_style))
            summary_text = (
                f"This compliance document serves as the formal record of design evaluation for "
                f"the engineering sheet <b>'{drawing.file_name if drawing else 'unknown'}'</b>. "
                f"The compliance score of <b>{session.compliance_score}%</b> was computed by running "
                f"integrated CAD geometry heuristics and AI grounding vision validation loops. "
                f"A total of <b>{len(violations)} infractions</b> were detected across drawing layers."
            )
            story.append(Paragraph(summary_text, body_style))
            story.append(Spacer(1, 15))
            
            # 3. Violations Listing
            story.append(Paragraph("Detailed Violations Register", h2_style))
            if not violations:
                story.append(Paragraph("No compliance violations were detected for this drawing sheet.", body_style))
            else:
                # Build standard violations grid
                data = [["ID", "Layer", "Severity", "Description", "Confidence"]]
                for idx, v in enumerate(violations):
                    severity = getattr(v, "severity", "medium").upper()
                    layer = getattr(v, "layer", "0")
                    desc = getattr(v, "description", "")
                    conf = f"{getattr(v, 'confidence', 1.0) * 100:.0f}%"
                    data.append([f"V-{idx+1}", layer, severity, desc[:50] + "...", conf])
                
                table = Table(data, colWidths=[40, 80, 70, 260, 60])
                table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e293b')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 10),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8fafc')),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
                    ('FONTSIZE', (0, 1), (-1, -1), 8),
                ]))
                story.append(table)
            
            doc.build(story)
            logger.info("Successfully generated ReportLab PDF.")
            
        except ImportError:
            logger.warning("ReportLab is not installed. Generating highly formatted, resilient HTML-based PDF fallback wrapper.")
            # Resilient plain text/HTML layout fallback in case ReportLab is not available
            fallback_text = f"""==================================================
AI-2D-CHECKER COMPLIANCE AUDIT
==================================================
Drawing File: {drawing.file_name if drawing else 'Unknown'}
Standard Code: {standard.name if standard else 'Standard'}
Compliance score: {session.compliance_score}%
Confidence score: {session.confidence_score}%
Violations count: {len(violations)}

DETAILED REGISTER OF DETECTED INFRACTIONS:
"""
            for idx, v in enumerate(violations):
                fallback_text += f"- [V-{idx+1}] LAYER: {getattr(v, 'layer', '0')} | SEVERITY: {getattr(v, 'severity', 'medium').upper()} | DESC: {getattr(v, 'description', '')}\n"
            
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(fallback_text)
                
        return output_path
