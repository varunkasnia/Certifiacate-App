import pandas as pd
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.units import inch
from datetime import datetime
from typing import List, Dict


def generate_csv(game_data: dict) -> BytesIO:
    """Generate CSV export of game results"""
    
    # Prepare data for DataFrame
    rows = []
    for player in game_data['players']:
        for answer in player.get('answers', []):
            rows.append({
                'Player Name': player['name'],
                'Question': answer['question_text'],
                'Player Answer': answer['answer'],
                'Correct Answer': answer['correct_answer'],
                'Is Correct': answer['is_correct'],
                'Time Taken (s)': round(answer['time_taken'], 2),
                'Points Earned': answer['points_earned']
            })
    
    df = pd.DataFrame(rows)
    
    # Convert to CSV
    buffer = BytesIO()
    df.to_csv(buffer, index=False, encoding='utf-8')
    buffer.seek(0)
    
    return buffer


def generate_excel(game_data: dict) -> BytesIO:
    """Generate Excel export with multiple sheets"""
    
    buffer = BytesIO()
    
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        # Summary sheet
        summary_data = {
            'Quiz Title': [game_data['quiz_title']],
            'Game PIN': [game_data['pin']],
            'Host': [game_data['host_name']],
            'Date': [game_data['created_at']],
            'Total Players': [len(game_data['players'])],
            'Total Questions': [game_data['total_questions']]
        }
        pd.DataFrame(summary_data).to_excel(writer, sheet_name='Summary', index=False)
        
        # Leaderboard sheet
        leaderboard = []
        for idx, player in enumerate(game_data['players'], 1):
            leaderboard.append({
                'Rank': idx,
                'Player Name': player['name'],
                'Total Score': player['score'],
                'Correct Answers': player['correct_count'],
                'Accuracy %': round((player['correct_count'] / game_data['total_questions']) * 100, 2)
            })
        pd.DataFrame(leaderboard).to_excel(writer, sheet_name='Leaderboard', index=False)
        
        # Detailed answers sheet
        detailed = []
        for player in game_data['players']:
            for answer in player.get('answers', []):
                detailed.append({
                    'Player': player['name'],
                    'Question #': answer['question_number'],
                    'Question': answer['question_text'],
                    'Player Answer': answer['answer'],
                    'Correct Answer': answer['correct_answer'],
                    'Correct': answer['is_correct'],
                    'Time (s)': round(answer['time_taken'], 2),
                    'Points': answer['points_earned']
                })
        pd.DataFrame(detailed).to_excel(writer, sheet_name='Detailed Results', index=False)
    
    buffer.seek(0)
    return buffer


def generate_pdf(game_data: dict) -> BytesIO:
    """Generate PDF report of game results"""
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()
    
    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1a1a1a'),
        spaceAfter=30
    )
    elements.append(Paragraph(f"Quiz Results: {game_data['quiz_title']}", title_style))
    elements.append(Spacer(1, 0.2 * inch))
    
    # Game Info
    info_style = styles['Normal']
    elements.append(Paragraph(f"<b>Game PIN:</b> {game_data['pin']}", info_style))
    elements.append(Paragraph(f"<b>Host:</b> {game_data['host_name']}", info_style))
    elements.append(Paragraph(f"<b>Date:</b> {game_data['created_at']}", info_style))
    elements.append(Paragraph(f"<b>Total Players:</b> {len(game_data['players'])}", info_style))
    elements.append(Spacer(1, 0.3 * inch))
    
    # Leaderboard
    elements.append(Paragraph("<b>Final Leaderboard</b>", styles['Heading2']))
    elements.append(Spacer(1, 0.1 * inch))
    
    leaderboard_data = [['Rank', 'Player Name', 'Score', 'Correct', 'Accuracy']]
    for idx, player in enumerate(game_data['players'], 1):
        accuracy = round((player['correct_count'] / game_data['total_questions']) * 100, 1)
        leaderboard_data.append([
            str(idx),
            player['name'],
            str(player['score']),
            f"{player['correct_count']}/{game_data['total_questions']}",
            f"{accuracy}%"
        ])
    
    leaderboard_table = Table(leaderboard_data, colWidths=[0.8*inch, 2.5*inch, 1.2*inch, 1.2*inch, 1.2*inch])
    leaderboard_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(leaderboard_table)
    
    # Build PDF
    doc.build(elements)
    buffer.seek(0)
    
    return buffer


def prepare_game_data_for_export(game_session, players, questions, answers) -> dict:
    """Prepare game data in a format suitable for export"""
    
    # Organize answers by player
    players_data = []
    for player in players:
        player_answers = [a for a in answers if a.player_id == player.id]
        
        correct_count = sum(1 for a in player_answers if a.is_correct)
        
        answers_detail = []
        for answer in player_answers:
            question = next((q for q in questions if q.id == answer.question_id), None)
            if question:
                answers_detail.append({
                    'question_number': question.order + 1,
                    'question_text': question.question_text,
                    'answer': answer.answer,
                    'correct_answer': question.correct_answer,
                    'is_correct': answer.is_correct,
                    'time_taken': answer.time_taken,
                    'points_earned': answer.points_earned
                })
        
        players_data.append({
            'name': player.name,
            'score': player.score,
            'correct_count': correct_count,
            'answers': answers_detail
        })
    
    # Sort by score
    players_data.sort(key=lambda x: x['score'], reverse=True)
    
    return {
        'quiz_title': game_session.quiz.title,
        'pin': game_session.pin,
        'host_name': game_session.host_name,
        'created_at': game_session.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        'total_questions': len(questions),
        'players': players_data
    }
