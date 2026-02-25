"""
seed_data.py - Generate and upload sample resumes for demo/testing

Run: python seed_data.py
"""
import requests
import os
from pathlib import Path

API_BASE = "http://localhost:8000/api"

# Sample resume texts to create as test files
SAMPLE_RESUMES = [
    {
        "filename": "sarah_chen_engineer.txt",
        "content": """Sarah Chen
sarah.chen@email.com | (415) 555-0101 | San Francisco, CA | linkedin.com/in/sarahchen

SUMMARY
Senior Software Engineer with 7 years of experience building scalable distributed systems. 
Passionate about Python, cloud architecture, and machine learning infrastructure.

SKILLS
Python, JavaScript, TypeScript, Go, AWS, GCP, Docker, Kubernetes, PostgreSQL, Redis, 
FastAPI, Django, React, TensorFlow, PyTorch, Kafka, Spark, Terraform, Git

EXPERIENCE
Senior Software Engineer | Stripe | Jan 2021 - Present
- Led backend development for Stripe's payment processing pipeline handling $500B+ annually
- Designed and implemented microservices architecture reducing API latency by 40%
- Mentored team of 5 junior engineers, established code review best practices

Software Engineer | Airbnb | Jun 2018 - Dec 2020
- Built real-time search and recommendation system using Elasticsearch and Python
- Improved search relevance by 25% using machine learning ranking models
- Developed high-performance data pipelines processing 10M events/day with Kafka

Software Engineer Intern | Google | Summer 2017
- Worked on Google Maps backend optimization with Python and C++

EDUCATION
B.S. Computer Science | UC Berkeley | 2018
GPA: 3.9/4.0, Honors
"""
    },
    {
        "filename": "james_rodriguez_ml.txt",
        "content": """James Rodriguez
james.r@gmail.com | (512) 555-0202 | Austin, TX

Machine Learning Engineer | Data Scientist

SKILLS
Python, R, SQL, TensorFlow, PyTorch, scikit-learn, Keras, Pandas, NumPy, 
Spark, Databricks, AWS SageMaker, MLflow, Docker, Kubernetes, Airflow, 
A/B Testing, Statistics, Natural Language Processing, Computer Vision

WORK EXPERIENCE
Machine Learning Engineer | Meta | Mar 2020 - Present
- Built recommendation models serving 3 billion users daily
- Developed NLP models for content moderation achieving 94% accuracy
- Reduced model inference cost by 30% through optimization and quantization

Data Scientist | Capital One | Aug 2017 - Feb 2020
- Created credit risk models reducing default rates by 18%
- Built real-time fraud detection system using gradient boosting
- Led A/B testing framework used across 50+ product experiments

Research Assistant | UT Austin | 2015 - 2017
- Published 2 papers on deep learning for time series forecasting

EDUCATION
M.S. Statistics | UT Austin | 2017
B.S. Mathematics | UT Austin | 2015
"""
    },
    {
        "filename": "priya_patel_frontend.txt",
        "content": """Priya Patel
priya.patel@dev.io | (628) 555-0303 | New York, NY

Frontend Engineer | React Specialist

SUMMARY
Creative frontend engineer with 5 years building beautiful, performant web applications.
Expert in React ecosystem, design systems, and accessibility.

TECHNICAL SKILLS
JavaScript, TypeScript, React, Next.js, Vue.js, HTML5, CSS3, SCSS, 
Tailwind CSS, GraphQL, REST APIs, Jest, Cypress, Webpack, Vite,
Figma, Storybook, Web Performance, Accessibility (WCAG 2.1), Node.js

EXPERIENCE
Senior Frontend Engineer | Figma | Feb 2022 - Present
- Built collaborative design features used by 10M+ designers worldwide
- Led migration from JavaScript to TypeScript reducing bugs by 35%
- Created component library used across 8 product teams

Frontend Engineer | Shopify | May 2019 - Jan 2022
- Developed merchant dashboard handling $500M in monthly transactions
- Improved Core Web Vitals scores by 60% through performance optimization
- Mentored 3 junior engineers and led weekly tech talks

EDUCATION
B.S. Computer Science | NYU | 2019
Minor in Graphic Design
"""
    },
    {
        "filename": "michael_kim_devops.txt",
        "content": """Michael Kim
michael.kim@cloudops.io | (206) 555-0404 | Seattle, WA

DevOps Engineer | Site Reliability Engineer | Cloud Architect

SKILLS
AWS, GCP, Azure, Kubernetes, Docker, Terraform, Ansible, Helm,
Python, Bash, Go, Jenkins, GitHub Actions, GitLab CI, ArgoCD,
Prometheus, Grafana, ELK Stack, Datadog, PagerDuty,
PostgreSQL, MySQL, Redis, Kafka, Linux, Networking

EXPERIENCE
Senior DevOps Engineer | Amazon Web Services | Apr 2020 - Present
- Managed cloud infrastructure for 200+ microservices at 99.99% uptime
- Reduced infrastructure costs by $2M/year through optimization
- Built zero-downtime deployment pipeline used by 500+ engineers

DevOps Engineer | Microsoft | Jun 2017 - Mar 2020
- Designed and implemented CI/CD pipelines for Azure DevOps
- Automated infrastructure provisioning using Terraform and Ansible
- Reduced deployment time from 4 hours to 15 minutes

EDUCATION
B.S. Information Technology | University of Washington | 2017
AWS Certified Solutions Architect Professional
Certified Kubernetes Administrator (CKA)
"""
    },
    {
        "filename": "lisa_wang_product.txt",
        "content": """Lisa Wang
lisa.wang@pm.com | (415) 555-0505 | San Francisco, CA

Product Manager | Product Strategy | User Research

SUMMARY
Experienced Product Manager with 6 years driving product strategy at B2B SaaS companies.
Strong background in user research, data analysis, and cross-functional leadership.

SKILLS
Product Strategy, Roadmap Planning, User Research, A/B Testing, Data Analysis,
SQL, Mixpanel, Amplitude, Figma, Jira, Confluence, OKRs, Agile/Scrum,
Market Research, Competitive Analysis, Stakeholder Management, Go-to-Market

EXPERIENCE
Senior Product Manager | Salesforce | Jan 2021 - Present
- Owned CRM analytics product generating $80M ARR
- Led team of 15 engineers and 3 designers to ship 4 major features
- Increased user engagement by 45% through data-driven product improvements

Product Manager | HubSpot | Aug 2018 - Dec 2020
- Launched marketing automation features adopted by 50,000+ customers
- Drove 30% increase in trial-to-paid conversion through onboarding improvements
- Defined and tracked OKRs across 3 product squads

Associate Product Manager | LinkedIn | 2017 - 2018
- Managed LinkedIn Learning content discovery features

EDUCATION
MBA | Stanford Graduate School of Business | 2017
B.A. Economics | UCLA | 2014
"""
    }
]


def create_text_file(content, filename):
    path = Path(f"/tmp/{filename}")
    path.write_text(content)
    return path


def upload_resume(file_path):
    with open(file_path, 'rb') as f:
        response = requests.post(
            f"{API_BASE}/upload",
            files={"file": (file_path.name.replace('.txt', '.pdf'), f, "application/pdf")}
        )
    return response


def main():
    print("🌱 Seeding sample resumes...\n")

    # Check API is running
    try:
        r = requests.get(f"{API_BASE}/health", timeout=5)
        print(f"✅ API connected — current resumes: {r.json().get('resume_count', 0)}\n")
    except Exception:
        print("❌ API not running. Start with: uvicorn main:app --reload")
        return

    for sample in SAMPLE_RESUMES:
        file_path = create_text_file(sample["content"], sample["filename"])
        try:
            r = upload_resume(file_path)
            if r.status_code == 200:
                data = r.json()
                print(f"✅ Uploaded: {sample['filename']} (ID: {data['id']})")
            else:
                print(f"❌ Failed: {sample['filename']} — {r.json().get('detail', 'Unknown error')}")
        except Exception as e:
            print(f"❌ Error uploading {sample['filename']}: {e}")
        finally:
            file_path.unlink(missing_ok=True)

    print(f"\n✅ Done! Uploaded {len(SAMPLE_RESUMES)} sample resumes.")
    print("⏳ AI parsing happening in background — check the UI in ~30 seconds.")


if __name__ == "__main__":
    main()
