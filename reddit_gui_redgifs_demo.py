import streamlit as st
import gspread
import random
import pytz
import requests
from bs4 import BeautifulSoup
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta

# Setup Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["google"], scope)
client = gspread.authorize(creds)

# Access tabs
sheet = client.open("Reddit Post Scheduler")
main_tab = sheet.worksheet("Sheet1")
post_tab = sheet.worksheet("Post Queue")
best_time_tab = sheet.worksheet("Best Time")

# Hardcoded demo client: Natasha
client_name = "Natasha"
template = next((row for row in main_tab.get_all_records() if row['Client Name'] == client_name), None)

# Title
st.title("🎬 RedGIFs Scheduler Demo (Natasha Only)")

# Load subreddit list
best_times = best_time_tab.get_all_records()
subreddit_list = sorted(set(row["Subreddit"].strip() for row in best_times if row["Subreddit"].strip()))
subreddit = st.selectbox("Select Subreddit", subreddit_list)

title = st.text_input("Title (you write it)")
url = st.text_input("Selected RedGIFs Video URL")

# 🔍 Scrape RedGIFs user profile
@st.cache_data(ttl=300)
def get_redgifs_videos(username):
    redgifs_url = f"https://www.redgifs.com/users/{username}"
    resp = requests.get(redgifs_url)
    soup = BeautifulSoup(resp.text, "html.parser")
    previews = []
    for a in soup.find_all("a", href=True):
        if "/watch/" in a["href"]:
            thumb = a.find("img")
            if thumb and "src" in thumb.attrs:
                previews.append({
                    "thumb": thumb["src"],
                    "link": "https://www.redgifs.com" + a["href"]
                })
    return previews

# Get Natasha’s RedGIFs
redgifs_username = "knottynatasha"
videos = get_redgifs_videos(redgifs_username)

# Show clickable thumbnails
st.markdown("### 🔻 Select a video to autofill the link:")
cols = st.columns(3)
for i, video in enumerate(videos[:9]):
    with cols[i % 3]:
        if st.button(f"Select", key=video["link"]):
            st.session_state["selected_redgifs_url"] = video["link"]
        st.image(video["thumb"], use_column_width=True)

# Fill URL input if a video was selected
if "selected_redgifs_url" in st.session_state:
    url = st.session_state["selected_redgifs_url"]
    st.success(f"Selected: {url}")

# Helper to get best time
def get_next_best_time(subreddit_name):
    now = datetime.utcnow()
    weekdays = {'Monday': 0, 'Tuesday': 1, 'Wednesday': 2,
                'Thursday': 3, 'Friday': 4, 'Saturday': 5, 'Sunday': 6}
    times = best_time_tab.get_all_records()
    future_times = []

    for row in times:
        if row['Subreddit'].strip().lower() == subreddit_name.strip().lower():
            try:
                best_day = row['Best Day (UTC)']
                best_hour = int(row['Best Hour (UTC)'])
                target_weekday = weekdays[best_day]
                days_ahead = (target_weekday - now.weekday() + 7) % 7
                post_date = now + timedelta(days=days_ahead)
                post_time = post_date.replace(hour=best_hour, minute=0, second=0, microsecond=0)
                if post_time <= now:
                    post_time += timedelta(days=7)
                future_times.append(post_time)
            except:
                continue

    if future_times:
        return random.choice(future_times).strftime("%Y-%m-%d %H:%M:%S")
    return None

# Schedule post
if st.button("✅ Schedule Post Now"):
    if template and subreddit and title and url:
        scheduled_time = get_next_best_time(subreddit)
        if scheduled_time:
            new_row = [
                client_name,
                subreddit,
                title.strip(),
                url.strip(),
                template['Reddit Username'],
                template['Client ID'],
                template['Client Secret'],
                template['User Agent'],
                template['Reddit Password'],
                f"script by u/{template['Reddit Username']}",
                scheduled_time,
                "FALSE"
            ]
            post_tab.append_row(new_row, value_input_option="USER_ENTERED")
            st.success(f"✅ Post scheduled for {scheduled_time} UTC.")
        else:
            st.error("No available time for that subreddit.")
    else:
        st.error("Please fill all fields or select a preview.")
