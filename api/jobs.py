import requests
from django.http import JsonResponse
from pymongo import MongoClient
import json
from bs4 import BeautifulSoup
import nltk
from datetime import datetime
from nltk.tokenize import word_tokenize
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time
import os
from playwright.sync_api import sync_playwright

# MongoDB Connection
client = MongoClient("mongodb+srv://ihub:ihub@cce.ksniz.mongodb.net/")
db = client["CCE"]

# RapidAPI Details
RAPIDAPI_KEY = "4c6f0f6fc5msh9ca8144c4f547fep16ac54jsndd5114267fd4"
RAPIDAPI_HOST = "jsearch.p.rapidapi.com"

def fetch_jobs_api(request):
    """Fetch jobs from RapidAPI and store in MongoDB in an organized format"""

    query = request.GET.get("query", "Software Developer in Tamil Nadu")  # Default search

    url = "https://jsearch.p.rapidapi.com/search"

    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST
    }

    params = {
        "query": query,
        "page": "1",
        "num_pages": "1",
        "country": "in",
        "date_posted": "all",
        "language": "en"
    }

    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()  # Raises exception if API fails

        job_data = response.json().get("data", [])

        formatted_jobs = []
        for job in job_data:
            formatted_job = {
                "title": job.get("job_title", "N/A"),
                "company_name": job.get("employer_name", "N/A"),
                "company_website": job.get("employer_website", "N/A"),
                "job_description": job.get("job_description", "N/A"),
                "job_location": job.get("location", "N/A"),
                "salary_range": job.get("estimated_salary", "N/A"),
                "job_link": job.get("job_apply_link", "N/A"),
                "work_schedule": job.get("schedule_type", "N/A"),
                "selectedCategory": job.get("category", "IT & Development"),
                "selectedWorkType": job.get("job_employment_type", "Full-time"),
                "is_publish": True,
                "admin_id":"67a5ef2f731be13d58bb2e62",
                "status": "Active",
                "updated_at": datetime.now().isoformat(),
                "edited": "superadmin"  # Placeholder for now
            }

            # Store in MongoDB
            db.api_jobs.update_one(
                {"job_link": formatted_job["job_link"]},  # Unique Identifier
                {"$set": formatted_job},
                upsert=True
            )

            formatted_jobs.append(formatted_job)

        return JsonResponse({"message": "Jobs stored successfully!", "jobs": formatted_jobs}, status=200)

    except requests.exceptions.RequestException as e:
        return JsonResponse({"error": f"API request failed: {str(e)}"}, status=500)

# **Custom Headers (Looks Like a Real Browser)**
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.google.com/",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive"
}

def scrape_naukri_jobs(request):
    """Scrape jobs from Naukri using Playwright (Bypass Block)"""

    query = request.GET.get("query", "Software Developer")
    location = request.GET.get("location", "India")

    query_formatted = query.replace(" ", "-")
    location_formatted = location.replace(" ", "-")
    naukri_url = f"https://www.naukri.com/{query_formatted}-jobs-in-{location_formatted}"

    jobs = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_extra_http_headers(HEADERS)
            page.goto("https://www.naukri.com/")
            context = browser.new_context(
            user_agent=HEADERS["User-Agent"],
            extra_http_headers=HEADERS
            )
            page = context.new_page()
            
            print(f"🔗 Visiting: {naukri_url}")
            page.goto(naukri_url, timeout=60000)

            # **Ensure Page is Fully Loaded**
            page.wait_for_load_state("networkidle")
            time.sleep(5)  # Allow page to load completely
            
            # **Check for Access Denied**
            if "Access Denied" in page.content():
                print("❌ Access Denied! Bypassing Required.")
                return JsonResponse({"message": "Access Denied by Naukri!", "jobs": []}, status=403)

            # **Scroll Down to Load More Jobs**
            for _ in range(3):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(2)

            # **Wait Until Job Elements are Visible**
            try:
                page.wait_for_selector(".srp-jobtuple-wrapper", timeout=30000)
            except:
                print("⚠️ No job listings found. Printing Page Source for Debugging:")
                print(page.content())  # Debugging: Check if Naukri is blocking
                return JsonResponse({"message": "No jobs found!", "jobs": []}, status=200)

            job_cards = page.query_selector_all(".srp-jobtuple-wrapper")

            if not job_cards:
                return JsonResponse({"message": "No jobs found!", "jobs": []}, status=200)

            for job in job_cards:
                try:
                    # **Extract Job Details**
                    title_element = job.query_selector("h2 a")
                    title = title_element.inner_text().strip() if title_element else "N/A"
                    job_link = title_element.get_attribute("href") if title_element else "N/A"

                    company_element = job.query_selector("span a.comp-name")
                    company_name = company_element.inner_text().strip() if company_element else "Not Available"

                    experience_element = job.query_selector("span.exp")
                    experience = experience_element.inner_text().strip() if experience_element else "N/A"

                    salary_element = job.query_selector("div:nth-child(3) div span:nth-child(2) span span")
                    salary_range = salary_element.inner_text().strip() if salary_element else "N/A"

                    location_element = job.query_selector("div:nth-child(1) div:nth-child(3) div span:nth-child(3) span span")
                    job_location = location_element.inner_text().strip() if location_element else "Not Specified"

                    skills_elements = job.query_selector_all("ul.tags-gt li")
                    required_skills = [skill.inner_text().strip() for skill in skills_elements if skill.inner_text().strip()]

                    desc_element = job.query_selector("span.job-desc.ni-job-tuple-icon.ni-job-tuple-icon-srp-description")
                    job_description = desc_element.inner_text().strip() if desc_element else "N/A"

                    # **Formatted Job Data**
                    formatted_job = {
                        "title": title,
                        "job_data": {
                            "company_name": company_name,
                            "job_description": job_description,
                            "required_skills": required_skills,
                            "experience_level": experience,
                            "salary_range": salary_range,
                            "job_location": job_location,
                            "job_link": job_link,
                            "selectedCategory": "IT & Development",
                            "selectedWorkType": "Full-time"
                        },
                        "is_publish": True,
                        "status": "Active",
                        "updated_at": datetime.utcnow().isoformat(),
                        "edited": "superadmin"
                    }

                    # **Store in MongoDB**
                    db.scraped_jobs.update_one(
                        {"job_link": job_link},
                        {"$set": formatted_job},
                        upsert=True
                    )

                    jobs.append(formatted_job)

                except Exception as e:
                    print(f"⚠️ Error extracting job: {e}")

            browser.close()

    except Exception as e:
        print(f"🔥 Playwright Error: {e}")
        return JsonResponse({"message": "Playwright failed!", "error": str(e)}, status=500)

    return JsonResponse({"message": "Naukri jobs scraped and stored successfully!", "jobs": jobs}, status=200)

nltk.download('punkt')

def search_jobs(request):
    """Search stored jobs using a natural-language prompt"""
    import nltk
    nltk.download('punkt')  # Ensure 'punkt' is downloaded before use
    from nltk.tokenize import word_tokenize

    user_query = request.GET.get("query", "").strip()

    if not user_query:
        return JsonResponse({"error": "Query is required!"}, status=400)

    # Tokenizing user input safely
    try:
        tokens = word_tokenize(user_query.lower())
    except Exception as e:
        return JsonResponse({"error": f"Failed to process query: {str(e)}"}, status=400)

    # Extract job category
    categories = ["software", "developer", "engineer", "data scientist"]
    matched_category = next((word for word in tokens if word in categories), "Software Developer")

    # Extract location
    locations = ["Tamil Nadu", "Chennai", "Bangalore", "Mumbai"]
    matched_location = next((word for word in tokens if word in locations), "Tamil Nadu")

    # Extract salary (if mentioned)
    salary = next((word for word in tokens if word.isdigit()), None)

    # Query MongoDB (API Jobs + Scraped Jobs)
    job_results = list(db.api_jobs.find({"title": {"$regex": matched_category, "$options": "i"}})) + \
                  list(db.scraped_jobs.find({"title": {"$regex": matched_category, "$options": "i"}}))

    # Filtering by location and salary
    if matched_location:
        job_results = [job for job in job_results if matched_location.lower() in job.get("location", "").lower()]

    if salary:
        job_results = [job for job in job_results if "salary" in job and int(job["salary"]) >= int(salary) * 100000]

    return JsonResponse({"jobs": job_results}, safe=False)