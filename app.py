import streamlit as st
import requests
import pandas as pd
import re
from bs4 import BeautifulSoup
import phonenumbers
from phonenumbers import carrier, geocoder
from urllib.parse import urljoin, urlparse
import time
from io import BytesIO
import os
from dotenv import load_dotenv
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
import random

# Load environment variables
load_dotenv()


class EnhancedEmployeeDataExtractor:
    def __init__(self):
        # API Keys
        self.serper_api_key = os.getenv('SERPER_API_KEY')
        self.hunter_api_key = os.getenv('HUNTER_API_KEY')
        self.pdl_api_key = os.getenv('PDL_API_KEY')
        self.numverify_api_key = os.getenv('NUMVERIFY_API_KEY')
        self.scraper_api_key = os.getenv('SCRAPER_API_KEY')
        
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def set_api_keys(self, serper_key=None, hunter_key=None, pdl_key=None, numverify_key=None, scraper_key=None):
        """Set API keys"""
        if serper_key:
            self.serper_api_key = serper_key
        if hunter_key:
            self.hunter_api_key = hunter_key
        if pdl_key:
            self.pdl_api_key = pdl_key
        if numverify_key:
            self.numverify_api_key = numverify_key
        if scraper_key:
            self.scraper_api_key = scraper_key

    def search_companies_with_serper(self, industry, job_role, city, country, num_results=20):
        """Search for companies using Serper.dev API with enhanced queries"""
        if not self.serper_api_key:
            st.error("Please provide Serper.dev API key")
            return []

        # Enhanced search queries targeting different platforms
        queries = [
            f'"{job_role}" "{industry}" "{city}" "{country}" site:linkedin.com/company',
            f'"{industry}" companies "{city}" "{country}" site:crunchbase.com',
            f'"{job_role}" "{industry}" "{city}" "{country}" site:justdial.com OR site:yellowpages.com',
            f'"{industry}" "{city}" "{country}" "contact us" "about us" -site:linkedin.com/in',
            f'"{job_role}" "{industry}" companies "{city}" "{country}" leadership team',
            f'"{industry}" "{city}" "{country}" "careers" "team" "management"',
            f'"{job_role}" "{industry}" "{city}" "{country}" site:zoominfo.com OR site:apollo.io'
        ]

        all_results = []
        
        for i, query in enumerate(queries):
            st.write(f"🔍 Searching query {i+1}/{len(queries)}: {query[:60]}...")
            
            url = "https://google.serper.dev/search"
            payload = {
                "q": query,
                "num": 10,
                "gl": "in" if country.lower() == "india" else "us",
                "hl": "en"
            }
            headers = {
                "X-API-KEY": self.serper_api_key,
                "Content-Type": "application/json"
            }

            try:
                response = requests.post(url, json=payload, headers=headers)
                response.raise_for_status()
                results = response.json().get("organic", [])
                all_results.extend(results)
                time.sleep(1)  # Rate limiting
            except requests.exceptions.RequestException as e:
                st.warning(f"Error with query {i+1}: {str(e)}")
                continue

        # Remove duplicates and filter relevant results
        seen_urls = set()
        unique_results = []
        
        for result in all_results:
            url = result.get('link', '')
            if url not in seen_urls and url:
                seen_urls.add(url)
                unique_results.append(result)

        return unique_results[:num_results]

    def extract_domain_from_url(self, url):
        """Extract clean domain from URL"""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.replace('www.', '').lower()
            return domain
        except:
            return None

    def get_emails_with_hunter(self, domain, limit=10):
        """Get professional emails using Hunter.io API"""
        if not self.hunter_api_key or not domain:
            return []

        try:
            url = f"https://api.hunter.io/v2/domain-search"
            params = {
                "domain": domain,
                "api_key": self.hunter_api_key,
                "limit": limit,
                "type": "personal"
            }
            
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            emails_data = []
            if data.get('data') and data['data'].get('emails'):
                for email_info in data['data']['emails']:
                    emails_data.append({
                        'email': email_info.get('value', ''),
                        'first_name': email_info.get('first_name', ''),
                        'last_name': email_info.get('last_name', ''),
                        'position': email_info.get('position', ''),
                        'confidence': email_info.get('confidence', 0)
                    })
            
            return emails_data
            
        except Exception as e:
            st.warning(f"Hunter.io API error for {domain}: {str(e)}")
            return []

    def search_employees_with_pdl(self, job_role, industry, city, country, limit=10):
        """Search for employees using People Data Labs API"""
        if not self.pdl_api_key:
            return []

        try:
            url = "https://api.peopledatalabs.com/v5/person/search"
            
            # Build search query
            job_titles = [job_role]
            if job_role.upper() == "CTO":
                job_titles.extend(["Chief Technology Officer", "VP Technology", "Head of Technology"])
            elif job_role.upper() == "CEO":
                job_titles.extend(["Chief Executive Officer", "Founder", "Managing Director"])
            elif job_role.upper() == "CFO":
                job_titles.extend(["Chief Financial Officer", "VP Finance", "Finance Director"])
            
            query = {
                "query": {
                    "bool": {
                        "must": [
                            {"term": {"location_country": country.lower()}},
                            {"term": {"location_locality": city.lower()}},
                            {"terms": {"job_title": [title.lower() for title in job_titles]}},
                            {"term": {"industry": industry.lower()}}
                        ]
                    }
                },
                "size": limit
            }
            
            headers = {
                "X-Api-Key": self.pdl_api_key,
                "Content-Type": "application/json"
            }
            
            response = requests.post(url, json=query, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            employees = []
            if data.get('data'):
                for person in data['data']:
                    employee_info = {
                        'full_name': person.get('full_name', ''),
                        'first_name': person.get('first_name', ''),
                        'last_name': person.get('last_name', ''),
                        'job_title': person.get('job_title', ''),
                        'company': person.get('job_company_name', ''),
                        'industry': person.get('industry', ''),
                        'location': person.get('location_name', ''),
                        'linkedin_url': person.get('linkedin_url', ''),
                        'work_email': person.get('work_email', ''),
                        'personal_emails': person.get('personal_emails', []),
                        'phone_numbers': person.get('phone_numbers', [])
                    }
                    employees.append(employee_info)
            
            return employees
            
        except Exception as e:
            st.warning(f"People Data Labs API error: {str(e)}")
            return []

    def validate_phone_with_numverify(self, phone_number, country_code="IN"):
        """Validate and format phone number using NumVerify API"""
        if not self.numverify_api_key or not phone_number:
            return None

        try:
            # Clean phone number
            clean_phone = re.sub(r'[^\d+]', '', str(phone_number))
            
            url = "http://apilayer.net/api/validate"
            params = {
                "access_key": self.numverify_api_key,
                "number": clean_phone,
                "country_code": country_code,
                "format": 1
            }
            
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            if data.get('valid'):
                return {
                    'number': data.get('international_format', clean_phone),
                    'local_format': data.get('local_format', ''),
                    'country_name': data.get('country_name', ''),
                    'carrier': data.get('carrier', ''),
                    'line_type': data.get('line_type', 'Unknown')
                }
            
            return None
            
        except Exception as e:
            st.warning(f"NumVerify API error: {str(e)}")
            return None

    def scrape_with_scraper_api(self, url):
        """Scrape website using ScraperAPI"""
        if self.scraper_api_key:
            try:
                scraper_url = f"http://api.scraperapi.com?api_key={self.scraper_api_key}&url={url}"
                response = requests.get(scraper_url, timeout=30)
                response.raise_for_status()
                return response.text
            except Exception as e:
                st.warning(f"ScraperAPI error for {url}: {str(e)}")
                return None
        else:
            # Fallback to direct scraping
            return self.scrape_website_direct(url)

    def scrape_website_direct(self, url):
        """Direct website scraping as fallback"""
        try:
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            return response.text
        except Exception as e:
            st.warning(f"Direct scraping error for {url}: {str(e)}")
            return None

    def extract_contact_info_from_page(self, html_content, url):
        """Extract contact information from webpage content"""
        if not html_content:
            return {}

        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
        
        text = soup.get_text()
        
        contact_info = {
            'emails': [],
            'phones': [],
            'addresses': [],
            'company_name': '',
            'employee_count': ''
        }
        
        # Extract emails
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        emails = re.findall(email_pattern, text)
        contact_info['emails'] = list(set(emails))
        
        # Extract phone numbers (multiple patterns)
        phone_patterns = [
            r'\+\d{1,3}[-.\s]?\d{1,4}[-.\s]?\d{1,4}[-.\s]?\d{1,9}',
            r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b',
            r'\b\d{10}\b',
            r'\(\d{3}\)\s*\d{3}[-.\s]?\d{4}'
        ]
        
        phones = []
        for pattern in phone_patterns:
            matches = re.findall(pattern, text)
            phones.extend(matches)
        contact_info['phones'] = list(set(phones))
        
        # Extract addresses
        address_patterns = [
            r'Address[:\s]+([^\n]+(?:\n[^\n]+)*?)(?=\n\n|\n[A-Z]|\n$)',
            r'Location[:\s]+([^\n]+)',
            r'Office[:\s]+([^\n]+)',
            r'\d+[^\n]*(?:Street|St|Avenue|Ave|Road|Rd|Lane|Ln)[^\n]*'
        ]
        
        addresses = []
        for pattern in address_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE | re.MULTILINE)
            addresses.extend(matches)
        contact_info['addresses'] = list(set(addresses))
        
        # Extract company name from title
        title_tag = soup.find('title')
        if title_tag:
            title = title_tag.get_text().strip()
            # Clean title to get company name
            company_name = title.split('|')[0].split('-')[0].strip()
            contact_info['company_name'] = company_name
        
        # Extract employee count
        employee_patterns = [
            r'(\d+[\+,]?\d*)\s*employees',
            r'team\s+of\s+(\d+[\+,]?\d*)',
            r'(\d+[\+,]?\d*)\s*people',
            r'(\d+[\+,]?\d*)\s*staff'
        ]
        
        for pattern in employee_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                contact_info['employee_count'] = match.group(1)
                break
        
        return contact_info

    def process_company_result(self, result, job_role, industry, city, country):
        """Process a single search result to extract comprehensive employee data"""
        url = result.get('link', '')
        title = result.get('title', '')
        snippet = result.get('snippet', '')
        
        employees_found = []
        
        # Extract domain
        domain = self.extract_domain_from_url(url)
        if not domain:
            return employees_found
        
        st.write(f"🌐 Processing: {domain}")
        
        # Skip certain domains
        skip_domains = ['linkedin.com/in/', 'facebook.com', 'twitter.com', 'instagram.com']
        if any(skip in url for skip in skip_domains):
            return employees_found
        
        # 1. Get emails from Hunter.io
        hunter_emails = self.get_emails_with_hunter(domain)
        
        # 2. Scrape website for contact information
        html_content = self.scrape_with_scraper_api(url)
        contact_info = self.extract_contact_info_from_page(html_content, url)
        
        # 3. Try to find specific pages (contact, about, team)
        specific_pages = ['/contact', '/about', '/team', '/leadership', '/careers']
        for page in specific_pages:
            page_url = urljoin(url, page)
            page_content = self.scrape_with_scraper_api(page_url)
            if page_content:
                page_contact_info = self.extract_contact_info_from_page(page_content, page_url)
                # Merge contact info
                contact_info['emails'].extend(page_contact_info.get('emails', []))
                contact_info['phones'].extend(page_contact_info.get('phones', []))
                contact_info['addresses'].extend(page_contact_info.get('addresses', []))
        
        # Remove duplicates
        contact_info['emails'] = list(set(contact_info['emails']))
        contact_info['phones'] = list(set(contact_info['phones']))
        contact_info['addresses'] = list(set(contact_info['addresses']))
        
        # 4. Process Hunter.io results
        for email_data in hunter_emails:
            if email_data.get('position') and job_role.lower() in email_data.get('position', '').lower():
                # Validate phone numbers
                validated_phones = []
                for phone in contact_info['phones'][:3]:  # Limit to 3 phones
                    validated = self.validate_phone_with_numverify(phone)
                    if validated:
                        validated_phones.append(validated)
                
                employee_record = {
                    'business_name': contact_info.get('company_name') or self.extract_company_name_from_domain(domain),
                    'num_employees': contact_info.get('employee_count') or 'Unknown',
                    'contact_person': f"{email_data.get('first_name', '')} {email_data.get('last_name', '')}".strip(),
                    'first_name': email_data.get('first_name', ''),
                    'corporate_email': email_data.get('email', ''),
                    'other_emails': ', '.join(contact_info['emails'][:3]) if contact_info['emails'] else f"info@{domain}",
                    'website': f"www.{domain}",
                    'phone': validated_phones[0]['number'] if validated_phones else contact_info['phones'][0] if contact_info['phones'] else 'Unknown',
                    'phone_type': validated_phones[0]['line_type'] if validated_phones else 'Office',
                    'street_address': contact_info['addresses'][0] if contact_info['addresses'] else f"{city}, {country}",
                    'zip_code': 'Unknown',
                    'state': 'Unknown',
                    'city': city
                }
                
                employees_found.append(employee_record)
        
        # 5. If no Hunter.io results, create records from scraped data
        if not employees_found and contact_info['emails']:
            # Try to extract names from email addresses
            for email in contact_info['emails'][:3]:
                if '@' in email:
                    local_part = email.split('@')[0]
                    # Try to extract name from email
                    name_parts = re.split(r'[._-]', local_part)
                    if len(name_parts) >= 2:
                        first_name = name_parts[0].capitalize()
                        last_name = name_parts[1].capitalize()
                        full_name = f"{first_name} {last_name}"
                        
                        # Validate phone
                        validated_phone = None
                        if contact_info['phones']:
                            validated_phone = self.validate_phone_with_numverify(contact_info['phones'][0])
                        
                        employee_record = {
                            'business_name': contact_info.get('company_name') or self.extract_company_name_from_domain(domain),
                            'num_employees': contact_info.get('employee_count') or 'Unknown',
                            'contact_person': full_name,
                            'first_name': first_name,
                            'corporate_email': email,
                            'other_emails': ', '.join([e for e in contact_info['emails'] if e != email][:2]),
                            'website': f"www.{domain}",
                            'phone': validated_phone['number'] if validated_phone else contact_info['phones'][0] if contact_info['phones'] else 'Unknown',
                            'phone_type': validated_phone['line_type'] if validated_phone else 'Office',
                            'street_address': contact_info['addresses'][0] if contact_info['addresses'] else f"{city}, {country}",
                            'zip_code': 'Unknown',
                            'state': 'Unknown',
                            'city': city
                        }
                        
                        employees_found.append(employee_record)
                        break  # Only one record per company if no specific role match
        
        return employees_found

    def extract_company_name_from_domain(self, domain):
        """Extract company name from domain"""
        try:
            name = domain.split('.')[0]
            return name.replace('-', ' ').replace('_', ' ').title()
        except:
            return "Unknown Company"

    def extract_comprehensive_employee_data(self, industry, job_role, city, country, num_results=10):
        """Main method to extract comprehensive employee data using all APIs"""
        all_employees = []
        
        # Step 1: Search companies using Serper.dev
        st.write("🔍 Step 1: Searching for companies...")
        search_results = self.search_companies_with_serper(industry, job_role, city, country, num_results * 2)
        
        if not search_results:
            st.error("No search results found")
            return []
        
        st.success(f"Found {len(search_results)} company results")
        
        # Step 2: Search employees using People Data Labs
        st.write("👥 Step 2: Searching employees with People Data Labs...")
        pdl_employees = self.search_employees_with_pdl(job_role, industry, city, country, num_results)
        
        # Process PDL results
        for emp in pdl_employees:
            if emp.get('work_email') or emp.get('personal_emails'):
                # Validate phone if available
                validated_phone = None
                if emp.get('phone_numbers'):
                    validated_phone = self.validate_phone_with_numverify(emp['phone_numbers'][0])
                
                employee_record = {
                    'business_name': emp.get('company', 'Unknown Company'),
                    'num_employees': 'Unknown',
                    'contact_person': emp.get('full_name', ''),
                    'first_name': emp.get('first_name', ''),
                    'corporate_email': emp.get('work_email', ''),
                    'other_emails': ', '.join(emp.get('personal_emails', [])[:2]),
                    'website': f"www.{emp.get('company', '').lower().replace(' ', '')}.com",
                    'phone': validated_phone['number'] if validated_phone else emp.get('phone_numbers', ['Unknown'])[0],
                    'phone_type': validated_phone['line_type'] if validated_phone else 'Unknown',
                    'street_address': emp.get('location', f"{city}, {country}"),
                    'zip_code': 'Unknown',
                    'state': 'Unknown',
                    'city': city
                }
                all_employees.append(employee_record)
        
        st.success(f"Found {len(pdl_employees)} employees from People Data Labs")
        
        # Step 3: Process company websites
        st.write("🌐 Step 3: Processing company websites...")
        
        with ThreadPoolExecutor(max_workers=3) as executor:
            future_to_result = {
                executor.submit(self.process_company_result, result, job_role, industry, city, country): result
                for result in search_results[:15]  # Process top 15 results
            }
            
            for future in as_completed(future_to_result):
                try:
                    employees = future.result(timeout=60)
                    all_employees.extend(employees)
                    
                    if len(all_employees) >= num_results:
                        break
                        
                except Exception as e:
                    st.warning(f"Error processing result: {str(e)}")
                    continue
        
        # Remove duplicates based on email
        seen_emails = set()
        unique_employees = []
        
        for emp in all_employees:
            email = emp.get('corporate_email', '').lower()
            if email and email not in seen_emails:
                seen_emails.add(email)
                unique_employees.append(emp)
            elif not email:  # Include records without email but with other info
                unique_employees.append(emp)
        
        return unique_employees[:num_results]


def main():
    st.set_page_config(page_title="Enhanced Employee Data Extractor", page_icon="🚀", layout="wide")

    st.title("🚀 Enhanced Real Employee Data Extractor")
    st.markdown("Extract **real employee details** using multiple professional APIs and data sources")
    
    st.info("🔥 **Multi-API Integration**: Serper.dev + Hunter.io + People Data Labs + NumVerify + ScraperAPI for comprehensive data extraction")

    # Initialize extractor
    if 'extractor' not in st.session_state:
        st.session_state.extractor = EnhancedEmployeeDataExtractor()

    # API Keys Configuration
    st.sidebar.header("🔑 API Configuration")
    
    # Check loaded API keys
    api_status = {
        "Serper.dev": st.session_state.extractor.serper_api_key,
        "Hunter.io": st.session_state.extractor.hunter_api_key,
        "People Data Labs": st.session_state.extractor.pdl_api_key,
        "NumVerify": st.session_state.extractor.numverify_api_key,
        "ScraperAPI": st.session_state.extractor.scraper_api_key
    }
    
    for api_name, api_key in api_status.items():
        if api_key:
            st.sidebar.success(f"✅ {api_name}")
        else:
            st.sidebar.warning(f"⚠️ {api_name}")
    
    # Manual API key inputs
    with st.sidebar.expander("🔧 Manual API Key Input"):
        serper_key = st.text_input("Serper.dev API Key", type="password", help="Get from https://serper.dev")
        hunter_key = st.text_input("Hunter.io API Key", type="password", help="Get from https://hunter.io")
        pdl_key = st.text_input("People Data Labs API Key", type="password", help="Get from https://peopledatalabs.com")
        numverify_key = st.text_input("NumVerify API Key", type="password", help="Get from https://numverify.com")
        scraper_key = st.text_input("ScraperAPI Key", type="password", help="Get from https://scraperapi.com")
        
        if st.button("Update API Keys"):
            st.session_state.extractor.set_api_keys(serper_key, hunter_key, pdl_key, numverify_key, scraper_key)
            st.success("API keys updated!")

    # Number of results
    num_results = st.sidebar.selectbox(
        "Number of Employee Records",
        options=[5, 10, 15, 20, 25, 30],
        index=1,
        help="Select how many employee records to extract"
    )

    # Main interface
    col1, col2 = st.columns(2)

    with col1:
        industry = st.selectbox(
            "Industry",
            options=["Technology", "Healthcare", "Finance", "Manufacturing", "Retail", "Education", "Consulting", "Real Estate", "Marketing", "Legal"],
            help="Select the target industry"
        )
        job_role = st.selectbox(
            "Job Role",
            options=["CTO", "CEO", "CFO", "VP Engineering", "Software Developer", "Marketing Manager", "HR Manager", "Sales Manager", "Director", "Founder"],
            help="Select the target job role"
        )

    with col2:
        city = st.text_input("City", placeholder="e.g., Delhi, Mumbai, Bangalore", value="Delhi")
        country = st.text_input("Country", placeholder="e.g., India, USA, UK", value="India")

    extract_button = st.button("🚀 Extract Real Employee Data", type="primary")

    if extract_button:
        if not all([industry, job_role, city, country]):
            st.error("Please fill in all fields")
        elif not st.session_state.extractor.serper_api_key:
            st.error("Please provide at least Serper.dev API key")
        else:
            with st.spinner("🔄 Extracting comprehensive employee data..."):
                employees_data = st.session_state.extractor.extract_comprehensive_employee_data(
                    industry, job_role, city, country, num_results
                )

            if employees_data:
                # Create DataFrame
                df = pd.DataFrame(employees_data)

                # Reorder columns
                column_order = [
                    'business_name', 'num_employees', 'contact_person', 'first_name',
                    'corporate_email', 'other_emails', 'website', 'phone', 'phone_type',
                    'street_address', 'zip_code', 'state', 'city'
                ]
                df = df[column_order]

                # Rename columns for display
                df.columns = [
                    'Business Name', 'Number of Employees', 'Contact Person', 'First Name',
                    'Corporate Email', 'Other Emails', 'Website', 'Phone', 'Phone Type',
                    'Street Address', 'Zip Code', 'State', 'City'
                ]

                # Display results
                st.subheader(f"📊 Extracted {len(employees_data)} Real Employee Records")
                st.success(f"✅ Found real employees working as {job_role} in {industry} companies in {city}, {country}")
                st.dataframe(df, use_container_width=True)

                # Download options
                col1, col2, col3 = st.columns(3)

                with col1:
                    # Excel download
                    buffer = BytesIO()
                    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                        df.to_excel(writer, index=False, sheet_name='Employee_Data')
                    buffer.seek(0)

                    st.download_button(
                        label="📥 Download Excel",
                        data=buffer,
                        file_name=f"employees_{job_role}_{industry}_{city}_{num_results}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )

                with col2:
                    # CSV download
                    csv = df.to_csv(index=False)
                    st.download_button(
                        label="📥 Download CSV",
                        data=csv,
                        file_name=f"employees_{job_role}_{industry}_{city}_{num_results}.csv",
                        mime="text/csv"
                    )

                with col3:
                    # JSON download
                    json_data = df.to_json(orient='records', indent=2)
                    st.download_button(
                        label="📥 Download JSON",
                        data=json_data,
                        file_name=f"employees_{job_role}_{industry}_{city}_{num_results}.json",
                        mime="application/json"
                    )

                st.success(f"✅ Successfully extracted {len(employees_data)} real employee records!")
                
                # Show API usage summary
                with st.expander("📈 API Usage Summary"):
                    st.markdown(f"""
                    **Data Sources Used:**
                    - 🔍 **Serper.dev**: Google search results for company discovery
                    - 📧 **Hunter.io**: Professional email extraction from company domains
                    - 👥 **People Data Labs**: Employee database search for {job_role} roles
                    - 📞 **NumVerify**: Phone number validation and formatting
                    - 🌐 **ScraperAPI/Direct**: Website content extraction for contact details
                    
                    **Extraction Strategy:**
                    - Multi-source data aggregation
                    - Real-time API calls
                    - Duplicate removal and data validation
                    - Contact information enrichment
                    """)
                        
            else:
                st.warning("⚠️ No employee data could be extracted. Try different search parameters or check your API keys.")

    # Instructions
    with st.expander("ℹ️ How This Enhanced Extraction Works"):
        st.markdown("""
        ## 🚀 Multi-API Data Extraction Process
        
        ### **1. Company Discovery (Serper.dev)**
        - Searches Google for companies in specified industry/location
        - Targets LinkedIn company pages, Crunchbase, business directories
        - Finds corporate websites and professional profiles
        
        ### **2. Employee Search (People Data Labs)**
        - Searches professional database for employees in specific roles
        - Finds CTO, CEO, and other leadership positions
        - Provides verified work emails and contact information
        
        ### **3. Email Extraction (Hunter.io)**
        - Extracts professional emails from company domains
        - Finds employee emails with job titles and confidence scores
        - Validates email formats and professional relevance
        
        ### **4. Website Scraping (ScraperAPI)**
        - Scrapes company websites for contact information
        - Extracts data from Contact Us, About Us, Team pages
        - Finds addresses, phone numbers, and additional emails
        
        ### **5. Phone Validation (NumVerify)**
        - Validates and formats phone numbers
        - Provides international format and line type
        - Identifies mobile, landline, and toll-free numbers
        
        ## 📊 Data Quality Features
        - **Duplicate Removal**: Eliminates duplicate entries across sources
        - **Data Validation**: Verifies email formats and phone numbers
        - **Contact Enrichment**: Combines data from multiple sources
        - **Real-time Processing**: Live API calls for fresh data
        
        ## 🎯 Best Results Tips
        - Use specific job roles (CTO, CEO) for better targeting
        - Major cities have more data availability
        - Technology companies have better online presence
        - Multiple API keys improve data coverage
        
        **Note**: This tool respects rate limits and follows ethical data extraction practices.
        """)


if __name__ == "__main__":
    main()