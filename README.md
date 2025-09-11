# Business Data Extractor

A Streamlit web application that extracts publicly available company details using the Serper.dev Google Search API and web scraping.

## Features

- **Search Companies**: Uses Serper.dev API to find companies based on industry, job role, and location
- **Data Extraction**: Scrapes company websites for contact information, emails, and phone numbers
- **Structured Output**: Displays data in a clean table format
- **Export Options**: Download results as Excel or CSV files
- **Email Validation**: Prioritizes corporate domain emails over generic ones
- **Phone Normalization**: Formats phone numbers to international standards

## Installation

1. Clone this repository
2. Create a virtual environment (recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Set up environment variables:
   ```bash
   cp .env.example .env
   ```
   Then edit `.env` file and add your Serper.dev API key.

## Usage

1. **Get API Key**: Sign up at [Serper.dev](https://serper.dev) and get your API key
2. **Configure Environment**: Add your API key to the `.env` file:
   ```
   SERPER_API_KEY=your_actual_api_key_here
   ```
3. **Run the application**:
   ```bash
   streamlit run app.py
   ```
4. Fill in the search parameters (Industry, Job Role, City, Country)
5. Click "Extract Data" to start the extraction process
6. Download the results as Excel or CSV

## Environment Variables

The application uses a `.env` file to store sensitive configuration:
- `SERPER_API_KEY`: Your Serper.dev API key

**Security Note**: Never commit your `.env` file to version control. The `.env.example` file is provided as a template.
## Data Fields Extracted

- Business Name
- Number of Employees
- Contact Person
- First Name
- Corporate Email
- Other Emails
- Website
- Phone
- Phone Type
- Street Address
- Zip Code
- State
- City

## Legal Notice

This tool only extracts publicly available information and respects robots.txt guidelines. Use responsibly and in accordance with applicable laws and website terms of service.
