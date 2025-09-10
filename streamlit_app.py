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

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GoogleEmployeeExtractor:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })

    def extract_emails_from_text(self, text):
        """Extract email addresses from text"""
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        emails = re.findall(email_pattern, text, re.IGNORECASE)

        # Filter out common noise emails
        noise_patterns = ['example.com', 'test.com', 'sample.com', 'placeholder.com', 'noreply', 'no-reply']
        filtered_emails = []

        for email in emails:
            if not any(noise in email.lower() for noise in noise_patterns):
                filtered_emails.append(email)

        return list(set(filtered_emails))[:5]  # Return top 5 unique emails

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
            r'(?:CEO|CTO|President|Director|Manager|VP|Vice President|Chief|Head|Lead)[:\s]+([A-Z][a-z]+\s+[A-Z][a-z]+)',
            r'([A-Z][a-z]+\s+[A-Z][a-z]+)[,\s]+(?:CEO|CTO|President|Director|Manager|VP|Vice President|Chief|Head|Lead)',
            r'Contact[:\s]+([A-Z][a-z]+\s+[A-Z][a-z]+)',
            r'([A-Z][a-z]+\s+[A-Z][a-z]+)[,\s]+(?:is|serves as)',
            r'Mr\.?\s+([A-Z][a-z]+\s+[A-Z][a-z]+)',
            r'Ms\.?\s+([A-Z][a-z]+\s+[A-Z][a-z]+)',
        ]

        names = []
        for pattern in name_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            names.extend(matches)

        # Filter out noise
        noise_words = ['Contact Us', 'About Us', 'Terms Service', 'Privacy Policy', 'Get Started', 'Learn More']
        filtered_names = [name for name in names if name not in noise_words and len(name.split()) == 2]

        return list(set(filtered_names))[:5]

    def extract_address(self, text):
        """Extract address from text"""
        address_patterns = [
            r'(?:Address|Location|Office)[:\s]+([^.!?\n]+(?:Street|Road|Avenue|Lane|Drive|Plaza|Building|Block)[^.!?\n]*)',
            r'(\d+[^.!?\n]*(?:Street|Road|Avenue|Lane|Drive|Plaza|Building|Block)[^.!?\n]*)',
        ]

        for pattern in address_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                return matches[0].strip()[:100]  # Limit length

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

        # Default estimation based on keywords
        if any(word in text_lower for word in ['startup', 'small team']):
            return '1-10'
        elif any(word in text_lower for word in ['growing', 'medium']):
            return '50-200'
        elif any(word in text_lower for word in ['enterprise', 'corporation']):
            return '200-1000'

        return "10-50"  # Default

    def search_google_companies(self, industry, city, country, limit=10):
        """Search for companies using Google Custom Search API"""

        # 🔑 Add your Google API Key and CSE ID here
        api_key = "AIzaSyAzNcYVARWf_cXKbBLdroLfRlHTS7XX8BA"
        cse_id = "d59b581ca6cbe4e5d"

        search_queries = [
            f"{industry} companies in {city} {country} contact email phone",
            f"{industry} firms {city} {country} CTO CEO director",
            f"list of {industry} companies {city} {country} management team",
            f"{industry} businesses {city} {country} leadership contact"
        ]

        companies = []

        for query in search_queries:
            try:
                url = f"https://www.googleapis.com/customsearch/v1?q={quote(query)}&key={api_key}&cx={cse_id}"
                response = self.session.get(url, timeout=15)

                if response.status_code == 200:
                    data = response.json()
                    for item in data.get("items", [])[:5]:  # Top 5 per query
                        link = item.get("link")
                        title = item.get("title")

                        if link and title and not any(skip in link.lower() for skip in
                                                      ['linkedin.com', 'facebook.com', 'twitter.com', 'youtube.com']):
                            companies.append({
                                'name': title,
                                'url': link,
                                'source': 'Google CSE'
                            })
                else:
                    logger.error(f"Google API error {response.status_code}: {response.text}")

                time.sleep(1)  # rate limiting

            except Exception as e:
                logger.error(f"Error searching query '{query}': {e}")
                continue

        # Deduplicate based on URL
        unique_companies = []
        seen_urls = set()
        for company in companies:
            if company['url'] not in seen_urls:
                unique_companies.append(company)
                seen_urls.add(company['url'])

        return unique_companies[:limit]

    def scrape_company_website(self, company_url, company_name, job_role):
        """Scrape individual company website for employee information"""
        try:
            response = self.session.get(company_url, timeout=20)
            if response.status_code != 200:
                return []

            soup = BeautifulSoup(response.content, 'html.parser')
            text_content = soup.get_text(separator=' ', strip=True)

            # Look for team/about/contact pages
            potential_pages = []
            for link in soup.find_all('a', href=True):
                href = link['href'].lower()
                link_text = link.get_text().lower()

                if any(keyword in href or keyword in link_text for keyword in
                       ['about', 'team', 'management', 'leadership', 'contact', 'executive', 'staff']):
                    full_url = urljoin(company_url, link['href'])
                    potential_pages.append(full_url)

            # Extract information from main page
            all_emails = self.extract_emails_from_text(text_content)
            all_phones = self.extract_phone_numbers(text_content)
            all_names = self.extract_names_from_text(text_content)

            # Scrape key subpages
            for page_url in potential_pages[:3]:  # Limit to 3 subpages
                try:
                    sub_response = self.session.get(page_url, timeout=15)
                    if sub_response.status_code == 200:
                        sub_soup = BeautifulSoup(sub_response.content, 'html.parser')
                        sub_text = sub_soup.get_text(separator=' ', strip=True)

                        all_emails.extend(self.extract_emails_from_text(sub_text))
                        all_phones.extend(self.extract_phone_numbers(sub_text))
                        all_names.extend(self.extract_names_from_text(sub_text))

                    time.sleep(1)  # Rate limiting
                except Exception:
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
                        'Business Name': company_name[:50],  # Limit length
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
                    'Business Name': company_name[:50],
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
            companies = self.search_google_companies(industry, city, country, limit * 2)

            if not companies:
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
    </style>
    """, unsafe_allow_html=True)

    # Main header
    st.markdown("""
    <div class="main-header">
        <h1>🔍 Employee Data Extractor</h1>
        <p>Extract real employee data from Google search results</p>
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
    limit = st.slider("Number of Results", min_value=5, max_value=25, value=10)

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
            extractor = GoogleEmployeeExtractor()

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
                st.warning("No results found. Try:")
                st.markdown("""
                - Using broader industry terms
                - Searching in major cities
                - Trying different job roles
                - Increasing the number of results
                """)

        except Exception as e:
            progress_bar.progress(0)
            status_text.error(f"❌ Error: {str(e)}")
            st.error("An error occurred during extraction. Please try again with different parameters.")

        finally:
            progress_bar.empty()

    else:
        st.markdown('</div>', unsafe_allow_html=True)

    # Information section
    with st.expander("ℹ️ How it works"):
        st.markdown("""
        **This tool extracts real employee data from Google search results:**
        
        1. **Search**: Finds companies in your specified industry and location
        2. **Scrape**: Extracts employee information from company websites
        3. **Parse**: Identifies names, emails, phones, and addresses
        4. **Filter**: Removes duplicates and validates data
        5. **Export**: Provides results in CSV, Excel, and JSON formats
        
        **Data Sources:**
        - Company websites and about pages
        - Team and leadership sections
        - Contact pages and directories
        - Publicly available business information
        """)

if __name__ == "__main__":
    main()
