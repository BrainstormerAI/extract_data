# API Setup Guide for Enhanced Employee Data Extractor

## Required API Keys

### 1. Serper.dev API (Required)
- **Purpose**: Google search results for company discovery
- **Free Tier**: 2,500 searches/month
- **Setup**: 
  1. Go to https://serper.dev
  2. Sign up for free account
  3. Get API key from dashboard
  4. Add to `.env` file as `SERPER_API_KEY`

### 2. Hunter.io API (Recommended)
- **Purpose**: Extract professional emails from company domains
- **Free Tier**: 25 requests/month
- **Setup**:
  1. Go to https://hunter.io
  2. Create free account
  3. Get API key from dashboard
  4. Add to `.env` file as `HUNTER_API_KEY`

### 3. People Data Labs API (Recommended)
- **Purpose**: Search employee database for specific roles
- **Free Tier**: 1,000 requests/month
- **Setup**:
  1. Go to https://peopledatalabs.com
  2. Sign up for free account
  3. Get API key from dashboard
  4. Add to `.env` file as `PDL_API_KEY`

### 4. NumVerify API (Optional)
- **Purpose**: Validate and format phone numbers
- **Free Tier**: 1,000 requests/month
- **Setup**:
  1. Go to https://numverify.com
  2. Create free account
  3. Get API key from dashboard
  4. Add to `.env` file as `NUMVERIFY_API_KEY`

### 5. ScraperAPI (Optional)
- **Purpose**: Enhanced website scraping with proxy rotation
- **Free Tier**: 1,000 requests/month
- **Setup**:
  1. Go to https://scraperapi.com
  2. Sign up for free account
  3. Get API key from dashboard
  4. Add to `.env` file as `SCRAPER_API_KEY`

## API Priority

### Essential (Must Have)
- **Serper.dev**: Core functionality for company search

### Highly Recommended
- **Hunter.io**: Professional email extraction
- **People Data Labs**: Employee database search

### Optional (Enhances Quality)
- **NumVerify**: Phone number validation
- **ScraperAPI**: Better scraping success rate

## Cost Breakdown (Free Tiers)

| API | Free Requests/Month | Purpose |
|-----|-------------------|---------|
| Serper.dev | 2,500 | Company search |
| Hunter.io | 25 | Email extraction |
| People Data Labs | 1,000 | Employee search |
| NumVerify | 1,000 | Phone validation |
| ScraperAPI | 1,000 | Website scraping |

## Usage Optimization

### To maximize free tier usage:
1. Start with essential APIs (Serper.dev + Hunter.io)
2. Add People Data Labs for better employee targeting
3. Use NumVerify for phone validation
4. Add ScraperAPI if direct scraping fails

### Request Management:
- The app automatically handles rate limiting
- Failed API calls fallback to alternative methods
- Duplicate removal reduces unnecessary API calls

## Setup Instructions

1. Copy `.env.example` to `.env`
2. Fill in your API keys
3. Start with Serper.dev API key (minimum requirement)
4. Add other APIs gradually to improve data quality
5. Run the application: `streamlit run app.py`

## Troubleshooting

### Common Issues:
- **No results**: Check Serper.dev API key
- **Limited emails**: Add Hunter.io API key
- **No employee names**: Add People Data Labs API key
- **Scraping failures**: Add ScraperAPI key
- **Invalid phones**: Add NumVerify API key

### Error Messages:
- "Please provide Serper.dev API key": Add SERPER_API_KEY to .env
- "Hunter.io API error": Check HUNTER_API_KEY validity
- "People Data Labs API error": Verify PDL_API_KEY
- "NumVerify API error": Check NUMVERIFY_API_KEY
- "ScraperAPI error": Verify SCRAPER_API_KEY

## Data Quality Expectations

### With All APIs:
- 80-90% success rate for employee data
- Verified emails and phone numbers
- Comprehensive company information
- High-quality contact details

### With Essential APIs Only:
- 60-70% success rate
- Basic company and contact information
- Some email addresses
- Limited phone number validation

## Legal Compliance

All APIs used comply with:
- Data protection regulations
- Terms of service of respective platforms
- Ethical data extraction practices
- Rate limiting and fair usage policies

**Note**: Always review and comply with each API's terms of service and your local data protection laws.