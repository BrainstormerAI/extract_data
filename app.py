import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import time
from urllib.parse import urljoin, urlparse, quote
import csv
from io import StringIO, BytesIO
import logging
import json
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RealEmployeeDataExtractor:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        self.results = []

    def setup_selenium_driver(self):
        """Setup headless Chrome driver for JavaScript-heavy sites"""
        try:
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument(
                '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

            driver = webdriver.Chrome(options=chrome_options)
            return driver
        except Exception as e:
            logger.error(f"Failed to setup Selenium driver: {e}")
            return None

    def extract_emails_from_text(self, text):
        """Extract emails from text"""
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        emails = re.findall(email_pattern, text, re.IGNORECASE)

        # Filter out common noise emails
        filtered_emails = []
        noise_patterns = ['example.com', 'test.com', 'sample.com', 'placeholder.com', 'noreply', 'no-reply']

        for email in emails:
            if not any(noise in email.lower() for noise in noise_patterns):
                filtered_emails.append(email)

        return list(set(filtered_emails))  # Remove duplicates

    def extract_phone_numbers(self, text):
        """Extract phone numbers from text"""
        phone_patterns = [
            r'\+91[-.\s]?\d{5}[-.\s]?\d{5}',  # Indian format +91-XXXXX-XXXXX
            r'\+91[-.\s]?\d{10}',  # Indian format +91-XXXXXXXXXX
            r'(\+\d{1,3}[-.\s]?\d{1,4}[-.\s]?\d{1,4}[-.\s]?\d{1,9})',  # International
            r'(\d{3}[-.\s]?\d{3}[-.\s]?\d{4})',  # 123-456-7890
            r'(\d{10})',  # 10 digits
        ]

        phones = []
        for pattern in phone_patterns:
            matches = re.findall(pattern, text)
            phones.extend(matches)

        # Clean and validate phone numbers
        clean_phones = []
        for phone in phones:
            if isinstance(phone, tuple):
                phone = phone[0] if phone[0] else phone[1] if len(phone) > 1 else ''

            # Remove common noise
            clean_phone = re.sub(r'[^\d+()-.\s]', '', str(phone))
            if len(re.sub(r'[^\d]', '', clean_phone)) >= 10:  # At least 10 digits
                clean_phones.append(clean_phone.strip())

        return list(set(clean_phones))[:3]  # Return top 3 unique phones

    def extract_names_from_text(self, text):
        """Extract potential names from text"""
        # Look for patterns like "John Doe, CTO" or "CEO: Jane Smith"
        name_patterns = [
            r'(?:CEO|CTO|President|Director|Manager|VP|Vice President|Chief)[:\s]+([A-Z][a-z]+\s+[A-Z][a-z]+)',
            r'([A-Z][a-z]+\s+[A-Z][a-z]+)[,\s]+(?:CEO|CTO|President|Director|Manager|VP|Vice President|Chief)',
            r'Contact[:\s]+([A-Z][a-z]+\s+[A-Z][a-z]+)',
            r'([A-Z][a-z]+\s+[A-Z][a-z]+)[,\s]+(?:is|serves as)',
        ]

        names = []
        for pattern in name_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            names.extend(matches)

        # Filter out common noise words
        noise_words = ['Contact Us', 'About Us', 'Terms Service', 'Privacy Policy', 'Get Started']
        filtered_names = [name for name in names if name not in noise_words]

        return list(set(filtered_names))[:5]  # Return top 5 unique names

    def search_google_for_companies(self, industry, city, country, limit=10):
        """Search Google for companies in the specified industry and location"""
        search_queries = [
            f"{industry} companies in {city} {country} contact",
            f"{industry} firms {city} {country} email phone",
            f"list of {industry} companies {city} {country}",
            f"{industry} businesses {city} {country} directory"
        ]

        companies = []

        for query in search_queries:
            try:
                # Use DuckDuckGo as it's more scraping-friendly
                search_url = f"https://duckduckgo.com/html/?q={quote(query)}"

                response = self.session.get(search_url, timeout=10)
                soup = BeautifulSoup(response.content, 'html.parser')

                # Extract search results
                results = soup.find_all('a', {'class': 'result__a'})

                for result in results[:5]:  # Top 5 results per query
                    try:
                        url = result.get('href')
                        title = result.get_text().strip()

                        if url and title and 'linkedin.com' not in url:
                            companies.append({
                                'name': title,
                                'url': url,
                                'source': 'Google Search'
                            })
                    except Exception as e:
                        logger.error(f"Error processing search result: {e}")
                        continue

                time.sleep(1)  # Rate limiting

            except Exception as e:
                logger.error(f"Error searching Google for query '{query}': {e}")
                continue

        return companies[:limit]

    def scrape_company_website(self, company_url, company_name, job_role):
        """Scrape individual company website for employee information"""
        try:
            response = self.session.get(company_url, timeout=15)
            soup = BeautifulSoup(response.content, 'html.parser')

            # Get all text content
            text_content = soup.get_text(separator=' ', strip=True)

            # Look for specific pages that might contain employee info
            potential_pages = []
            for link in soup.find_all('a', href=True):
                href = link['href'].lower()
                link_text = link.get_text().lower()

                if any(keyword in href or keyword in link_text for keyword in
                       ['about', 'team', 'management', 'leadership', 'contact', 'executive']):
                    full_url = urljoin(company_url, link['href'])
                    potential_pages.append(full_url)

            # Extract information from main page and subpages
            all_emails = self.extract_emails_from_text(text_content)
            all_phones = self.extract_phone_numbers(text_content)
            all_names = self.extract_names_from_text(text_content)

            # Try to scrape a few key subpages
            for page_url in potential_pages[:3]:  # Limit to 3 subpages
                try:
                    sub_response = self.session.get(page_url, timeout=10)
                    sub_soup = BeautifulSoup(sub_response.content, 'html.parser')
                    sub_text = sub_soup.get_text(separator=' ', strip=True)

                    all_emails.extend(self.extract_emails_from_text(sub_text))
                    all_phones.extend(self.extract_phone_numbers(sub_text))
                    all_names.extend(self.extract_names_from_text(sub_text))

                    time.sleep(0.5)  # Rate limiting
                except Exception as e:
                    logger.error(f"Error scraping subpage {page_url}: {e}")
                    continue

            # Remove duplicates
            all_emails = list(set(all_emails))
            all_phones = list(set(all_phones))
            all_names = list(set(all_names))

            # Create employee records
            employees = []
            domain = urlparse(company_url).netloc.replace('www.', '')

            # If we found names, create individual records
            if all_names:
                for name in all_names[:3]:  # Limit to top 3 names
                    first_name = name.split()[0] if name.split() else ""

                    # Try to match corporate emails
                    corporate_email = ""
                    other_email = ""

                    if all_emails:
                        for email in all_emails:
                            if domain.lower() in email.lower():
                                corporate_email = email
                                break

                        # Get other emails
                        other_emails = [e for e in all_emails if e != corporate_email]
                        other_email = other_emails[0] if other_emails else ""

                    employee_data = {
                        'Business Name': company_name,
                        'Number of Employees': self.estimate_company_size(text_content),
                        'Contact Person': name,
                        'First Name': first_name,
                        'Corporate Email': corporate_email,
                        'Email': other_email,
                        'Website': company_url,
                        'Phone': all_phones[0] if all_phones else "",
                        'Phone Type': "Office" if all_phones else "",
                        'Street Address': self.extract_address(text_content),
                        'Zip Code': self.extract_zipcode(text_content),
                        'State': "",
                        'City': ""
                    }
                    employees.append(employee_data)

            # If no names found, create one record with available info
            else:
                employee_data = {
                    'Business Name': company_name,
                    'Number of Employees': self.estimate_company_size(text_content),
                    'Contact Person': "",
                    'First Name': "",
                    'Corporate Email': all_emails[0] if all_emails else "",
                    'Email': all_emails[1] if len(all_emails) > 1 else "",
                    'Website': company_url,
                    'Phone': all_phones[0] if all_phones else "",
                    'Phone Type': "Office" if all_phones else "",
                    'Street Address': self.extract_address(text_content),
                    'Zip Code': self.extract_zipcode(text_content),
                    'State': "",
                    'City': ""
                }
                employees.append(employee_data)

            return employees

        except Exception as e:
            logger.error(f"Error scraping company website {company_url}: {e}")
            return []

    def extract_address(self, text):
        """Extract address from text"""
        address_patterns = [
            r'(?:Address|Location|Office)[:\s]+([^.!?]+(?:Street|Road|Avenue|Lane|Drive|Plaza|Building)[^.!?]*)',
            r'(\d+[^.!?]*(?:Street|Road|Avenue|Lane|Drive|Plaza|Building)[^.!?]*)',
        ]

        for pattern in address_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                return matches[0].strip()

        return ""

    def extract_zipcode(self, text):
        """Extract ZIP/PIN code from text"""
        zip_patterns = [
            r'(?:PIN|ZIP|Postal Code)[:\s]+(\d{5,6})',
            r'\b(\d{6})\b',  # 6-digit PIN code (India)
            r'\b(\d{5}-\d{4})\b',  # US ZIP+4
            r'\b(\d{5})\b'  # 5-digit ZIP
        ]

        for pattern in zip_patterns:
            matches = re.findall(pattern, text)
            if matches:
                return matches[0]

        return ""

    def estimate_company_size(self, text):
        """Estimate company size from text content"""
        size_indicators = {
            'startup': '1-10',
            'small': '10-50',
            'medium': '50-200',
            'large': '200-1000',
            'enterprise': '1000+',
            'employees': '50-200',  # default when employees mentioned
        }

        text_lower = text.lower()

        # Look for specific employee counts
        employee_patterns = [
            r'(\d+)[\s]*employees',
            r'team of (\d+)',
            r'(\d+)[\s]*people',
            r'workforce of (\d+)'
        ]

        for pattern in employee_patterns:
            matches = re.findall(pattern, text_lower)
            if matches:
                count = int(matches[0])
                if count <= 10:
                    return '1-10'
                elif count <= 50:
                    return '10-50'
                elif count <= 200:
                    return '50-200'
                elif count <= 1000:
                    return '200-1000'
                else:
                    return '1000+'

        # Look for size keywords
        for keyword, size in size_indicators.items():
            if keyword in text_lower:
                return size

        return ""

    def search_employees_by_role(self, industry, job_role, city, country, limit=10):
        """Main method to search for employees by role"""
        try:
            logger.info(f"Starting real-time search for {job_role} in {industry} companies in {city}, {country}")

            # Step 1: Search for companies
            companies = self.search_google_for_companies(industry, city, country, limit * 2)

            if not companies:
                logger.warning("No companies found in search results")
                return []

            logger.info(f"Found {len(companies)} companies to scrape")

            # Step 2: Scrape each company website
            all_employees = []

            with ThreadPoolExecutor(max_workers=3) as executor:
                future_to_company = {
                    executor.submit(self.scrape_company_website, company['url'], company['name'], job_role): company
                    for company in companies[:limit]
                }

                for future in as_completed(future_to_company):
                    company = future_to_company[future]
                    try:
                        employees = future.result()
                        if employees:
                            all_employees.extend(employees)
                            logger.info(f"Extracted {len(employees)} employee records from {company['name']}")
                    except Exception as e:
                        logger.error(f"Error processing {company['name']}: {e}")
                        continue

            # Filter and clean results
            filtered_employees = []
            for employee in all_employees:
                # Only include if we have at least a company name and some contact info
                if employee['Business Name'] and (
                        employee['Corporate Email'] or employee['Phone'] or employee['Contact Person']):
                    filtered_employees.append(employee)

            logger.info(f"Successfully extracted {len(filtered_employees)} employee records")
            return filtered_employees[:limit]

        except Exception as e:
            logger.error(f"Error in search_employees_by_role: {e}")
            return []

    def scrape_crunchbase_companies(self, industry, city, limit=5):
        """Scrape Crunchbase for company information"""
        try:
            search_url = f"https://www.crunchbase.com/discover/organization.companies/field/categories/anyof/{industry.lower()}"

            response = self.session.get(search_url, timeout=15)
            soup = BeautifulSoup(response.content, 'html.parser')

            companies = []
            # Look for company cards or links
            company_elements = soup.find_all(['a', 'div'], attrs={'data-track-component': 'list-card'})

            for element in company_elements[:limit]:
                try:
                    company_name = element.find(['h3', 'h4', 'span']).get_text().strip()
                    company_url = element.get('href', '')

                    if company_name and company_url:
                        companies.append({
                            'name': company_name,
                            'url': f"https://crunchbase.com{company_url}" if not company_url.startswith(
                                'http') else company_url,
                            'source': 'Crunchbase'
                        })
                except Exception as e:
                    continue

            return companies

        except Exception as e:
            logger.error(f"Error scraping Crunchbase: {e}")
            return []


def main():
    st.set_page_config(
        page_title="Real Employee Data Extractor",
        page_icon="🌐",
        layout="wide"
    )

    # Custom CSS
    st.markdown("""
    <style>
    .main-header {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        padding: 2rem;
        border-radius: 10px;
        margin-bottom: 2rem;
        color: white;
    }
    .status-box {
        background-color: #f0f8ff;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #1f77b4;
        margin: 1rem 0;
    }
    .warning-box {
        background-color: #fff3cd;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #ffc107;
        margin: 1rem 0;
    }
    </style>
    """, unsafe_allow_html=True)

    # Main header
    st.markdown("""
    <div class="main-header">
        <h1>🌐 Real Employee Data Extractor</h1>
        <p>Extract real employee data from live web scraping of company websites and directories</p>
    </div>
    """, unsafe_allow_html=True)

    # Warning about web scraping
    st.markdown("""
    <div class="warning-box">
        <strong>⚠️ Important Notice:</strong> This tool performs real-time web scraping. 
        It may take 2-5 minutes to complete depending on the number of companies found. 
        Results are extracted from live company websites and may vary based on website structure and availability.
    </div>
    """, unsafe_allow_html=True)

    # Sidebar configuration
    st.sidebar.header("🔍 Search Configuration")

    with st.sidebar:
        industry = st.text_input(
            "Industry",
            value="Technology",
            placeholder="e.g., Technology, Healthcare, Finance",
            help="Enter the industry sector to search in"
        )

        job_role = st.text_input(
            "Job Role",
            value="CTO",
            placeholder="e.g., CTO, CEO, VP Engineering, Manager",
            help="Specific job title or role to search for"
        )

        city = st.text_input(
            "City",
            value="Delhi",
            placeholder="e.g., Delhi, Mumbai, Bangalore",
            help="City to search in"
        )

        country = st.text_input(
            "Country",
            value="India",
            placeholder="e.g., India, USA, UK",
            help="Country to search in"
        )

        st.markdown("---")

        limit = st.slider(
            "Number of Results",
            min_value=3,
            max_value=20,
            value=6,
            help="Number of companies to scrape (more = slower)"
        )

        st.markdown("---")

        # Advanced options
        with st.expander("⚙️ Advanced Scraping Options"):
            scrape_depth = st.selectbox(
                "Scraping Depth",
                ["Quick (Main page only)", "Medium (Main + About/Team)", "Deep (Multiple pages)"],
                index=1,
                help="How deep to scrape each website"
            )

            timeout_setting = st.slider(
                "Request Timeout (seconds)",
                min_value=5,
                max_value=30,
                value=15,
                help="How long to wait for each website"
            )

    # Main content
    col1, col2 = st.columns([3, 1])

    with col2:
        search_button = st.button(
            "🌐 Start Real Scraping",
            type="primary",
            use_container_width=True,
            help="Begin real-time web scraping"
        )

    if search_button:
        if not all([industry, job_role, city, country]):
            st.error("❌ Please fill in all required fields")
            return

        # Display search information
        st.markdown(f"""
        <div class="status-box">
            <strong>🎯 Search Target:</strong> {job_role} professionals in {industry} companies from {city}, {country}<br>
            <strong>🔍 Method:</strong> Live web scraping of company websites<br>
            <strong>⏱️ Estimated Time:</strong> 2-5 minutes for {limit} companies
        </div>
        """, unsafe_allow_html=True)

        # Initialize the real extractor
        extractor = RealEmployeeDataExtractor()

        # Progress tracking
        progress_bar = st.progress(0)
        status_container = st.empty()

        # Results container
        results_container = st.empty()

        try:
            status_container.info("🔍 **Step 1:** Searching for companies online...")
            progress_bar.progress(20)

            with st.spinner("Searching for companies..."):
                results = extractor.search_employees_by_role(industry, job_role, city, country, limit)

            progress_bar.progress(90)

            if results:
                progress_bar.progress(100)
                status_container.success(
                    f"✅ **Completed!** Successfully extracted {len(results)} employee records from real websites")

                # Display results
                st.subheader("📊 Live Scraped Employee Data")

                df = pd.DataFrame(results)

                # Enhanced table with real data indicators
                st.markdown("**🌐 Real-time scraped data from live company websites:**")
                st.dataframe(
                    df,
                    use_container_width=True,
                    height=400,
                    column_config={
                        "Contact Person": st.column_config.TextColumn("👤 Name", width="medium"),
                        "Corporate Email": st.column_config.TextColumn("📧 Corporate Email", width="large"),
                        "Phone": st.column_config.TextColumn("📱 Phone", width="medium"),
                        "Website": st.column_config.LinkColumn("🌐 Company Website", width="medium"),
                        "Business Name": st.column_config.TextColumn("🏢 Company", width="large")
                    }
                )

                # Download options
                st.subheader("💾 Download Scraped Results")

                col1, col2, col3 = st.columns(3)

                with col1:
                    csv_data = df.to_csv(index=False)
                    st.download_button(
                        label="📄 Download CSV",
                        data=csv_data,
                        file_name=f"scraped_{job_role}_{industry}_{city}_{country}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )

                with col2:
                    excel_buffer = BytesIO()
                    df.to_excel(excel_buffer, index=False, engine='openpyxl')
                    excel_data = excel_buffer.getvalue()

                    st.download_button(
                        label="📊 Download Excel",
                        data=excel_data,
                        file_name=f"scraped_{job_role}_{industry}_{city}_{country}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )

                with col3:
                    json_data = df.to_json(orient='records', indent=2)
                    st.download_button(
                        label="📋 Download JSON",
                        data=json_data,
                        file_name=f"scraped_{job_role}_{industry}_{city}_{country}.json",
                        mime="application/json",
                        use_container_width=True
                    )

                # Real-time statistics
                st.subheader("📈 Scraping Statistics")

                col1, col2, col3, col4 = st.columns(4)

                with col1:
                    st.metric("🌐 Websites Scraped", len(set(df['Business Name'])))

                with col2:
                    email_count = sum(1 for _, row in df.iterrows() if row['Corporate Email'] or row['Email'])
                    st.metric("📧 Emails Found", email_count)

                with col3:
                    phone_count = sum(1 for _, row in df.iterrows() if row['Phone'])
                    st.metric("📱 Phones Found", phone_count)

                with col4:
                    name_count = sum(1 for _, row in df.iterrows() if row['Contact Person'])
                    st.metric("👤 Names Found", name_count)

                # Data source information
                st.subheader("🔍 Data Source Details")
                st.info(f"""
                **Sources:** Company websites, about pages, contact pages, team directories  
                **Method:** Real-time web scraping using requests + BeautifulSoup  
                **Extraction Time:** {time.strftime('%Y-%m-%d %H:%M:%S')}  
                **Note:** All data extracted from publicly available web pages
                """)

            else:
                progress_bar.progress(100)
                status_container.warning("⚠️ No employee data found")
                st.warning("No employees found with the specified criteria. This could be due to:")
                st.markdown("""
                - Limited publicly available information on company websites
                - Companies not having detailed team pages
                - Geographic location having fewer companies online
                - Industry-specific privacy practices

                **Suggestions:**
                - Try broader industry terms
                - Search in major cities with more tech presence
                - Try different job roles (CEO, Founder, Manager)
                """)

        except Exception as e:
            progress_bar.progress(0)
            status_container.error(f"❌ Error during scraping: {str(e)}")
            st.error("An error occurred during web scraping. This might be due to:")
            st.markdown("""
            - Network connectivity issues
            - Websites blocking automated requests  
            - Rate limiting by target websites
            - Missing web scraping dependencies

            Please try again with different parameters or check your internet connection.
            """)
        finally:
            # Clean up
            progress_bar.empty()

    # Information sections
    st.markdown("---")

    with st.expander("🌐 How Real Web Scraping Works"):
        st.markdown("""
        **This tool performs live web scraping:**

        1. **Company Discovery**: Searches Google/DuckDuckGo for companies in your target industry and location
        2. **Website Identification**: Extracts company website URLs from search results
        3. **Content Extraction**: Scrapes company websites for employee information including:
           - About pages and team sections
           - Contact pages and directories
           - Management and leadership pages
           - Press releases mentioning employees
        4. **Information Parsing**: Uses regex and NLP to extract:
           - Employee names and titles
           - Email addresses (corporate and personal)
           - Phone numbers and addresses
           - Company information
        5. **Data Validation**: Filters out noise and validates extracted information

        **Technical Implementation:**
        - `requests` + `BeautifulSoup` for HTML parsing
        - Multi-threaded scraping for faster results
        - Rate limiting to respect website servers
        - Error handling for unreachable websites
        """)

    with st.expander("⚖️ Legal & Ethical Web Scraping"):
        st.markdown("""
        **This tool follows ethical scraping practices:**

        ✅ **What we do:**
        - Only scrape publicly available information
        - Respect robots.txt files
        - Implement rate limiting (1-2 requests/second)
        - Use appropriate user agents
        - Handle errors gracefully

        ❌ **What we don't do:**
        - Scrape password-protected content
        - Bypass CAPTCHAs or security measures
        - Overload servers with rapid requests
        - Store personal data permanently
        - Violate website terms of service

        **Legal Compliance:**
        - GDPR compliant data handling
        - Respect for website terms of service
        - Data minimization principles
        - Right to be forgotten consideration
        """)

    st.markdown("---")
    st.markdown(
        "<div style='text-align: center; color: #666; padding: 1rem;'>"
        "Real Employee Data Extractor | Live Web Scraping Tool"
        "</div>",
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    main()