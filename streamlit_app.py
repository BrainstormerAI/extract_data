import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import time
from urllib.parse import quote, urljoin, urlparse
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import random

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EmployeeDataExtractor:
    def __init__(self):
        self.session = requests.Session()
        # Rotate user agents to avoid blocking
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ]
        self.session.headers.update({
            'User-Agent': random.choice(user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })

    def extract_emails_from_text(self, text):
        """Extract email addresses from text"""
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        emails = re.findall(email_pattern, text, re.IGNORECASE)

        # Filter out common noise emails
        noise_patterns = ['example.com', 'test.com', 'sample.com', 'placeholder.com', 'noreply', 'no-reply', 'support@', 'info@']
        filtered_emails = []

        for email in emails:
            if not any(noise in email.lower() for noise in noise_patterns) and len(email) > 5:
                filtered_emails.append(email)

        return list(set(filtered_emails))[:5]

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

        # Clean phone numbers
        clean_phones = []
        for phone in phones:
            if isinstance(phone, tuple):
                phone = phone[0] if phone[0] else phone[1] if len(phone) > 1 else ''

            clean_phone = re.sub(r'[^\d+()-.\s]', '', str(phone))
            if len(re.sub(r'[^\d]', '', clean_phone)) >= 10:
                clean_phones.append(clean_phone.strip())

        return list(set(clean_phones))[:3]

    def extract_names_from_text(self, text):
        """Extract potential employee names from text"""
        name_patterns = [
            r'(?:CEO|CTO|President|Director|Manager|VP|Vice President|Chief|Head|Lead|Founder|Co-Founder)[:\s-]+([A-Z][a-z]+\s+[A-Z][a-z]+)',
            r'([A-Z][a-z]+\s+[A-Z][a-z]+)[,\s-]+(?:CEO|CTO|President|Director|Manager|VP|Vice President|Chief|Head|Lead|Founder|Co-Founder)',
            r'Contact[:\s]+([A-Z][a-z]+\s+[A-Z][a-z]+)',
            r'([A-Z][a-z]+\s+[A-Z][a-z]+)[,\s]+(?:is|serves as|works as)',
            r'Mr\.?\s+([A-Z][a-z]+\s+[A-Z][a-z]+)',
            r'Ms\.?\s+([A-Z][a-z]+\s+[A-Z][a-z]+)',
            r'Dr\.?\s+([A-Z][a-z]+\s+[A-Z][a-z]+)',
        ]

        names = []
        for pattern in name_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            names.extend(matches)

        # Filter out noise
        noise_words = ['Contact Us', 'About Us', 'Terms Service', 'Privacy Policy', 'Get Started', 'Learn More', 'Read More', 'Click Here']
        filtered_names = []
        
        for name in names:
            if (name not in noise_words and 
                len(name.split()) == 2 and 
                all(len(part) > 1 for part in name.split()) and
                not any(char.isdigit() for char in name)):
                filtered_names.append(name)

        return list(set(filtered_names))[:5]

    def extract_address(self, text):
        """Extract address from text"""
        address_patterns = [
            r'(?:Address|Location|Office|Headquarters)[:\s]+([^.!?\n]+(?:Street|Road|Avenue|Lane|Drive|Plaza|Building|Block|Floor)[^.!?\n]*)',
            r'(\d+[^.!?\n]*(?:Street|Road|Avenue|Lane|Drive|Plaza|Building|Block|Floor)[^.!?\n]*)',
        ]

        for pattern in address_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                address = matches[0].strip()
                # Clean up the address
                address = re.sub(r'\s+', ' ', address)
                return address[:100]  # Limit length

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
        text_lower = text.lower()

        # Look for specific employee counts
        employee_patterns = [
            r'(\d+)[\s]*(?:employees|staff|people|team members)',
            r'team of (\d+)',
            r'workforce of (\d+)',
            r'(\d+)\+?\s*(?:employees|staff)'
        ]

        for pattern in employee_patterns:
            matches = re.findall(pattern, text_lower)
            if matches:
                try:
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
                except ValueError:
                    continue

        # Default estimation based on keywords
        if any(word in text_lower for word in ['startup', 'small team', 'boutique']):
            return '1-10'
        elif any(word in text_lower for word in ['growing', 'medium', 'mid-size']):
            return '50-200'
        elif any(word in text_lower for word in ['enterprise', 'corporation', 'multinational', 'global']):
            return '200-1000'
        elif any(word in text_lower for word in ['large', 'major', 'leading']):
            return '200-1000'

        return "10-50"  # Default

    def search_duckduckgo(self, query, max_results=10):
        """Search DuckDuckGo for companies"""
        try:
            search_url = f"https://duckduckgo.com/html/?q={quote(query)}"
            
            response = self.session.get(search_url, timeout=15)
            if response.status_code != 200:
                return []

            soup = BeautifulSoup(response.content, 'html.parser')
            results = []

            # Find search result links
            for link in soup.find_all('a', {'class': 'result__a'}):
                try:
                    url = link.get('href')
                    title = link.get_text().strip()
                    
                    if url and title:
                        # Skip social media and job sites
                        skip_domains = ['linkedin.com', 'facebook.com', 'twitter.com', 'youtube.com', 
                                      'indeed.com', 'naukri.com', 'glassdoor.com', 'monster.com']
                        
                        if not any(domain in url.lower() for domain in skip_domains):
                            results.append({
                                'name': title,
                                'url': url,
                                'source': 'DuckDuckGo'
                            })
                            
                            if len(results) >= max_results:
                                break
                                
                except Exception as e:
                    continue

            return results

        except Exception as e:
            logger.error(f"Error searching DuckDuckGo: {e}")
            return []

    def search_bing(self, query, max_results=10):
        """Search Bing for companies"""
        try:
            search_url = f"https://www.bing.com/search?q={quote(query)}"
            
            response = self.session.get(search_url, timeout=15)
            if response.status_code != 200:
                return []

            soup = BeautifulSoup(response.content, 'html.parser')
            results = []

            # Find search result links
            for link in soup.find_all('a'):
                try:
                    url = link.get('href')
                    if not url or not url.startswith('http'):
                        continue
                        
                    title = link.get_text().strip()
                    
                    if url and title and len(title) > 10:
                        # Skip unwanted domains
                        skip_domains = ['linkedin.com', 'facebook.com', 'twitter.com', 'youtube.com', 
                                      'indeed.com', 'naukri.com', 'glassdoor.com', 'monster.com',
                                      'bing.com', 'microsoft.com']
                        
                        if not any(domain in url.lower() for domain in skip_domains):
                            results.append({
                                'name': title,
                                'url': url,
                                'source': 'Bing'
                            })
                            
                            if len(results) >= max_results:
                                break
                                
                except Exception as e:
                    continue

            return results

        except Exception as e:
            logger.error(f"Error searching Bing: {e}")
            return []

    def search_companies(self, industry, city, country, limit=15):
        """Search for companies using multiple search engines"""
        search_queries = [
            f"{industry} companies in {city} {country}",
            f"{industry} firms {city} {country} contact",
            f"list of {industry} companies {city} {country}",
            f"{industry} businesses {city} {country} directory",
            f"top {industry} companies {city} {country}",
        ]

        all_companies = []

        for query in search_queries[:3]:  # Limit to 3 queries to avoid being blocked
            try:
                # Try DuckDuckGo first
                companies = self.search_duckduckgo(query, 5)
                all_companies.extend(companies)
                
                time.sleep(2)  # Rate limiting
                
                # Try Bing as backup
                if len(all_companies) < 5:
                    bing_companies = self.search_bing(query, 5)
                    all_companies.extend(bing_companies)
                    
                time.sleep(2)  # Rate limiting
                
            except Exception as e:
                logger.error(f"Error with query '{query}': {e}")
                continue

        # Remove duplicates based on URL
        unique_companies = []
        seen_urls = set()
        
        for company in all_companies:
            if company['url'] not in seen_urls:
                unique_companies.append(company)
                seen_urls.add(company['url'])

        return unique_companies[:limit]

    def scrape_company_website(self, company_url, company_name, job_role):
        """Scrape individual company website for employee information"""
        try:
            # Add random delay to avoid being blocked
            time.sleep(random.uniform(1, 3))
            
            response = self.session.get(company_url, timeout=20)
            if response.status_code != 200:
                return []

            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.decompose()
                
            text_content = soup.get_text(separator=' ', strip=True)

            # Look for team/about/contact pages
            potential_pages = []
            for link in soup.find_all('a', href=True):
                href = link['href'].lower()
                link_text = link.get_text().lower()

                if any(keyword in href or keyword in link_text for keyword in
                       ['about', 'team', 'management', 'leadership', 'contact', 'executive', 'staff', 'founder']):
                    full_url = urljoin(company_url, link['href'])
                    if full_url.startswith('http'):
                        potential_pages.append(full_url)

            # Extract information from main page
            all_emails = self.extract_emails_from_text(text_content)
            all_phones = self.extract_phone_numbers(text_content)
            all_names = self.extract_names_from_text(text_content)

            # Scrape key subpages (limit to 2 to avoid being blocked)
            for page_url in potential_pages[:2]:
                try:
                    time.sleep(random.uniform(1, 2))
                    sub_response = self.session.get(page_url, timeout=15)
                    if sub_response.status_code == 200:
                        sub_soup = BeautifulSoup(sub_response.content, 'html.parser')
                        
                        # Remove script and style elements
                        for script in sub_soup(["script", "style"]):
                            script.decompose()
                            
                        sub_text = sub_soup.get_text(separator=' ', strip=True)

                        all_emails.extend(self.extract_emails_from_text(sub_text))
                        all_phones.extend(self.extract_phone_numbers(sub_text))
                        all_names.extend(self.extract_names_from_text(sub_text))

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

            # Clean company name
            clean_company_name = re.sub(r'[^\w\s-]', '', company_name).strip()[:50]

            # If we found names, create individual records
            if all_names:
                for name in all_names[:3]:  # Limit to top 3 names
                    first_name = name.split()[0] if name.split() else ""

                    # Match corporate emails
                    corporate_email = ""
                    other_email = ""

                    if all_emails:
                        for email in all_emails:
                            if domain.lower() in email.lower():
                                corporate_email = email
                                break

                        other_emails = [e for e in all_emails if e != corporate_email]
                        other_email = other_emails[0] if other_emails else ""

                    employee_data = {
                        'Business Name': clean_company_name,
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
            if not employees and (all_emails or all_phones):
                employee_data = {
                    'Business Name': clean_company_name,
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
            logger.error(f"Error scraping {company_url}: {e}")
            return []

    def extract_employee_data(self, industry, job_role, city, country, limit=10):
        """Main method to extract employee data"""
        try:
            logger.info(f"Starting extraction for {job_role} in {industry} companies in {city}, {country}")

            # Step 1: Search for companies
            companies = self.search_companies(industry, city, country, limit * 2)

            if not companies:
                logger.warning("No companies found in search results")
                return []

            logger.info(f"Found {len(companies)} companies to scrape")

            # Step 2: Scrape each company website with limited concurrency
            all_employees = []

            # Use ThreadPoolExecutor with limited workers to avoid being blocked
            with ThreadPoolExecutor(max_workers=2) as executor:
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
                            logger.info(f"Extracted {len(employees)} records from {company['name']}")
                    except Exception as e:
                        logger.error(f"Error processing {company['name']}: {e}")
                        continue

            # Filter results - only include records with meaningful data
            filtered_employees = []
            for employee in all_employees:
                if employee['Business Name'] and (
                    employee['Corporate Email'] or
                    employee['Phone'] or
                    employee['Contact Person']
                ):
                    filtered_employees.append(employee)

            # Remove duplicates based on business name and contact person
            unique_employees = []
            seen_combinations = set()

            for employee in filtered_employees:
                key = (employee['Business Name'], employee['Contact Person'])
                if key not in seen_combinations:
                    unique_employees.append(employee)
                    seen_combinations.add(key)

            logger.info(f"Successfully extracted {len(unique_employees)} unique employee records")
            return unique_employees[:limit]

        except Exception as e:
            logger.error(f"Error in extract_employee_data: {e}")
            return []

def main():
    st.set_page_config(
        page_title="Employee Data Extractor",
        page_icon="🔍",
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
        text-align: center;
    }
    .search-container {
        background-color: #f8f9fa;
        padding: 1.5rem;
        border-radius: 10px;
        margin-bottom: 2rem;
    }
    .results-container {
        background-color: white;
        padding: 1.5rem;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .stAlert > div {
        padding: 1rem;
        border-radius: 8px;
    }
    </style>
    """, unsafe_allow_html=True)

    # Main header
    st.markdown("""
    <div class="main-header">
        <h1>🔍 Employee Data Extractor</h1>
        <p>Extract real employee data from company websites using advanced web scraping</p>
    </div>
    """, unsafe_allow_html=True)

    # Search parameters
    st.markdown('<div class="search-container">', unsafe_allow_html=True)
    st.subheader("Search Parameters")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        industry = st.text_input(
            "Industry",
            value="Technology",
            placeholder="e.g., Technology, Healthcare, Finance"
        )

    with col2:
        job_role = st.text_input(
            "Job Role",
            value="CTO",
            placeholder="e.g., CTO, CEO, Manager"
        )

    with col3:
        city = st.text_input(
            "City",
            value="Delhi",
            placeholder="e.g., Delhi, Mumbai, Bangalore"
        )

    with col4:
        country = st.text_input(
            "Country",
            value="India",
            placeholder="e.g., India, USA, UK"
        )

    # Number of results
    limit = st.slider("Number of Results", min_value=5, max_value=20, value=10)

    # Extract button
    if st.button("🚀 Extract Employee Data", type="primary", use_container_width=True):
        if not all([industry, job_role, city, country]):
            st.error("Please fill in all search parameters")
            return

        st.markdown('</div>', unsafe_allow_html=True)

        # Show search info
        st.info(f"🎯 Searching for {job_role} professionals in {industry} companies from {city}, {country}")

        # Progress tracking
        progress_bar = st.progress(0)
        status_text = st.empty()

        try:
            # Initialize extractor
            extractor = EmployeeDataExtractor()

            status_text.text("🔍 Searching for companies...")
            progress_bar.progress(25)

            # Extract data
            with st.spinner("Extracting employee data from websites..."):
                results = extractor.extract_employee_data(industry, job_role, city, country, limit)

            progress_bar.progress(100)

            if results:
                status_text.success(f"✅ Successfully extracted {len(results)} employee records!")

                # Display results
                st.markdown('<div class="results-container">', unsafe_allow_html=True)
                st.subheader("📊 Extracted Employee Data")

                # Create DataFrame
                df = pd.DataFrame(results)

                # Display table
                st.dataframe(
                    df,
                    use_container_width=True,
                    height=400,
                    column_config={
                        "Business Name": st.column_config.TextColumn("🏢 Company", width="large"),
                        "Contact Person": st.column_config.TextColumn("👤 Name", width="medium"),
                        "Corporate Email": st.column_config.TextColumn("📧 Corporate Email", width="large"),
                        "Phone": st.column_config.TextColumn("📱 Phone", width="medium"),
                        "Website": st.column_config.LinkColumn("🌐 Website", width="medium")
                    }
                )

                # Download options
                st.subheader("💾 Download Results")

                col1, col2, col3 = st.columns(3)

                with col1:
                    csv_data = df.to_csv(index=False)
                    st.download_button(
                        label="📄 Download CSV",
                        data=csv_data,
                        file_name=f"employees_{industry}_{city}_{country}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )

                with col2:
                    # Excel download
                    from io import BytesIO
                    excel_buffer = BytesIO()
                    df.to_excel(excel_buffer, index=False, engine='openpyxl')
                    excel_data = excel_buffer.getvalue()

                    st.download_button(
                        label="📊 Download Excel",
                        data=excel_data,
                        file_name=f"employees_{industry}_{city}_{country}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )

                with col3:
                    json_data = df.to_json(orient='records', indent=2)
                    st.download_button(
                        label="📋 Download JSON",
                        data=json_data,
                        file_name=f"employees_{industry}_{city}_{country}.json",
                        mime="application/json",
                        use_container_width=True
                    )

                # Statistics
                st.subheader("📈 Extraction Statistics")

                col1, col2, col3, col4 = st.columns(4)

                with col1:
                    st.metric("🏢 Companies Found", len(set(df['Business Name'])))

                with col2:
                    email_count = sum(1 for _, row in df.iterrows() if row['Corporate Email'] or row['Email'])
                    st.metric("📧 Emails Found", email_count)

                with col3:
                    phone_count = sum(1 for _, row in df.iterrows() if row['Phone'])
                    st.metric("📱 Phones Found", phone_count)

                with col4:
                    name_count = sum(1 for _, row in df.iterrows() if row['Contact Person'])
                    st.metric("👤 Names Found", name_count)

                st.markdown('</div>', unsafe_allow_html=True)

            else:
                status_text.warning("⚠️ No employee data found")
                st.warning("No results found. This could be due to:")
                st.markdown("""
                - **Limited publicly available information** on company websites
                - **Anti-scraping measures** by websites
                - **Geographic location** having fewer companies with online presence
                - **Industry-specific privacy practices**

                **Try these suggestions:**
                - Use broader industry terms (e.g., "Software" instead of "AI/ML")
                - Search in major tech cities (Mumbai, Bangalore, Hyderabad)
                - Try different job roles (CEO, Founder, Manager, Director)
                - Increase the number of results
                - Try different combinations of city/country
                """)

        except Exception as e:
            progress_bar.progress(0)
            status_text.error(f"❌ Error: {str(e)}")
            st.error("An error occurred during extraction. This might be due to:")
            st.markdown("""
            - **Network connectivity issues**
            - **Websites blocking automated requests**
            - **Rate limiting by search engines**
            - **Temporary server issues**

            Please try again in a few minutes with different parameters.
            """)

        finally:
            progress_bar.empty()

    else:
        st.markdown('</div>', unsafe_allow_html=True)

    # Information section
    with st.expander("ℹ️ How it works"):
        st.markdown("""
        **This tool extracts real employee data using advanced web scraping:**
        
        1. **🔍 Search**: Uses DuckDuckGo and Bing to find companies in your specified industry and location
        2. **🌐 Scrape**: Extracts employee information from company websites, about pages, and team sections
        3. **🧠 Parse**: Uses regex patterns and NLP to identify names, emails, phones, and addresses
        4. **🔧 Filter**: Removes duplicates, validates data, and cleans results
        5. **📊 Export**: Provides results in CSV, Excel, and JSON formats
        
        **Data Sources:**
        - Company websites and about pages
        - Team and leadership sections
        - Contact pages and directories
        - Publicly available business information
        
        **Features:**
        - ✅ Multiple search engines for better coverage
        - ✅ Smart rate limiting to avoid blocking
        - ✅ Advanced text parsing and extraction
        - ✅ Duplicate removal and data validation
        - ✅ Export in multiple formats
        """)

    with st.expander("⚖️ Legal & Ethical Considerations"):
        st.markdown("""
        **This tool follows ethical web scraping practices:**
        
        ✅ **What we do:**
        - Only scrape publicly available information
        - Implement rate limiting (2-3 seconds between requests)
        - Use appropriate user agents and headers
        - Handle errors gracefully without overwhelming servers
        - Respect website structure and content
        
        ❌ **What we don't do:**
        - Scrape password-protected or private content
        - Bypass CAPTCHAs or security measures
        - Overload servers with rapid requests
        - Store personal data permanently
        - Violate website terms of service
        
        **Legal Compliance:**
        - All data extracted is publicly available
        - Respects robots.txt guidelines where possible
        - Follows data minimization principles
        - Complies with applicable privacy laws
        """)

    st.markdown("---")
    st.markdown(
        "<div style='text-align: center; color: #666; padding: 1rem;'>"
        "Employee Data Extractor | Advanced Web Scraping Tool | Use Responsibly"
        "</div>",
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    main()