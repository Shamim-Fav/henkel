import streamlit as st
import requests
import pandas as pd
import time
from bs4 import BeautifulSoup

# ========== CONFIG ==========
BASE_URL = "https://www.henkel.com/ajax/collection/en/34828-34828/queryresults/asJson"
HEADERS = {
    "accept": "application/json, text/javascript, */*; q=0.01",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    "x-requested-with": "XMLHttpRequest",
    "referer": "https://www.henkel.com/careers/jobs-and-application"
}

LOAD_COUNT = 10  # jobs per request
MAX_JOBS_DEFAULT = 50  # default max jobs to scrape

# ========== STREAMLIT UI ==========
st.title("Henkel Job Scraper")

# User inputs
selected_regions = st.multiselect(
    "Select Regions",
    options=["Europe", "Latin America", "North America", "Asia-Pacific"],
    default=["Europe"]
)

max_jobs = st.number_input("Maximum Jobs to Scrape (0 = All)", min_value=0, value=MAX_JOBS_DEFAULT, step=10)

if st.button("Fetch Jobs"):
    progress_bar = st.progress(0)
    with st.spinner("Scraping jobs... this may take a few minutes..."):
        all_jobs = []
        params = {
            "Career_Level_18682": "",
            "Functional_Area_18674": "",
            "Digital_1030670": "",
            "Locations_279384": ",".join(selected_regions) if selected_regions else "",
            "search_filter": "",
            "startIndex": 0,
            "loadCount": LOAD_COUNT,
            "ignoreDefaultFilterTags": "true"
        }

        while True:
            response = requests.get(BASE_URL, headers=HEADERS, params=params)
            data = response.json()
            jobs = data.get("results", [])

            if not jobs:
                break

            for job in jobs:
                job_link = "https://www.henkel.com" + job.get("link", "")
                job_id = job.get("id")
                title = job.get("title")
                location = job.get("location")

                # Fetch full job page for details
                job_response = requests.get(job_link, headers=HEADERS)
                soup = BeautifulSoup(job_response.text, "html.parser")

                # Description
                description_section = soup.find("div", class_="job-detail__content-description")
                description = description_section.get_text(separator="\n").strip() if description_section else None

                # Qualifications
                qualification_section = soup.find("div", class_="job-detail__content-qualification")
                qualifications = qualification_section.get_text(separator="\n").strip() if qualification_section else None

                # Contact Email
                contact_tag = soup.select_one("p.job-detail__content-contact a")
                contact_email = contact_tag.get("href").replace("mailto:", "") if contact_tag else None

                # Application Deadline
                deadline_tag = soup.find("strong", string="Application Deadline:")
                application_deadline = deadline_tag.find_next("span").get_text(strip=True) if deadline_tag else None

                # Job Center
                job_center_tag = soup.find("strong", string="Job-Center:")
                job_center_text = ""
                if job_center_tag:
                    span_tag = job_center_tag.find_next("span")
                    if span_tag:
                        link_tag = span_tag.find("a")
                        url = link_tag.get("href") if link_tag else ""
                        job_center_text = span_tag.get_text(separator=" ").strip()
                        if url:
                            job_center_text += f" ({url})"

                all_jobs.append({
                    "Job ID": job_id,
                    "Job Title": title,
                    "Location": location,
                    "Link": job_link,
                    "Description": description,
                    "Qualifications": qualifications,
                    "Contact Email": contact_email,
                    "Application Deadline": application_deadline,
                    "Job Center": job_center_text
                })

                if max_jobs and max_jobs > 0 and len(all_jobs) >= max_jobs:
                    break

            if max_jobs and max_jobs > 0 and len(all_jobs) >= max_jobs:
                break

            params["startIndex"] += LOAD_COUNT
            if params["startIndex"] >= data.get("resultsTotal", 0):
                break

            # Update progress
            progress_bar.progress(min(params["startIndex"] / max(data.get("resultsTotal", 1), 1), 1.0))
            time.sleep(0.5)

        progress_bar.empty()

        if all_jobs:
            st.success(f"Found {len(all_jobs)} jobs!")
            df = pd.DataFrame(all_jobs)
            st.dataframe(df)

            # Excel download
            df.to_excel("henkel_jobs.xlsx", index=False)
            with open("henkel_jobs.xlsx", "rb") as f:
                st.download_button("Download Excel", data=f, file_name="henkel_jobs.xlsx")
        else:
            st.warning("No jobs found.")

