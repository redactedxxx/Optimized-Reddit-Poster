import streamlit as st
import gspread
import random
import pytz
import praw
import os
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta

# ==============================
# Google Sheets setup (cloud + local)
# ==============================
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

try:
    creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["google"], scope)
except Exception:
    creds = ServiceAccountCredentials.from_json_keyfile_name(
        os.path.expanduser("~/Documents/redactedreddit/google-credentials.json"), scope)

client = gspread.authorize(creds)

# ==============================
# Google Sheets tabs
# ==============================
sheet = client.open("Reddit Post Scheduler")
main_tab = sheet.worksheet("Sheet1")
post_tab = sheet.worksheet("Post Queue")
best_time_tab = sheet.worksheet("Best Time")

# ==============================
# Helper: Count how many posts to a subreddit on a given day
# ==============================
def count_subreddit_posts_on_day(subreddit_name, target_date, cached_rows):
    count = 0
    for row in cached_rows:
        if row.get("Subreddit", "").strip().lower() == subreddit_name.strip().lower():
            try:
                dt = datetime.strptime(row["Post Time (UTC)"], "%Y-%m-%d %H:%M:%S")
                if dt.date() == target_date:
                    count += 1
            except:
                continue
    return count

# ==============================
# UI Header
# ==============================
st.title("📬 Reddit Post Scheduler")

rows = main_tab.get_all_records()
client_names = list(sorted(set(row['Client Name'] for row in rows if row['Client Name'])))
selected_client = st.selectbox("Select Client", client_names)

# ==============================
# Subreddit dropdown or manual entry
# ==============================
subreddit_rows = best_time_tab.get_all_records()
subreddit_options = sorted(set(
    row['Subreddit'].strip() for row in subreddit_rows if row.get('Subreddit', '').strip()
))

use_dropdown = st.toggle("🔽 Use subreddit dropdown instead of typing", value=True)

if use_dropdown:
    subreddit = st.selectbox("Subreddit", subreddit_options)
else:
    subreddit = st.text_input("Subreddit", placeholder="e.g. r/RealGirls")

title = st.text_input("Title")
url = st.text_input("Link (RedGIF or other media URL)")

# ==============================
# Flair dropdown (if subreddit entered)
# ==============================
flair_text = ""
if subreddit:
    try:
        template = next((row for row in rows if row['Client Name'] == selected_client), None)
        if template:
            reddit = praw.Reddit(
                client_id=template["Client ID"],
                client_secret=template["Client Secret"],
                password=template["Reddit Password"],
                user_agent=template["User Agent"],
                username=template["Reddit Username"]
            )
            sub = reddit.subreddit(subreddit.replace("r/", "").strip())
            flair_templates = sub.flair.link_templates
            flair_options = [f["text"] for f in flair_templates]
            if flair_options:
                flair_text = st.selectbox("🎯 Optional Flair", flair_options)
    except Exception as e:
        st.warning(f"⚠️ Could not load flairs: {e}")

# ==============================
# Improved scheduling logic: skip overcrowded days
# ==============================
def get_next_best_time(subreddit_name, best_times):
    now = datetime.utcnow()
    weekdays = {
        'Monday': 0, 'Tuesday': 1, 'Wednesday': 2,
        'Thursday': 3, 'Friday': 4, 'Saturday': 5, 'Sunday': 6
    }

    future_times = []

    for row in best_times:
        if row['Subreddit'].strip().lower() == subreddit_name.strip().lower():
            try:
                best_day = row['Best Day (UTC)']
                best_hour = int(row['Best Hour (UTC)'])

                target_weekday = weekdays[best_day]

                for week_ahead in range(4):
                    days_until_target = (target_weekday - now.weekday() + 7) % 7 + (week_ahead * 7)
                    post_datetime = now + timedelta(days=days_until_target)
                    post_datetime = post_datetime.replace(hour=best_hour, minute=0, second=0, microsecond=0)

                    if post_datetime > now:
                        future_times.append(post_datetime)
            except:
                continue

    if future_times:
        future_times.sort()
        return future_times
    return []

# ==============================
# Display next best post time
# ==============================
if subreddit:
    preview_options = get_next_best_time(subreddit, subreddit_rows)
    if preview_options:
        try:
            utc_time = preview_options[0]
            eastern = pytz.timezone('US/Eastern')
            utc = pytz.utc
            utc_time = utc.localize(utc_time) if utc_time.tzinfo is None else utc_time
            est_time = utc_time.astimezone(eastern)

            display_time = est_time.strftime("%A %B %d, %Y at %I:%M %p EST")
            st.info(f"📅 Next best post time for **{subreddit.strip()}**: `{display_time}`")
        except Exception as e:
            st.warning(f"⚠️ Found time, but couldn't convert to EST: {e}")
    else:
        st.warning("⚠️ No scheduled best times found for that subreddit.")

# ==============================
# Schedule Post
# ==============================
if st.button("Schedule Post"):
    template = next((row for row in rows if row['Client Name'] == selected_client), None)

    if template and subreddit and title and url:
        best_time_options = get_next_best_time(subreddit, subreddit_rows)
        if not best_time_options:
            st.error("⚠️ No valid future best post time found for this subreddit.")
        else:
            scheduled_time = best_time_options[0].strftime("%Y-%m-%d %H:%M:%S")
            new_row = [
                selected_client,
                subreddit.strip(),
                title.strip(),
                url.strip(),
                scheduled_time,
                template['Reddit Username'],
                template['Reddit Password'],
                template['Client ID'],
                template['Client Secret'],
                template['User Agent'],
                "FALSE",
                flair_text
            ]
            post_tab.append_row(new_row, value_input_option="USER_ENTERED")
            st.success(f"✅ Post scheduled for {scheduled_time} UTC.")
    else:
        st.error("⚠️ Please fill all fields and make sure the client exists.")

# ==============================
# 🧩 Schedule all unscheduled posts
# ==============================
if st.button("🧩 Schedule All Unscheduled Posts"):
    all_rows = post_tab.get_all_records()
    best_times = best_time_tab.get_all_records()
    headers = post_tab.row_values(1)
    time_col = headers.index("Post Time (UTC)") + 1
    row_offset = 2
    count = 0
    used_times = set()
    scheduled_rows = all_rows

    # Correct: track actual row number in sheet
    unscheduled = []
    for idx, row in enumerate(all_rows):
        if not row.get("Post Time (UTC)", "").strip():
            unscheduled.append((idx + row_offset, row))

    for sheet_row_idx, row in unscheduled:
        subreddit = row.get("Subreddit", "").strip()
        if not subreddit:
            continue

        best_time_options = get_next_best_time(subreddit, best_times)
        for best_time_dt in best_time_options:
            best_time_str = best_time_dt.strftime("%Y-%m-%d %H:%M:%S")
            if best_time_str not in used_times:
                if count_subreddit_posts_on_day(subreddit, best_time_dt.date(), scheduled_rows) < 4:
                    post_tab.update_cell(sheet_row_idx, time_col, best_time_str)
                    used_times.add(best_time_str)
                    count += 1
                    break
        else:
            st.warning(f"⚠️ No available time found for row {sheet_row_idx} (subreddit: {subreddit})")

    st.success(f"✅ Scheduled {count} unscheduled post(s) with unique global times.")
