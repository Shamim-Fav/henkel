import streamlit as st
import requests
import pandas as pd
import time
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

# ========== CONFIG ==========
BASE_URL = "https://www.henkel.com/ajax/collection/en/34828-34828/queryresults/asJson"
HEADERS = {
    "accept": "application/json, text/javascript, */*; q=0.01",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    "x-requested-with": "XMLHttpRequest",
    "referer": "https://www.henkel.com/careers/jobs-and-application"
}

LOAD_COUNT = 10        # jobs per request
MAX_JOBS_DEFAULT = 50  # default max jobs to scrape
MAX_THREADS = 10       # number of parallel requests
MAX_RETRIES = 3        # retry attempts for failed requests
RETRY_DELAY = 2        # seconds to wait between retries

# ========== STREAMLIT UI ==========
st.title("💼 Henkel Job Scraper")

selected_regions = st.multiselect(
    "Select Regions",
    options=["Europe", "Latin America", "North America", "Asia-Pacific"],
    default=["Europe"]
)

max_jobs = st.number_input("Maximum Jobs to Scrape (0 = All)", min_value=0, value=MAX_JOBS_DEFAULT, step=10)

def generate_slug(company, job_title, location):
    """Generate slug from company, job title, and first two parts of location."""
    location_parts = location.split(",")[:2]  # first two parts
    parts = [company, job_title] + [part.strip() for part in location_parts]
    slug = "-".join(parts).lower().replace(" ", "-")
    return slug

def fetch_job_details(job):
    """Fetch individual job page and parse details with retry mechanism and fixed Company."""
    job_link = "https://www.henkel.com" + job.get("link", "")
    job_id = job.get("id")
    title = job.get("title")
    location = job.get("location")

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            job_response = requests.get(job_link, headers=HEADERS, timeout=10)
            job_response.raise_for_status()
            soup = BeautifulSoup(job_response.text, "html.parser")

            # Description as HTML
            description_section = soup.find("div", class_="job-detail__content-description")
            description = str(description_section) if description_section else None

            # Qualifications (plain text for now)
            qualification_section = soup.find("div", class_="job-detail__content-qualification")
            qualifications = qualification_section.get_text(separator="\n").strip() if qualification_section else None

            # Contact Email
            contact_tag = soup.select_one("p.job-detail__content-contact a")
            contact_email = contact_tag.get("href").replace("mailto:", "") if contact_tag else None

            # Application Deadline
            deadline_tag = soup.find("strong", string="Application Deadline:")
            application_deadline = deadline_tag.find_next("span").get_text(strip=True) if deadline_tag else None

            # Job Center (Industry)
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

            # Categories
            job_department = None
            job_function = None
            job_type = None
            job_nature = None
            job_location = None

            for span in soup.select("span.category"):
                svg = span.find("svg")
                if svg:
                    svg_class = svg.get("class", [])
                    text = span.get_text(strip=True)
                    if "a-icon--tag" in svg_class:
                        if not job_department:
                            job_department = text
                        else:
                            job_function = text
                    elif "a-icon--maps" in svg_class:
                        job_location = text  # full location
                    elif "a-icon--clock" in svg_class:
                        job_type = text
                    elif "a-icon--doc-inv" in svg_class:
                        job_nature = text

            # Application link
            apply_link_tag = soup.select_one("a.job-detail__apply-now")
            apply_link = apply_link_tag.get("href") if apply_link_tag else None

            # Generate slug
            slug = generate_slug("Henkel", title, job_location or location)

            return {
                "Name": title,
                "Location": job_location or location,
                "Company": "Henkel AG & Co. KGaA",
                "Description": description,
                "Level": job_type,
                "Type": job_nature,
                "Deadline": application_deadline,
                "Industry": job_center_text,
                "Department": job_department,
                "Function": job_function,
                "Apply URL": apply_link,
                "Slug": slug
            }

        except Exception as e:
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
            else:
                return {"Name": title, "Error": f"Failed after {MAX_RETRIES} attempts: {str(e)}"}

# ========== MAIN SCRAPER LOOP ==========
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

            # Limit jobs if max_jobs is set
            if max_jobs and max_jobs > 0:
                remaining = max_jobs - len(all_jobs)
                jobs = jobs[:remaining]

            # Fetch job details in parallel
            with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
                future_to_job = {executor.submit(fetch_job_details, job): job for job in jobs}
                for future in as_completed(future_to_job):
                    job_data = future.result()
                    all_jobs.append(job_data)
                    progress_bar.progress(min(len(all_jobs) / (max_jobs if max_jobs>0 else data.get("resultsTotal",1)), 1.0))

            if max_jobs and len(all_jobs) >= max_jobs:
                break

            params["startIndex"] += LOAD_COUNT
            if params["startIndex"] >= data.get("resultsTotal", 0):
                break

            time.sleep(0.2)

        progress_bar.empty()

        if all_jobs:
            st.success(f"Found {len(all_jobs)} jobs!")
            df = pd.DataFrame(all_jobs)

            # Add blank columns
            blank_columns = [
                "Collection ID", "Locale ID", "Item ID", "Archived", "Draft",
                "Created On", "Updated On", "Published On", "CMS ID",
                "Salary Range", "Access", "Salary"  # renamed and added
            ]
            for col in blank_columns:
                df[col] = ""

            # Reorder columns
            column_order = [
                "Name", "Slug", "Collection ID", "Locale ID", "Item ID", "Archived", "Draft",
                "Created On", "Updated On", "Published On", "CMS ID", "Company",
                "Type", "Description", "Salary Range", "Access", "Location",
                "Industry", "Level", "Salary", "Deadline", "Apply URL"
            ]

            # Ensure all columns exist
            for col in column_order:
                if col not in df.columns:
                    df[col] = ""

            df = df[column_order]

            st.dataframe(df)

            # Excel download
            df.to_excel("henkel_jobs.xlsx", index=False)
            with open("henkel_jobs.xlsx", "rb") as f:
                st.download_button("Download Excel", data=f, file_name="henkel_jobs.xlsx")
        else:
            st.warning("No jobs found.")

