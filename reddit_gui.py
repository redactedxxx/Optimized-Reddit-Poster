import streamlit as st
import gspread
import random
import pytz
import requests
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta

# Google Sheets setup
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["google"], scope)
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

# Load subreddit dropdown
best_times = best_time_tab.get_all_records()
subreddit_list = sorted(set(row["Subreddit"].strip() for row in best_times if row["Subreddit"].strip()))
subreddit = st.selectbox("Select Subreddit", subreddit_list)

# Persist input fields
if "title" not in st.session_state:
    st.session_state.title = ""
if "url" not in st.session_state:
    st.session_state.url = ""
if "uploaded_image" not in st.session_state:


title = st.text_input("Title", value=st.session_state.title, key="title")
url = st.text_input("Link (RedGIF or other media URL)", value=st.session_state.url, key="url")
uploaded_image = st.file_uploader("Optional: Upload an image to schedule", type=["jpg", "jpeg", "png"], key="uploaded_image")

# Upload image to Imgur
def upload_to_imgur(image_file):
    headers = {
        "Authorization": f"Client-ID {st.secrets['imgur']['client_id']}"
    }
    response = requests.post(
        "https://api.imgur.com/3/image",
        headers=headers,
        files={"image": image_file}
    )
    if response.status_code == 200:
        return response.json()["data"]["link"]
    else:
        st.error("⚠️ Failed to upload image to Imgur.")
        return None

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

# Show EST preview of best post time
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
            st.info(f"📅 Next best post time for **{subreddit.strip()}**: `{display_time}`")
        except Exception as e:
            st.warning(f"⚠️ Found time, but couldn't convert to EST: {e}")
    else:
        st.warning("⚠️ No scheduled best times found for that subreddit.")

# Schedule post
if st.button("Schedule Post"):
    template = next((row for row in rows if row['Client Name'] == selected_client), None)

    # Get final URL to post
    final_url = url.strip()
    if not final_url and uploaded_image:
        final_url = upload_to_imgur(uploaded_image)

    if template and subreddit and title and final_url:
        scheduled_time = get_next_best_time(subreddit)

        if not scheduled_time:
            st.error("⚠️ No valid future best post time found for this subreddit.")
        else:
            new_row = [
                selected_client,
                subreddit.strip(),
                title.strip(),
                final_url,
                scheduled_time,
                template['Reddit Username'],
                template['Reddit Password'],
                template['Client ID'],
                template['Client Secret'],
                template['User Agent'],
                "FALSE"
            ]
            post_tab.append_row(new_row, value_input_option="USER_ENTERED")
            st.success(f"✅ Post scheduled for {scheduled_time} UTC.")

            # Reset inputs
            st.session_state.title = ""
            st.session_state.url = ""
            st.session_state.uploaded_image = None

    else:
        st.error("⚠️ Please fill all fields and ensure either a link or image is provided.")
