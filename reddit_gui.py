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

use_dropdown = st.toggle("\ud83d\udd7d Use subreddit dropdown instead of typing", value=True)

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
                flair_text = st.selectbox("\ud83c\udfaf Optional Flair", flair_options)
    except Exception as e:
        st.warning(f"\u26a0\ufe0f Could not load flairs: {e}")

# ==============================
# Helper: Count how many posts to a subreddit on a given day
# ==============================
def count_subreddit_posts_on_day(subreddit_name, target_date):
    scheduled_rows = post_tab.get_all_records()
    count = 0
    for row in scheduled_rows:
        if row.get("Subreddit", "").strip().lower() == subreddit_name.strip().lower():
            try:
                dt = datetime.strptime(row["Post Time (UTC)"], "%Y-%m-%d %H:%M:%S")
                if dt.date() == target_date:
                    count += 1
            except:
                continue
    return count

# ==============================
# Improved scheduling logic: skip overcrowded days
# ==============================
def get_next_best_time(subreddit_name):
    times = best_time_tab.get_all_records()
    now = datetime.utcnow()
    weekdays = {
        'Monday': 0, 'Tuesday': 1, 'Wednesday': 2,
        'Thursday': 3, 'Friday': 4, 'Saturday': 5, 'Sunday': 6
    }

    future_times = []

    for row in times:
        if row['Subreddit'].strip().lower() == subreddit_name.strip().lower():
            try:
                best_day = row['Best Day (UTC)']
                best_hour = int(row['Best Hour (UTC)'])

                target_weekday = weekdays[best_day]

                for week_ahead in range(4):  # Look ahead 4 weeks
                    days_until_target = (target_weekday - now.weekday() + 7) % 7 + (week_ahead * 7)
                    post_datetime = now + timedelta(days=days_until_target)
                    post_datetime = post_datetime.replace(hour=best_hour, minute=0, second=0, microsecond=0)

                    if post_datetime > now:
                        # Skip if 4 or more posts already scheduled
                        if count_subreddit_posts_on_day(subreddit_name, post_datetime.date()) < 4:
                            future_times.append(post_datetime)
            except:
                continue

    if future_times:
        future_times.sort()
        return future_times[0].strftime("%Y-%m-%d %H:%M:%S")
    return None

# ==============================
# Display next best post time
# ==============================
if subreddit:
    preview_time_utc = get_next_best_time(subreddit)
    if preview_time_utc:
        try:
            utc_time = datetime.strptime(preview_time_utc, "%Y-%m-%d %H:%M:%S")
            eastern = pytz.timezone('US/Eastern')
            utc = pytz.utc
            utc_time = utc.localize(utc_time)
            est_time = utc_time.astimezone(eastern)

            display_time = est_time.strftime("%A %B %d, %Y at %I:%M %p EST")
            post_count = count_subreddit_posts_on_day(subreddit, est_time.date())

            st.info(f"\ud83d\udcc5 Next best post time for **{subreddit.strip()}**: `{display_time}`")
            st.caption(f"\ud83d\udcca There are {post_count} post(s) already scheduled for this day to r/{subreddit.strip()}.")
        except Exception as e:
            st.warning(f"\u26a0\ufe0f Found time, but couldn't convert to EST: {e}")
    else:
        st.warning("\u26a0\ufe0f No scheduled best times found for that subreddit.")

# ==============================
# Schedule Post
# ==============================
if st.button("Schedule Post"):
    template = next((row for row in rows if row['Client Name'] == selected_client), None)

    if template and subreddit and title and url:
        scheduled_time = get_next_best_time(subreddit)
        if not scheduled_time:
            st.error("\u26a0\ufe0f No valid future best post time found for this subreddit.")
        else:
            new_row = [
                selected_client,              # A - Client Name
                subreddit.strip(),            # B - Subreddit
                title.strip(),                # C - Title
                url.strip(),                  # D - URL
                scheduled_time,               # E - Post Time (UTC)
                template['Reddit Username'],  # F - Reddit Username
                template['Reddit Password'],  # G - Reddit Password
                template['Client ID'],        # H - Client ID
                template['Client Secret'],    # I - Client Secret
                template['User Agent'],       # J - User Agent
                "FALSE",                      # K - Posted?
                flair_text                    # L - Flair Text
            ]
            post_tab.append_row(new_row, value_input_option="USER_ENTERED")
            st.success(f"\u2705 Post scheduled for {scheduled_time} UTC.")
    else:
        st.error("\u26a0\ufe0f Please fill all fields and make sure the client exists.")
