import streamlit as st
import pandas as pd
import re
from datetime import datetime, timedelta
from io import BytesIO

st.set_page_config(page_title="WhatsApp Work Hours", layout="centered")

st.title("🕒 WhatsApp Work Hours Calculator")
st.markdown("Upload your exported WhatsApp group chat (.txt) to calculate total hours worked per person.")

uploaded_file = st.file_uploader("📂 Upload WhatsApp .txt file", type=["txt"], key="whatsapp_upload_1")

# --- Helper Functions ---
def parse_custom_format(file_text):
    pattern = r"\[(\d{1,2}/\d{1,2}/\d{2,4}), (\d{1,2}:\d{2}:\d{2})(?:\u202f|\xa0)?([APM]+)\] (.*?): (.*)"
    records = []
    for line in file_text.splitlines():
        match = re.match(pattern, line)
        if match:
            date_str, time_str, ampm, name, message = match.groups()
            timestamp_str = f"{date_str} {time_str} {ampm}"
            for fmt in ("%m/%d/%y %I:%M:%S %p", "%m/%d/%Y %I:%M:%S %p"):
                try:
                    timestamp = datetime.strptime(timestamp_str, fmt)
                    records.append({
                        "name": name.strip(),
                        "timestamp": timestamp,
                        "message": message.strip().lower()
                    })
                    break
                except ValueError:
                    continue
    return pd.DataFrame(records)

def get_week_range(date):
    monday = date - timedelta(days=date.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday, f"{monday.strftime('%b %d')} - {sunday.strftime('%b %d')} {sunday.year}"

def calculate_hours(df):
    df = df[df['message'].str.contains(r'\bin\b|\bout\b|\blunch\b|\bback\b|\breturn\b', na=False)].copy()
    df['date'] = df['timestamp'].dt.date
    df['week'] = df['timestamp'].dt.isocalendar().week
    df['year'] = df['timestamp'].dt.isocalendar().year

    latest_weeks = df[['year', 'week']].drop_duplicates().sort_values(['year', 'week'], ascending=False).head(4)
    df = df.merge(latest_weeks, on=['year', 'week'])

    daily_records = []

    for (name, date), group in df.groupby(['name', 'date']):
        group = group.sort_values(by='timestamp')
        times = group['timestamp'].tolist()
        messages = group['message'].tolist()
        i = 0
        while i < len(messages) - 1:
            msg1 = messages[i]
            msg2 = messages[i + 1]
            # Clock In keywords: in, back, return
            # Clock Out keywords: out, lunch
            if any(x in msg1 for x in ['in', 'back', 'return']) and any(x in msg2 for x in ['out', 'lunch']):
                duration = times[i + 1] - times[i]
                clock_in = times[i].strftime('%I:%M %p')
                clock_out = times[i + 1].strftime('%I:%M %p')
                week_range = get_week_range(times[i])[2]
                daily_records.append({
                    'Name': name,
                    'Date': date.strftime('%b %d, %Y'),
                    'Week': week_range,
                    'Clock In': clock_in,
                    'Clock Out': clock_out,
                    'Hours Worked': round(duration.total_seconds() / 3600, 2)
                })
                i += 2
            else:
                i += 1

    daily_df = pd.DataFrame(daily_records)

    if not daily_df.empty:
        weekly_summary = (
            daily_df.groupby(['Name', 'Week'])['Hours Worked']
            .sum().reset_index()
            .rename(columns={'Hours Worked': 'Total Hours'})
        )
    else:
        weekly_summary = pd.DataFrame()

    return daily_df, weekly_summary

def get_last_week_data(daily_df):
    today = datetime.now().date()
    this_monday = today - timedelta(days=today.weekday())
    last_monday = this_monday - timedelta(days=7)
    last_sunday = last_monday + timedelta(days=6)

    last_week_df = daily_df[
        pd.to_datetime(daily_df['Date']).dt.date.between(last_monday, last_sunday)
    ]

    if not last_week_df.empty:
        total_hours = last_week_df.groupby("Name")["Hours Worked"].sum().reset_index()
        total_hours.rename(columns={"Hours Worked": "Total Hours This Week"}, inplace=True)
        last_week_df = last_week_df.merge(total_hours, on="Name")
        last_week_df["Total Hours This Week"] = last_week_df.groupby("Name")["Total Hours This Week"].transform(
            lambda x: [x.iat[0]] + [""] * (len(x) - 1)
        )

    return last_week_df, last_monday, last_sunday

def to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Sheet1')
    return output.getvalue()

# --- Main Execution ---
if uploaded_file:
    file_text = uploaded_file.read().decode("utf-8")
    df = parse_custom_format(file_text)

    if df.empty or "message" not in df.columns:
        st.error("❌ Format issue: Could not extract messages. Please upload a valid WhatsApp group .txt file.")
    else:
        daily_df, weekly_df = calculate_hours(df)

        if daily_df.empty:
            st.warning("⚠️ No valid IN/OUT pairs found.")
        else:
            st.success("✅ Successfully processed the chat file!")

            st.subheader("🧾 Daily Work Log")
            st.dataframe(daily_df)
            st.download_button("📥 Download Daily Logs (Excel)",
                               data=to_excel(daily_df),
                               file_name="Daily Work Log.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

            st.subheader("📊 Weekly Total Hours per Person")
            st.dataframe(weekly_df)
            st.download_button("📥 Download Weekly Summary (Excel)",
                               data=to_excel(weekly_df),
                               file_name="Weekly Total Hours Summary.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

            last_week_df, last_monday, last_sunday = get_last_week_data(daily_df)
            if not last_week_df.empty:
                title = f"{last_monday.strftime('%b %d')} - {last_sunday.strftime('%b %d')} {last_sunday.year} WORKDAY TIMESHEET"
                st.subheader(f"📆 {title}")
                st.dataframe(last_week_df)

                st.download_button(f"📥 Download {title}",
                                   data=to_excel(last_week_df),
                                   file_name=f"{title}.xlsx",
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
