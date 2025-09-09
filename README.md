# Employee Data Extractor

A Streamlit application that extracts real employee data from Google search results based on industry, job role, city, and country parameters.

## Features

- **Real-time Data Extraction**: Scrapes live data from Google search results
- **Comprehensive Search**: Finds companies based on industry and location
- **Employee Information**: Extracts names, emails, phones, and addresses
- **Multiple Export Formats**: Download results as CSV, Excel, or JSON
- **Clean Interface**: Simple and intuitive Streamlit UI
- **Duplicate Removal**: Automatically filters out duplicate entries

## Installation

1. Install Python 3.8 or higher
2. Install required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

1. Run the application:
   ```bash
   streamlit run streamlit_app.py
   ```

2. Open your browser and navigate to the provided URL (usually `http://localhost:8501`)

3. Fill in the search parameters:
   - **Industry**: e.g., Technology, Healthcare, Finance
   - **Job Role**: e.g., CTO, CEO, Manager, Director
   - **City**: e.g., Delhi, Mumbai, Bangalore
   - **Country**: e.g., India, USA, UK

4. Click "Extract Employee Data" to start the extraction

5. View results in the data table and download in your preferred format

## Data Fields Extracted

- Business Name
- Number of Employees
- Contact Person
- First Name
- Corporate Email
- Email
- Website
- Phone
- Phone Type
- Street Address
- Zip Code
- State
- City

## How It Works

1. **Company Search**: Uses Google/DuckDuckGo to find companies matching your criteria
2. **Website Scraping**: Extracts information from company websites, about pages, and team sections
3. **Data Parsing**: Uses regex patterns to identify employee names, emails, and contact information
4. **Data Validation**: Filters out noise and validates extracted information
5. **Duplicate Removal**: Ensures unique results based on company and contact person

## Legal & Ethical Considerations

- Only extracts publicly available information
- Implements rate limiting to respect website servers
- Follows ethical web scraping practices
- Complies with robots.txt guidelines
- Use responsibly and in accordance with local laws

## Technical Features

- Multi-threaded scraping for faster results
- Error handling and retry mechanisms
- Clean data validation and filtering
- Responsive Streamlit interface
- Export capabilities in multiple formats

## Requirements

- Python 3.8+
- Internet connection for web scraping
- All dependencies listed in requirements.txt

## License

This project is for educational and demonstration purposes. Please ensure compliance with all applicable laws and terms of service when using for commercial purposes.