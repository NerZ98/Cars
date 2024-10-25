from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from pymongo import MongoClient
from bson import ObjectId
import os
from dotenv import load_dotenv
import datetime
import json
from termcolor import colored
from art import text2art
import sys

# Load environment variables
load_dotenv()

class JSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        return json.JSONEncoder.default(self, obj)

class CarDatabase:
    def __init__(self):
        try:
            self.client = MongoClient('mongodb://localhost:27017/')
            self.db = self.client['cars_db']
            self.cars = self.db['cars']
        except Exception as e:
            print(f"Error connecting to MongoDB: {e}")
            raise e

    def insert_many(self, cars_data):
        try:
            for car in cars_data:
                car['timestamp'] = datetime.datetime.utcnow()
            result = self.cars.insert_many(cars_data)
            return cars_data
        except Exception as e:
            print(f"Error inserting cars: {e}")
            raise e

    def find_all(self, query_params=None):
        query = {}
        if query_params:
            if 'brand' in query_params:
                query['brand'] = {'$regex': query_params['brand'], '$options': 'i'}
            if 'year_min' in query_params:
                query['year'] = query.get('year', {})
                query['year']['$gte'] = query_params['year_min']
            if 'year_max' in query_params:
                query['year'] = query.get('year', {})
                query['year']['$lte'] = query_params['year_max']
        
        cursor = self.cars.find(query)
        return list(cursor)

    def find_one(self, car_id):
        return self.cars.find_one({'_id': ObjectId(car_id)})

class CarAPI:
    def __init__(self):
        self.db = CarDatabase()
        self.llm = ChatOpenAI(
            api_key=os.getenv('OPENAI_API_KEY'),
            model="gpt-3.5-turbo"
        )
        
        self.prompt_template = PromptTemplate(
            input_variables=["num_cars", "year_range"],
            template="""Generate {num_cars} car entries as a JSON array. Each car should follow this format exactly: {{"brand": "string", "model": "string", "year": number, "mileage": number, "cost": number}} Years between {year_range}. Use realistic brands, models, mileage, and costs. Ensure valid JSON format with no trailing commas."""
        )
        
        self.chat_prompt_template = PromptTemplate(
            input_variables=["user_query", "car_data"],
            template="""You are a car expert assistant. Analyze the available cars and the user's query.

Available cars:
{car_data}

User query: {user_query}

Respond with a JSON object in this exact format:
{{"query_interpretation": "what you understood from the query", "suggested_filters": {{"brands": [], "year_min": null, "year_max": null, "max_cost": null}}, "explanation": "why these cars match", "car_count": 0, "market_insights": {{"value_rating": "string", "price_trend": "string", "best_time_to_buy": "string", "alternative_suggestions": []}}}}"""
        )
        
        self.chain = LLMChain(llm=self.llm, prompt=self.prompt_template)
        self.chat_chain = LLMChain(llm=self.llm, prompt=self.chat_prompt_template)

    def generate_cars(self, num_cars, year_start, year_end):
        try:
            result = self.chain.invoke({
                "num_cars": num_cars,
                "year_range": f"{year_start}-{year_end}"
            })
            
            cars_data = json.loads(result['text'].strip())
            return cars_data
            
        except Exception as e:
            print(f"Error generating cars: {str(e)}")
            raise e

    def chat_query(self, user_query):
        try:
            all_cars = self.db.find_all()
            
            result = self.chat_chain.invoke({
                "user_query": user_query,
                "car_data": json.dumps(all_cars, cls=JSONEncoder)
            })
            
            cleaned_text = result['text'].strip()
            response_data = json.loads(cleaned_text)
            
            filters = response_data.get('suggested_filters', {})
            query_params = {}
            
            if filters.get('brands'):
                query_params['brand'] = '|'.join(filters['brands'])
            if filters.get('year_min'):
                query_params['year_min'] = filters['year_min']
            if filters.get('year_max'):
                query_params['year_max'] = filters['year_max']
            
            matching_cars = self.db.find_all(query_params)
            
            if matching_cars:
                costs = [car['cost'] for car in matching_cars]
                response_data['statistics'] = {
                    'average_cost': sum(costs) / len(costs),
                    'lowest_cost': min(costs),
                    'highest_cost': max(costs),
                    'total_matches': len(matching_cars)
                }
            
            response_data['matching_cars'] = matching_cars
            return response_data
            
        except Exception as e:
            print(f"Error in chat query: {str(e)}")
            raise e

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def print_header():
    clear_screen()
    print(colored(text2art("Car Expert"), "blue"))
    print(colored("Welcome to your personal car expert! Ask me anything about cars.", "cyan"))
    print(colored("Type 'exit' to quit, 'help' for command list, or 'generate' to add cars\n", "yellow"))

def print_help():
    print(colored("\nAvailable commands:", "yellow"))
    print("- help: Show this help message")
    print("- clear: Clear the screen")
    print("- exit: Exit the program")
    print("- generate: Generate and add new cars to the database")
    print("\nExample questions:")
    print("- I want a German luxury car")
    print("- Show me sports cars under 50000")
    print("- What's a good family SUV?")
    print(colored("\nJust type your question and press Enter!\n", "cyan"))

def format_car_info(car):
    return (f"\n{colored(f'{car['year']} {car['brand']} {car['model']}', 'green')}\n"
            f"  Price: ${car['cost']:,}\n"
            f"  Mileage: {car['mileage']:,} miles\n")

def generate_cars_prompt(car_api):
    try:
        print(colored("\nLet's generate some cars!", "cyan"))
        num_cars = int(input(colored("How many cars do you want to generate? > ", "yellow")))
        year_start = int(input(colored("Start year? > ", "yellow")))
        year_end = int(input(colored("End year? > ", "yellow")))
        
        print(colored("\nGenerating cars...", "yellow"))
        cars_data = car_api.generate_cars(num_cars, year_start, year_end)
        stored_cars = car_api.db.insert_many(cars_data)
        
        print(colored(f"\nSuccessfully generated {len(stored_cars)} cars:", "green"))
        for car in stored_cars[:5]:
            print(format_car_info(car))
            
        if len(stored_cars) > 5:
            print(colored(f"...and {len(stored_cars) - 5} more cars", "yellow"))
            
    except ValueError as e:
        print(colored("\nPlease enter valid numbers for cars and years!", "red"))
    except Exception as e:
        print(colored(f"\nError generating cars: {str(e)}", "red"))

def main():
    load_dotenv()
    car_api = CarAPI()
    
    try:
        print_header()
        
        while True:
            user_input = input(colored("\nWhat would you like to know about cars? > ", "cyan")).strip()
            
            if not user_input:
                continue
                
            if user_input.lower() == 'exit':
                print(colored("\nGoodbye! Happy car hunting! \n", "yellow"))
                break
                
            if user_input.lower() == 'help':
                print_help()
                continue
                
            if user_input.lower() == 'clear':
                print_header()
                continue
                
            if user_input.lower() == 'generate':
                generate_cars_prompt(car_api)
                continue
            
            print(colored("\nThinking...", "yellow"))
            
            try:
                response = car_api.chat_query(user_input)
                
                print(colored("\n Understanding: ", "blue") + response['query_interpretation'])
                print(colored("\n Analysis: ", "blue") + response['explanation'])
                
                if 'matching_cars' in response and response['matching_cars']:
                    print(colored(f"\n Found {len(response['matching_cars'])} matching cars:", "green"))
                    for car in response['matching_cars'][:5]:
                        print(format_car_info(car))
                    
                    if len(response['matching_cars']) > 5:
                        print(colored(f"...and {len(response['matching_cars']) - 5} more matches", "yellow"))
                
                # if 'market_insights' in response:
                #     insights = response['market_insights']
                #     print(colored("\n Market Insights:", "magenta"))
                #     print(f"Value Rating: {insights['value_rating']}")
                #     print(f"Price Trend: {insights['price_trend']}")
                #     print(f"Best Time to Buy: {insights['best_time_to_buy']}")
                    
                #     if 'alternative_suggestions' in insights:
                #         print(colored("\n You might also consider:", "cyan"))
                #         for suggestion in insights['alternative_suggestions']:
                #             print(f"- {suggestion}")
                
            except Exception as e:
                print(colored(f"\nOops! Something went wrong: {str(e)}", "red"))
                print(colored("Please try rephrasing your question.", "yellow"))
            
            print("\n" + colored("-" * 80, "blue"))
            
    except KeyboardInterrupt:
        print(colored("\n\nGoodbye! Happy car hunting! \n", "yellow"))
        sys.exit(0)

if __name__ == "__main__":
    main()