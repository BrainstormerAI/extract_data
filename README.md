# Business Data Extractor

An intelligent business data extractor built with Streamlit that collects publicly available business information from various sources including company websites and business directories.

## Features

- **Smart Search**: Search for businesses by industry, job role, city, and country
- **Data Extraction**: Extract contact information, emails, phone numbers, and addresses
- **Multiple Formats**: Export data as CSV or Excel
- **Professional Interface**: Clean and intuitive Streamlit interface
- **Statistics Dashboard**: View extraction statistics and success rates

## Installation

1. Install Python 3.8 or higher
2. Install required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

1. Run the application:
   ```bash
   streamlit run app.py
   ```

2. Open your browser and navigate to the provided local URL (usually `http://localhost:8501`)

3. Fill in the search parameters:
   - Industry (e.g., Technology, Healthcare)
   - Job Role (e.g., Software Engineer, Marketing Manager)
   - City (e.g., New York, London)
   - Country (e.g., USA, UK)

4. Click "Extract Business Data" to start the search

5. View results in the data table and download as CSV or Excel

## Data Fields Extracted

- Business Name
- Number of Employees
- Contact Person
- First Name
- Corporate Email
- Other Email
- Website
- Phone
- Phone Type
- Street Address
- Zip Code
- State
- City

## Important Notes

### Legal & Ethical Considerations

- Only collect publicly available information
- Respect robots.txt and terms of service
- Implement appropriate rate limiting
- Use data responsibly and in compliance with local laws
- Consider GDPR and other privacy regulations
- Always verify information before use

### Technical Limitations

This demonstration version includes:
- Mock data for testing purposes
- Basic web scraping functionality
- Rate limiting considerations

For production use, you would need:
- Proper API integrations (Google Custom Search API, etc.)
- Enhanced error handling
- Database integration
- User authentication
- Compliance monitoring

## Architecture

```
app.py                 # Main Streamlit application
requirements.txt       # Python dependencies
README.md             # Documentation
```

## Future Enhancements

- Integration with business directory APIs
- Real-time data validation
- Advanced search filters
- Database storage
- User authentication
- Batch processing
- API rate limiting management
- Data quality scoring

## License

This project is for educational and demonstration purposes. Please ensure compliance with all applicable laws and terms of service when using for commercial purposes.