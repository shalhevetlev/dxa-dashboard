import io
import json
import sqlite3
import datetime
import pandas as pd
import streamlit as st

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

DB_NAME = "dxa_complaints.db"

# --- Page Configuration ---
st.set_page_config(
    page_title="European Digital Banking Radar",
    page_icon="🏦",
    layout="wide"
)

# --- Database Helper Functions ---
def get_complaints_df():
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT * FROM complaints", conn)
    conn.close()
    return df

def calculate_leaderboard(df):
    if df.empty:
        return pd.DataFrame()
    
    # Filter for digital complaints with identified bank
    digital_df = df[(df['digital_complaint'] == 1) & (df['bank'].notna()) & (df['bank'] != 'None')].copy()
    
    if digital_df.empty:
        return pd.DataFrame()

    grouped = digital_df.groupby('bank').agg(
        digital_complaints=('id', 'count'),
        avg_severity=('severity', 'mean'),
        avg_relevance=('glassbox_relevance', 'mean'),
        blocked_customers=('customer_blocked', 'sum'),
        churn_signals=('churn_signal', 'sum'),
        support_contacts=('support_contacted', 'sum')
    ).reset_index()

    scores = []
    for _, row in grouped.iterrows():
        cnt = row['digital_complaints']
        sev = row['avg_severity'] or 0
        rel = row['avg_relevance'] or 0
        blocked_ratio = row['blocked_customers'] / cnt
        churn_ratio = row['churn_signals'] / cnt
        support_ratio = row['support_contacts'] / cnt

        pain = min(100, round((cnt * 15) + (sev * 4) + (blocked_ratio * 20) + (churn_ratio * 25), 1))
        opp = min(100, round((cnt * 12) + (rel * 6) + (blocked_ratio * 20) + (churn_ratio * 25) + (support_ratio * 10), 1))
        
        scores.append({
            'bank': row['bank'],
            'Opportunity Score': opp,
            'Pain Score': pain,
            'Digital Complaints': cnt,
            'Avg Severity': round(sev, 1),
            'Glassbox Rel.': round(rel, 1),
            'Blocked Users': int(row['blocked_customers']),
            'Churn Signals': int(row['churn_signals'])
        })

    result_df = pd.DataFrame(scores).sort_values(by='Opportunity Score', ascending=False)
    return result_df

# --- PDF Generation Function ---
def generate_pdf_report(company_name: str, bank_info: dict, top_journey: str) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('DocTitle', parent=styles['Heading1'], fontSize=18, leading=22, textColor=colors.HexColor('#1E3A8A'))
    subtitle_style = ParagraphStyle('DocSub', parent=styles['Normal'], fontSize=9, leading=11, textColor=colors.HexColor('#6B7280'))
    h2_style = ParagraphStyle('Heading2', parent=styles['Heading2'], fontSize=12, leading=15, textColor=colors.HexColor('#1E3A8A'), spaceBefore=10, spaceAfter=4)
    body_style = ParagraphStyle('Body', parent=styles['Normal'], fontSize=8, leading=10, textColor=colors.HexColor('#1F2937'))
    pitch_style = ParagraphStyle('PitchBody', parent=styles['Normal'], fontSize=8.5, leading=11, textColor=colors.HexColor('#1E3A8A'))
    table_header_style = ParagraphStyle('TH', parent=styles['Normal'], fontSize=8, leading=10, fontName='Helvetica-Bold', textColor=colors.white)
    table_body_style = ParagraphStyle('TB', parent=styles['Normal'], fontSize=7.5, leading=9.5, textColor=colors.HexColor('#1F2937'))
    table_meta_style = ParagraphStyle('TM', parent=styles['Normal'], fontSize=7.5, leading=9.5, fontName='Helvetica-Bold', textColor=colors.HexColor('#2563EB'))

    story = []

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT created_at, author, source, journey, issue_type, severity, raw_text
        FROM complaints
        WHERE bank = ? AND digital_complaint = 1
        ORDER BY created_at DESC
    """, (company_name,))
    rows = cursor.fetchall()
    conn.close()

    total_complaints = len(rows)

    # 1. Document Title & Header
    story.append(Paragraph(f"Glassbox Commercial Intelligence Report: {company_name}", title_style))
    story.append(Paragraph(f"Generated on: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Target Account Analysis", subtitle_style))
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#1E3A8A'), spaceAfter=10))

    # 2. Key Metrics Summary Table
    summary_data = [
        [
            Paragraph("<b>Opportunity Score</b>", table_body_style),
            Paragraph("<b>Pain Score</b>", table_body_style),
            Paragraph("<b>Total Issues</b>", table_body_style),
            Paragraph("<b>Blocked Users</b>", table_body_style),
            Paragraph("<b>Churn Risk Signals</b>", table_body_style)
        ],
        [
            Paragraph(f"<font size=10 color='#2563EB'><b>{bank_info.get('Opportunity Score', 0)} / 100</b></font>", table_body_style),
            Paragraph(f"<font size=10 color='#DC2626'><b>{bank_info.get('Pain Score', 0)} / 100</b></font>", table_body_style),
            Paragraph(f"<font size=10 color='#1E3A8A'><b>{total_complaints}</b></font>", table_body_style),
            Paragraph(f"<font size=10 color='#1F2937'><b>{bank_info.get('Blocked Users', 0)}</b></font>", table_body_style),
            Paragraph(f"<font size=10 color='#DC2626'><b>{bank_info.get('Churn Signals', 0)}</b></font>", table_body_style)
        ]
    ]
    summary_table = Table(summary_data, colWidths=[108, 108, 108, 108, 108])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F3F4F6')),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E5E7EB')),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 10))

    # 3. Recommended Sales Pitch Box
    story.append(Paragraph("🎯 Recommended Glassbox Commercial Pitch", h2_style))
    pitch_text = f"""
    <b>Primary Sales Angle for {company_name}:</b><br/>
    We detected critical customer friction specifically around <b>{top_journey.upper()}</b>. 
    Multiple users report being blocked from completing transactions or accessing accounts, leading to churn risk.<br/><br/>
    <b>Recommended Glassbox Solutions to Pitch:</b><br/>
    • <b>Session Replay & Struggle Analytics:</b> Pinpoint exact friction points during {top_journey}.<br/>
    • <b>Mobile & Web Crash Analytics:</b> Capture client-side exceptions and network failures in real time.<br/>
    • <b>Funnel Drop-Off Quantification:</b> Calculate lost revenue from abandonments during key journeys.
    """
    pitch_table = Table([[Paragraph(pitch_text, pitch_style)]], colWidths=[540])
    pitch_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#EFF6FF')),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#93C5FD')),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
    ]))
    story.append(pitch_table)
    story.append(Spacer(1, 12))

    # 4. Detailed Customer Feedback & Complaints Table
    story.append(Paragraph("📜 Customer Evidence & Incident Log", h2_style))

    if total_complaints == 0:
        story.append(Paragraph("No digital failure complaints recorded for this company.", body_style))
    else:
        table_data = [[
            Paragraph("Date / Time", table_header_style),
            Paragraph("Author", table_header_style),
            Paragraph("Source", table_header_style),
            Paragraph("Journey / Issue", table_header_style),
            Paragraph("Feedback Text", table_header_style)
        ]]

        for row in rows:
            created_at, author, source, journey, issue_type, severity, raw_text = row
            meta_text = f"<b>{journey or 'General'}</b><br/><font color='#6B7280'>{issue_type or 'Issue'}</font><br/><font color='#DC2626'>Sev: {severity}/10</font>"
            
            table_data.append([
                Paragraph(str(created_at or "N/A"), table_body_style),
                Paragraph(str(author or "Anonymous"), table_meta_style),
                Paragraph(str(source or "Web"), table_body_style),
                Paragraph(meta_text, table_body_style),
                Paragraph(str(raw_text or ""), table_body_style)
            ])

        complaints_table = Table(table_data, colWidths=[80, 85, 75, 100, 200])
        complaints_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1E3A8A')),
            ('ALIGN', (0,0), (-1,0), 'LEFT'),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E5E7EB')),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#F9FAFB')]),
            ('TOPPADDING', (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ]))
        story.append(complaints_table)

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes

# --- Dashboard Header ---
st.title("🏦 European Digital Banking Radar")
st.caption("AI-Powered Commercial Intelligence for Digital Experience Analytics (DXA)")

df = get_complaints_df()
leaderboard_df = calculate_leaderboard(df)

if leaderboard_df.empty:
    st.warning("No digital complaints found in the database. Please run the ingestion scripts first!")
else:
    # --- Top KPI Summary Cards ---
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Reviews Analyzed", len(df))
    with col2:
        st.metric("Digital Issues Detected", len(df[df['digital_complaint'] == 1]))
    with col3:
        top_opp_bank = leaderboard_df.iloc[0]['bank']
        top_opp_score = leaderboard_df.iloc[0]['Opportunity Score']
        st.metric("Top Opportunity", top_opp_bank, f"{top_opp_score} Score")
    with col4:
        churn_count = int(df['churn_signal'].sum()) if 'churn_signal' in df else 0
        st.metric("Competitor Churn Signals", churn_count)

    st.markdown("---")

    # --- Leaderboard Table ---
    st.subheader("🎯 Target Account Leaderboard")
    st.dataframe(
        leaderboard_df,
        column_config={
            "Opportunity Score": st.column_config.ProgressColumn(
                "Opportunity Score",
                help="Commercial value for Glassbox sales team",
                format="%f",
                min_value=0,
                max_value=100,
            ),
            "Pain Score": st.column_config.NumberColumn("Pain Score"),
        },
        use_container_width=True,
        hide_index=True
    )

    st.markdown("---")

    # --- Bank Deep Dive Section ---
    st.subheader("🔍 Bank Account Intelligence & Sales Angle")
    selected_bank = st.selectbox("Select Target Bank for Sales Intelligence:", leaderboard_df['bank'].unique())

    bank_reviews = df[(df['bank'] == selected_bank) & (df['digital_complaint'] == 1)]
    bank_info = leaderboard_df[leaderboard_df['bank'] == selected_bank].iloc[0].to_dict()

    top_journey = bank_reviews['journey'].mode()[0] if not bank_reviews.empty and 'journey' in bank_reviews and not bank_reviews['journey'].empty else "general app friction"

    d_col1, d_col2 = st.columns([1, 2])

    with d_col1:
        st.markdown(f"### **{selected_bank} Summary**")
        st.write(f"**Opportunity Score:** {bank_info['Opportunity Score']}/100")
        st.write(f"**Digital Pain Score:** {bank_info['Pain Score']}/100")
        st.write(f"**Glassbox Relevance:** {bank_info['Glassbox Rel.']}/10")
        st.write(f"**Blocked Customers:** {bank_info['Blocked Users']}")
        st.write(f"**Active Churn Signals:** {bank_info['Churn Signals']}")

        # Top failing journeys
        if not bank_reviews.empty and 'journey' in bank_reviews:
            top_journeys = bank_reviews['journey'].value_counts()
            st.markdown("**Top Failing Journeys:**")
            for j_name, j_count in top_journeys.items():
                st.write(f"• `{j_name}`: {j_count} issue(s)")

        st.markdown("<br/>", unsafe_allow_html=True)
        
        # PDF Report Download Button
        pdf_bytes = generate_pdf_report(selected_bank, bank_info, top_journey)
        st.download_button(
            label=f"📄 Download Full PDF Report for {selected_bank}",
            data=pdf_bytes,
            file_name=f"{selected_bank.replace(' ', '_')}_Glassbox_Intelligence.pdf",
            mime="application/pdf",
            use_container_width=True
        )

    with d_col2:
        st.markdown("### **🎯 Recommended Glassbox Sales Pitch**")
        
        pitch_box = f"""
        > **Primary Value Pitch for {selected_bank}:**
        > 
        > We detected critical digital friction specifically around **{top_journey.upper()}**. 
        > Multiple customers report being completely blocked from completing transactions or onboarding.
        >
        > **Recommended Glassbox Solutions to Pitch:**
        > * **Session Replay & Struggle Analytics:** Identify where users are freezing or experiencing validation errors.
        > * **Mobile App Crash & Error Analytics:** Uncover client-side issues and API latency during {top_journey}.
        > * **Funnel Drop-Off Analysis:** Quantify lost conversion revenue and customer friction in real-time.
        """
        st.markdown(pitch_box)

    # Raw Evidence List
    st.markdown("### 📜 Customer Evidence Feed")
    for _, r in bank_reviews.iterrows():
        author_display = r.get('author') or 'Anonymous'
        date_display = r.get('created_at') or 'N/A'
        
        with st.expander(f"[{r['source']}] [{date_display}] Author: {author_display} | Journey: {r['journey']} | Severity: {r['severity']}/10"):
            st.write(f"**Customer Feedback:** \"{r['raw_text']}\"")
            st.write(f"**Issue Type:** `{r['issue_type']}` | **Channel:** `{r['channel']}`")
            impacts = json.loads(r['business_impact']) if 'business_impact' in r and r['business_impact'] else []
            if impacts:
                st.write(f"**Business Impact Tags:** {', '.join(impacts)}")
