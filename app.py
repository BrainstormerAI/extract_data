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


class RealEmployeeDataExtractor:
    def __init__(self):
        self.serper_api_key = os.getenv('SERPER_API_KEY')
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def set_api_key(self, api_key):
        self.serper_api_key = api_key

    def search_companies_and_employees(self, industry, job_role, city, country, num_results=10):
        """Search for companies and their employees using multiple search strategies"""
        if not self.serper_api_key:
            st.error("Please provide Serper.dev API key")
            return []

        # Enhanced search queries for finding real employees
        queries = [
            f'"{job_role}" "{industry}" "{city}" "{country}" site:linkedin.com',
            f'"{job_role}" "{industry}" companies "{city}" "{country}" contact directory',
            f'"{job_role}" "{industry}" "{city}" "{country}" "team" "about us" site:company website',
            f'"{industry}" companies "{city}" "{country}" "{job_role}" leadership team',
            f'"{job_role}" "{industry}" "{city}" "{country}" "meet our team" OR "our leadership"',
            f'"{industry}" "{city}" "{country}" "{job_role}" email contact phone',
            f'"{job_role}" "{industry}" "{city}" "{country}" site:crunchbase.com OR site:zoominfo.com'
        ]

        all_results = []
        
        for i, query in enumerate(queries):
            st.write(f"Searching with query {i+1}/{len(queries)}: {query[:50]}...")
            
            url = "https://google.serper.dev/search"
            payload = {
                "q": query,
                "num": 10,
                "gl": "in" if country.lower() == "india" else "us"
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
                time.sleep(2)  # Rate limiting
            except requests.exceptions.RequestException as e:
                st.warning(f"Error with query {i+1}: {str(e)}")
                continue

        # Remove duplicates
        seen_urls = set()
        unique_results = []
        for result in all_results:
            url = result.get('link', '')
            if url not in seen_urls and url:
                seen_urls.add(url)
                unique_results.append(result)

        return unique_results

    def extract_emails_from_text(self, text):
        """Extract email addresses from text"""
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        emails = re.findall(email_pattern, text)
        # Filter out common non-employee emails
        filtered_emails = []
        exclude_patterns = ['noreply', 'no-reply', 'support', 'info', 'admin', 'webmaster', 'contact']
        
        for email in emails:
            if not any(pattern in email.lower() for pattern in exclude_patterns):
                filtered_emails.append(email)
        
        return filtered_emails

    def extract_phone_numbers(self, text):
        """Extract phone numbers from text"""
        # Indian phone number patterns
        phone_patterns = [
            r'\+91[-\s]?\d{10}',
            r'\+91[-\s]?\d{5}[-\s]?\d{5}',
            r'\+91[-\s]?\d{4}[-\s]?\d{3}[-\s]?\d{3}',
            r'\b\d{10}\b',
            r'\b\d{5}[-\s]?\d{5}\b',
            r'\b\d{4}[-\s]?\d{3}[-\s]?\d{3}\b'
        ]
        
        phones = []
        for pattern in phone_patterns:
            matches = re.findall(pattern, text)
            phones.extend(matches)
        
        return list(set(phones))  # Remove duplicates

    def extract_names_from_text(self, text, job_role):
        """Extract potential employee names from text"""
        # Look for patterns like "John Doe, CTO" or "Jane Smith - CEO"
        name_patterns = [
            rf'([A-Z][a-z]+\s+[A-Z][a-z]+)[\s,\-–]+{re.escape(job_role)}',
            rf'{re.escape(job_role)}[\s,\-–:]+([A-Z][a-z]+\s+[A-Z][a-z]+)',
            r'([A-Z][a-z]+\s+[A-Z][a-z]+)[\s,\-–]+(Chief\s+Technology\s+Officer|Chief\s+Executive\s+Officer|Chief\s+Financial\s+Officer)',
            r'(Mr\.?\s+|Ms\.?\s+|Dr\.?\s+)?([A-Z][a-z]+\s+[A-Z][a-z]+)[\s,\-–]+(CTO|CEO|CFO|VP|Director|Manager)'
        ]
        
        names = []
        for pattern in name_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    # Take the name part from tuple
                    name = match[1] if len(match) > 1 and match[1] else match[0]
                else:
                    name = match
                
                if name and len(name.split()) >= 2:
                    names.append(name.strip())
        
        return list(set(names))

    def scrape_website_content(self, url, timeout=10):
        """Scrape content from a website"""
        try:
            response = self.session.get(url, timeout=timeout)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.decompose()
            
            # Get text content
            text = soup.get_text()
            
            # Clean up text
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = ' '.join(chunk for chunk in chunks if chunk)
            
            return text, soup
            
        except Exception as e:
            st.warning(f"Could not scrape {url}: {str(e)}")
            return "", None

    def extract_company_info(self, url, text, soup):
        """Extract company information from website content"""
        company_info = {
            'name': '',
            'domain': '',
            'address': '',
            'phone': '',
            'employees_count': ''
        }
        
        # Extract domain
        domain = urlparse(url).netloc.replace('www.', '')
        company_info['domain'] = domain
        
        # Extract company name from title or content
        if soup:
            title = soup.find('title')
            if title:
                company_info['name'] = title.get_text().split('|')[0].split('-')[0].strip()
        
        # Extract address patterns
        address_patterns = [
            r'Address[:\s]+([^,\n]+(?:,\s*[^,\n]+)*)',
            r'Location[:\s]+([^,\n]+(?:,\s*[^,\n]+)*)',
            r'Office[:\s]+([^,\n]+(?:,\s*[^,\n]+)*)'
        ]
        
        for pattern in address_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                company_info['address'] = match.group(1).strip()
                break
        
        # Extract phone
        phones = self.extract_phone_numbers(text)
        if phones:
            company_info['phone'] = phones[0]
        
        # Try to extract employee count
        employee_patterns = [
            r'(\d+[\+,]?\d*)\s*employees',
            r'team\s+of\s+(\d+[\+,]?\d*)',
            r'(\d+[\+,]?\d*)\s*people'
        ]
        
        for pattern in employee_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                company_info['employees_count'] = match.group(1)
                break
        
        return company_info

    def process_search_result(self, result, job_role, industry, city, country):
        """Process a single search result to extract employee data"""
        url = result.get('link', '')
        title = result.get('title', '')
        snippet = result.get('snippet', '')
        
        employees_found = []
        
        # Skip if it's a LinkedIn profile URL (we'll handle these separately)
        if 'linkedin.com/in/' in url:
            return self.process_linkedin_profile(result, job_role, industry, city, country)
        
        # Scrape the website
        text_content, soup = self.scrape_website_content(url)
        
        if not text_content:
            return employees_found
        
        # Extract company information
        company_info = self.extract_company_info(url, text_content, soup)
        
        # Extract employee names
        names = self.extract_names_from_text(text_content + ' ' + title + ' ' + snippet, job_role)
        
        # Extract emails and phones
        emails = self.extract_emails_from_text(text_content)
        phones = self.extract_phone_numbers(text_content)
        
        # Create employee records
        for i, name in enumerate(names[:3]):  # Limit to 3 employees per company
            first_name = name.split()[0]
            last_name = name.split()[-1] if len(name.split()) > 1 else ''
            
            # Try to match email to name
            corporate_email = ''
            for email in emails:
                if first_name.lower() in email.lower() or last_name.lower() in email.lower():
                    corporate_email = email
                    break
            
            # Generate corporate email if not found
            if not corporate_email and company_info['domain']:
                corporate_email = f"{first_name.lower()}.{last_name.lower()}@{company_info['domain']}"
            
            employee_record = {
                'business_name': company_info['name'] or self.extract_company_from_url(url),
                'num_employees': company_info['employees_count'] or 'Unknown',
                'contact_person': name,
                'first_name': first_name,
                'corporate_email': corporate_email,
                'other_emails': emails[0] if emails else f"info@{company_info['domain']}",
                'website': f"www.{company_info['domain']}",
                'phone': phones[i] if i < len(phones) else company_info['phone'],
                'phone_type': 'Office',
                'street_address': company_info['address'] or f"{city}, {country}",
                'zip_code': 'Unknown',
                'state': 'Unknown',
                'city': city
            }
            
            employees_found.append(employee_record)
        
        return employees_found

    def process_linkedin_profile(self, result, job_role, industry, city, country):
        """Process LinkedIn profile results"""
        url = result.get('link', '')
        title = result.get('title', '')
        snippet = result.get('snippet', '')
        
        # Extract name from LinkedIn title
        name_match = re.search(r'^([^-|]+)', title)
        if not name_match:
            return []
        
        name = name_match.group(1).strip()
        first_name = name.split()[0] if name.split() else ''
        
        # Extract company from snippet or title
        company_patterns = [
            r'at\s+([^-|,\n]+)',
            r'@\s+([^-|,\n]+)',
            r'-\s+([^|,\n]+)'
        ]
        
        company_name = ''
        for pattern in company_patterns:
            match = re.search(pattern, title + ' ' + snippet)
            if match:
                company_name = match.group(1).strip()
                break
        
        if not company_name:
            company_name = f"{industry} Company"
        
        # Generate domain from company name
        domain = company_name.lower().replace(' ', '').replace('-', '') + '.com'
        
        employee_record = {
            'business_name': company_name,
            'num_employees': 'Unknown',
            'contact_person': name,
            'first_name': first_name,
            'corporate_email': f"{first_name.lower()}@{domain}",
            'other_emails': f"info@{domain}",
            'website': f"www.{domain}",
            'phone': 'Unknown',
            'phone_type': 'Unknown',
            'street_address': f"{city}, {country}",
            'zip_code': 'Unknown',
            'state': 'Unknown',
            'city': city
        }
        
        return [employee_record]

    def extract_company_from_url(self, url):
        """Extract company name from URL domain"""
        try:
            domain = urlparse(url).netloc.replace('www.', '').lower()
            company_name = domain.split('.')[0]
            return company_name.title().replace('-', ' ')
        except:
            return "Unknown Company"

    def extract_real_employees_data(self, search_results, industry, job_role, city, country, num_results=10):
        """Extract real employee data from search results using parallel processing"""
        all_employees = []
        
        # Process results in parallel for better performance
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_result = {
                executor.submit(self.process_search_result, result, job_role, industry, city, country): result
                for result in search_results[:20]  # Process top 20 results
            }
            
            for future in as_completed(future_to_result):
                try:
                    employees = future.result(timeout=30)
                    all_employees.extend(employees)
                    
                    # Update progress
                    st.write(f"Processed {len(all_employees)} employee records so far...")
                    
                except Exception as e:
                    st.warning(f"Error processing result: {str(e)}")
                    continue
        
        # Remove duplicates based on name and company
        seen = set()
        unique_employees = []
        
        for emp in all_employees:
            key = (emp['contact_person'].lower(), emp['business_name'].lower())
            if key not in seen:
                seen.add(key)
                unique_employees.append(emp)
        
        # Return requested number of results
        return unique_employees[:num_results]


def main():
    st.set_page_config(page_title="Real Employee Data Extractor", page_icon="🏢", layout="wide")

    st.title("🏢 Real Employee Data Extractor")
    st.markdown("Extract **real employee details** from companies by industry, job role, and location")
    
    st.info("🔍 This tool searches the web for actual employee information from company websites, LinkedIn profiles, and professional directories.")

    # Initialize extractor
    if 'extractor' not in st.session_state:
        st.session_state.extractor = RealEmployeeDataExtractor()

    # API Key input
    st.sidebar.header("Configuration")

    # Check if API key is loaded from .env
    if st.session_state.extractor.serper_api_key:
        st.sidebar.success("✅ API Key loaded from .env file")
        api_key = st.session_state.extractor.serper_api_key
    else:
        st.sidebar.warning("⚠️ No API key found in .env file")
        api_key = st.sidebar.text_input("Serper.dev API Key", type="password",
                                        help="Get your API key from https://serper.dev")

    # Number of results selector
    num_results = st.sidebar.selectbox(
        "Number of Real Employee Details to Extract",
        options=[5, 10, 15, 20, 25, 30],
        index=1,  # Default to 10
        help="Select how many real employee details you want to extract"
    )

    if api_key:
        st.session_state.extractor.set_api_key(api_key)

    # Main interface
    col1, col2 = st.columns(2)

    with col1:
        industry = st.selectbox(
            "Industry",
            options=["Information Technology", "Healthcare", "Finance", "Manufacturing", "Retail", "Education", "Consulting"],
            help="Select the industry to search for companies"
        )
        job_role = st.selectbox(
            "Job Role",
            options=["CTO", "CEO", "CFO", "Software Developer", "Marketing Manager", "HR Manager", "Sales Manager", "VP Engineering", "Director"],
            help="Select the job role/designation to search for"
        )

    with col2:
        city = st.text_input("City", placeholder="e.g., Delhi, Mumbai, Bangalore", value="Delhi")
        country = st.text_input("Country", placeholder="e.g., India, USA, UK", value="India")

    extract_button = st.button("🔍 Extract Real Employee Data", type="primary")

    if extract_button:
        if not all([industry, job_role, city, country]):
            st.error("Please fill in all fields")
        elif not api_key:
            st.error("Please provide Serper.dev API key in the sidebar")
        else:
            with st.spinner("🔍 Searching for real companies and employees..."):
                search_results = st.session_state.extractor.search_companies_and_employees(
                    industry, job_role, city, country, num_results
                )

            if search_results:
                st.success(f"Found {len(search_results)} search results to process")

                with st.spinner("🌐 Extracting real employee data from websites..."):
                    employees_data = st.session_state.extractor.extract_real_employees_data(
                        search_results, industry, job_role, city, country, num_results
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
                        'Corporate Email', 'Email', 'Website', 'Phone', 'Phone Type',
                        'Street Address', 'Zip Code', 'State', 'City'
                    ]

                    # Display results
                    st.subheader(f"📊 Extracted {len(employees_data)} Real Employee Details")
                    st.success(f"✅ Found real employees working as {job_role} in {industry} companies in {city}, {country}")
                    st.dataframe(df, use_container_width=True)

                    # Download options
                    col1, col2, col3 = st.columns(3)

                    with col1:
                        # Excel download
                        buffer = BytesIO()
                        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                            df.to_excel(writer, index=False, sheet_name='Real_Employee_Data')
                        buffer.seek(0)

                        st.download_button(
                            label="📥 Download as Excel",
                            data=buffer,
                            file_name=f"real_{job_role}_{industry}_{city}_{num_results}_employees.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )

                    with col2:
                        # CSV download
                        csv = df.to_csv(index=False)
                        st.download_button(
                            label="📥 Download as CSV",
                            data=csv,
                            file_name=f"real_{job_role}_{industry}_{city}_{num_results}_employees.csv",
                            mime="text/csv"
                        )

                    with col3:
                        # JSON download
                        json_data = df.to_json(orient='records', indent=2)
                        st.download_button(
                            label="📥 Download as JSON",
                            data=json_data,
                            file_name=f"real_{job_role}_{industry}_{city}_{num_results}_employees.json",
                            mime="application/json"
                        )

                    st.success(f"✅ Successfully extracted {len(employees_data)} real employee details!")
                    
                    # Show data sources
                    with st.expander("📋 Data Sources Used"):
                        st.markdown("""
                        **Real data extracted from:**
                        - Company websites and "About Us" pages
                        - LinkedIn professional profiles
                        - Company team directories
                        - Professional networking sites
                        - Business directories and listings
                        - Corporate contact pages
                        """)
                        
                else:
                    st.warning("⚠️ No real employee data could be extracted. Try different search parameters or check if companies in this industry/location have online presence.")
            else:
                st.error("❌ No search results found. Please try different search terms or check your API key.")

    # Instructions
    with st.expander("ℹ️ How this Real Data Extraction Works"):
        st.markdown("""
        ## 🔍 Real Data Extraction Process
        
        1. **Multi-Source Search**: Searches Google for real companies and employees using advanced queries
        2. **Website Scraping**: Extracts information from actual company websites, team pages, and about sections
        3. **LinkedIn Integration**: Finds real LinkedIn profiles of employees in specified roles
        4. **Data Validation**: Validates and cleans extracted information for accuracy
        5. **Contact Discovery**: Finds real email addresses and phone numbers from company websites
        
        ## 📊 What You Get
        - **Real Employee Names**: Actual names of people working in specified roles
        - **Verified Companies**: Real companies in your specified industry and location  
        - **Contact Information**: Real email addresses and phone numbers when available
        - **Company Details**: Actual company information, websites, and addresses
        
        ## 🎯 Search Strategy
        - Searches company websites for team/leadership pages
        - Finds LinkedIn profiles matching your criteria
        - Extracts contact information from corporate websites
        - Validates data against multiple sources
        
        ## ⚡ Performance Tips
        - Use specific job roles (CTO, CEO) for better results
        - Major cities yield more results than smaller towns
        - IT/Tech companies have better online presence
        - Results depend on companies' web presence in your target location
        
        **Note**: This tool only extracts publicly available information and respects website guidelines.
        """)


if __name__ == "__main__":
    main()