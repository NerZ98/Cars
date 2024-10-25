# Car Expert System

A comprehensive car information and recommendation system built with Python, featuring both CLI and web interfaces. The system uses OpenAI's GPT-3.5 for natural language processing and MongoDB for data storage.

## Prerequisites

```bash
# Python packages
pip install langchain-openai pymongo python-dotenv termcolor art flask

# Environment variables needed in .env file
OPENAI_API_KEY=your_openai_api_key
```

## Database Setup

The system requires MongoDB running locally on the default port (27017). Make sure MongoDB is installed and running before starting the application.

```bash
# MongoDB connection string used
mongodb://localhost:27017/
```

## Usage

### CLI Version 1 (`cars.py`)

```bash
python cars.py
```

**Available commands:**
- `help`: Show help message
- `clear`: Clear the screen
- `exit`: Exit the program
- `generate`: Generate and add new cars to database

### CLI Version 2 (`cars2.py`)

```bash
python cars2.py
```

**Generation Examples:**
- "generate 10 JDM sports cars from 2005-2010 with RWD"
- "create 5 German luxury cars with AWD"
- "make some Japanese drift cars with turbo"

### Web API (`app.py`)

```bash
python app.py
```

#### API Endpoints

1. Generate Cars
```http
POST /generate_cars
Content-Type: application/json

{
    "num_cars": 10,
    "year_start": 2010,
    "year_end": 2020
}
```

2. Get All Cars
```http
GET /cars
```

3. Get Cars with Filters
```http
GET /cars?brand=Toyota&year_min=2015&year_max=2020
```

4. Get Specific Car
```http
GET /car/<car_id>
```
