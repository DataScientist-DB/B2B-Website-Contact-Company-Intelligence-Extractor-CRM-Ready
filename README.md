# B2B Website Contact Extractor — Emails, Phones & Company Data

Extract Emails, Phone Numbers & Company Intelligence from up to **10,000 websites automatically**.

The **B2B Website Contact Extractor** is a scalable web intelligence Actor that automatically scans company websites and extracts contact information and business intelligence signals.

Instead of manually visiting thousands of websites, the Actor automatically:
- crawls company websites  
- discovers contact and about pages  
- extracts business emails  
- extracts phone numbers  
- detects company names  
- identifies LinkedIn company pages  
- detects Google Maps locations  
- estimates company size  
- classifies industry  
- detects country from domain  

The result is a **clean structured dataset ready for lead generation, CRM enrichment, and market research**.

---
# Key Capabilities

✔ Extract business emails  
✔ Extract phone numbers  
✔ Discover contact pages automatically  
✔ Detect LinkedIn company profiles  
✔ Detect Google Maps locations  
✔ Extract company addresses  
✔ Detect social media profiles  
✔ Estimate company size  
✔ Classify industry  
✔ Export CSV and Excel datasets  
✔ Process up to 10,000 websites per run  

---

# Perfect For
• B2B lead generation  
• CRM data enrichment  
• Business directory creation  
• Market intelligence datasets  
• Startup discovery  
• Competitor contact research  
---
# Typical Use Cases

## Lead Generation
Build prospect lists by extracting company emails and phone numbers directly from websites.
## CRM Data Enrichment
Enhance company records with missing contact information and company intelligence signals.
## Market Research
Analyze industry signals, company presence, and contact channels across thousands of websites.
## Business Development
Discover new companies and identify potential outreach channels.
## Startup Intelligence
Track emerging companies and their online presence.
---
# How It Works

The Actor uses targeted website crawling to extract valuable information efficiently.

Website List
│
▼
Homepage Crawl
│
▼
Page Discovery
(Contact / About / Support)
│
▼
Contact Extraction
(Emails / Phones)
│
▼
Company Intelligence Detection
(Industry / LinkedIn / Maps)
│
▼
Structured Dataset
Instead of crawling entire websites, the Actor scans only the **most relevant pages**, keeping runs **fast and cost-efficient**.
---
# Quick Start (60-Second Test Run)
Test the Actor quickly using the following configuration.
```json
{
  "startUrls": [
    {"url": "https://stripe.com"},
    {"url": "https://shopify.com"},
    {"url": "https://notion.so"}
  ],
  "maxSites": 3,
  "concurrency": 3,
  "maxPagesPerSite": 1,
  "extractSocialLinks": true,
  "outputCsv": true,
  "outputXlsx": true
}
Example Output Dataset
The Actor produces a structured dataset ready for CRM systems, lead generation workflows, and market research.
organization_name	industry	country	best_email	best_phone	linkedin_company_url	pages_scanned_count	status
Stripe	Fintech	United States	support@stripe.com	+1 888 926 2289	https://linkedin.com/company/stripe	3	OK
Shopify	Ecommerce	Canada	support@shopify.com	+1 613 241 2828	https://linkedin.com/company/shopify	3	OK
Notion	Software	United States	team@notion.so	+1 415 555 1234	https://linkedin.com/company/notion	2	OK
 
Output Dataset Fields
The Actor generates a dataset containing the following fields.
Company Identity
•	organization_name
•	industry
•	country
•	company_size_estimate
•	address_text
Contact Information
•	best_email
•	best_phone
•	emails
•	phones
•	emails_count
•	phones_count
•	contact_page
•	contact_form_url
Company Online Presence
•	linkedin_company_url
•	google_maps_url
•	socials
•	socials_count
Technical Metadata
•	input_url
•	final_url
•	pages_scanned_count
•	confidence_email
•	confidence_phone
•	evidence
•	status
•	error
 
Output Files
The Actor automatically generates export files.
File	Description
OUTPUT.csv	Full dataset in CSV format
OUTPUT.xlsx	Excel spreadsheet version
Files are available in the Apify Key-Value Store.
Both files contain the same structured dataset including contact information, company intelligence signals, and extraction metadata.
 
Capacity
Designed for large-scale website processing.
Parameter	Value
Websites per run	10,000
Concurrent workers	up to 200
Pages per website	up to 10
Typical pages scanned	3–4
 
Recommended Configuration
Typical production configuration:
maxSites = 10000
concurrency = 35
maxPagesPerSite = 2
Estimated workload:
10,000 websites
× ~3 pages each
≈ 30,000 page requests
Typical runtime:
20–40 minutes depending on website speed.
 
Input Parameters
startUrls
List of websites to scan.
{
  "startUrls": [
    {"url": "https://example.com"},
    {"url": "https://company.org"}
  ]
}
 
maxSites
Maximum number of websites processed.
Range:
1 – 10,000
Example:
"maxSites": 5000
 
concurrency
Number of websites processed simultaneously.
Websites	Concurrency
100	10
1,000	20
5,000	30
10,000	35–40
Example:
"concurrency": 30
 
maxPagesPerSite
Number of additional pages scanned beyond the homepage.
Common discovered pages:
•	/contact
•	/about
•	/support
•	/locations
•	/impressum
Allowed values:
0 – 10
Recommended:
maxPagesPerSite = 2
 
extractSocialLinks
Enable extraction of social media profiles.
Extracts:
•	LinkedIn
•	Facebook
•	Twitter
•	Instagram
Example:
"extractSocialLinks": true
 
useConcurrent
Enable high-performance concurrent scraping.
Example:
"useConcurrent": true
 
outputCsv
Export results as CSV.
"outputCsv": true
 
outputXlsx
Export results as Excel.
"outputXlsx": true
 
Best Practices
Start Small
Test with 10–50 websites first.
Increase Scale Gradually
Run in stages:
•	100 websites
•	1,000 websites
•	5,000 websites
•	10,000 websites
Limit Page Depth
Most websites expose contact information on homepage or contact page.
Recommended:
maxPagesPerSite = 2
 
Limitations
Some websites may:
•	block automated requests
•	hide contact information
•	load contact data using JavaScript
In these cases the Actor may return partial results.
FAQ
Can this Actor crawl entire websites?
No.
The Actor scans only the most relevant pages to keep runs fast.
How many websites can be processed?
Up to 10,000 websites per run.
Can the Actor extract emails from PDFs?
No.
The Actor processes HTML pages only.
 
Summary
The B2B Website Contact Extractor is a scalable contact intelligence engine capable of scanning thousands of websites and extracting structured company information.
It combines:
•	intelligent crawling
•	contact extraction
•	company data enrichment
•	scalable concurrent processing
to produce datasets suitable for:
•	lead generation
•	market research
•	CRM enrichment
•	business intelligence


