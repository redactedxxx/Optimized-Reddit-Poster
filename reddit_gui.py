import streamlit as st
import gspread
import random
import pytz
import praw
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta

# Google Sheets setup
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name(
    "/Users/natashacarter/Documents/redactedreddit/google-credentials.json", scope)
client = gspread.authorize(creds)

# Access tabs
sheet = client.open("Reddit Post Scheduler")
main_tab = sheet.worksheet("Sheet1")
post_tab = sheet.worksheet("Post Queue")
best_time_tab = sheet.worksheet("Best Time")

# UI Header
st.title("📬 Reddit Post Scheduler")

# Load client names
rows = main_tab.get_all_records()
client_names = list(sorted(set(row['Client Name'] for row in rows if row['Client Name'])))
selected_client = st.selectbox("Select Client", client_names)

subreddit = st.text_input("Subreddit", placeholder="e.g. r/RealGirls")
title = st.text_input("Title")
url = st.text_input("Link (RedGIF or other media URL)")

# Flair selection
flair_text = ""
if subreddit:
    try:
        # Pull credentials from selected client template
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

# Randomized best time picker
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
                today_weekday = now.weekday()

                days_ahead = (target_weekday - today_weekday + 7) % 7
                post_date = now + timedelta(days=days_ahead)
                post_datetime = post_date.replace(hour=best_hour, minute=0, second=0, microsecond=0)

                if post_datetime <= now:
                    post_datetime += timedelta(days=7)

                future_times.append(post_datetime)

            except Exception as e:
                print(f"Error parsing time for {subreddit_name}: {e}")

    if future_times:
        selected_time = random.choice(future_times)
        return selected_time.strftime("%Y-%m-%d %H:%M:%S")

    return None

# Show preview time
if subreddit:
    preview_time_utc = get_next_best_time(subreddit)
    if preview_time_utc:
        try:
            # Convert to Eastern Time for display
            utc_time = datetime.strptime(preview_time_utc, "%Y-%m-%d %H:%M:%S")
            eastern = pytz.timezone('US/Eastern')
            utc = pytz.utc
            utc_time = utc.localize(utc_time)
            est_time = utc_time.astimezone(eastern)

            display_time = est_time.strftime("%A %B %d, %Y at %I:%M %p EST")
            st.info(f"📅 Next best post time for **{subreddit.strip()}**: `{display_time}`")

        except Exception as e:
            st.warning(f"⚠️ Found time, but couldn't convert to EST: {e}")
    else:
        st.warning("⚠️ No scheduled best times found for that subreddit.")

# Schedule post
if st.button("Schedule Post"):
    template = next((row for row in rows if row['Client Name'] == selected_client), None)
    
    if template and subreddit and title and url:
        scheduled_time = get_next_best_time(subreddit)
        
        if not scheduled_time:
            st.error("⚠️ No valid future best post time found for this subreddit.")
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
            st.success(f"✅ Post scheduled for {scheduled_time} UTC.")
    else:
        st.error("⚠️ Please fill all fields and make sure the client exists.")
