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
        
        # Generation request interpretation prompt
        self.generation_interpreter_prompt = PromptTemplate(
            input_variables=["user_request"],
            template="""Extract car generation parameters from this request: {user_request}
            
            Return a JSON object with these fields:
            {{
                "num_cars": number of cars requested (default 10 if not specified),
                "year_start": start year,
                "year_end": end year,
                "categories": ["list of car categories mentioned"],
                "regions": ["list of regions/countries mentioned"],
                "specifications": {{
                    "drivetrain": ["mentioned drivetrains: RWD/FWD/AWD"],
                    "doors": ["mentioned door configurations: 2-door/4-door"],
                    "transmission": ["mentioned transmission types: manual/automatic"],
                    "engine_type": ["mentioned engine types: turbo/NA/hybrid"],
                    "body_style": ["mentioned body styles: coupe/sedan/hatchback"]
                }}
            }}"""
        )
        
        # Car generation prompt
        self.car_generation_prompt = PromptTemplate(
            input_variables=["params"],
            template="""Generate a JSON array of unique cars based on these parameters:
            {params}
            
            Each car should have this format:
            {{
                "brand": "string",
                "model": "string",
                "year": number,
                "mileage": number,
                "cost": number,
                "category": "string",
                "origin": "string",
                "specifications": {{
                    "drivetrain": "RWD/FWD/AWD",
                    "doors": "2-door/4-door",
                    "transmission": "manual/automatic",
                    "engine_type": "string",
                    "engine_size": "string",
                    "body_style": "string",
                    "horsepower": number
                }}
            }}

            Requirements:
            - Focus on authenticity and accuracy for the specified categories/regions
            - Include realistic trim levels and special editions when applicable
            - Ensure accurate drivetrain configurations for each model
            - Use realistic engine sizes and horsepower figures
            - Set appropriate market prices based on year, model, and condition
            - Calculate realistic mileage based on year and type
            - No duplicate model/year combinations"""
        )
        
        # Chat prompt for car queries
        self.chat_prompt_template = PromptTemplate(
            input_variables=["user_query", "car_data"],
            template="""You are a car expert assistant. Analyze the available cars and the user's query.

Available cars:
{car_data}

User query: {user_query}

Respond with a JSON object in this exact format:
{{"query_interpretation": "what you understood from the query", "suggested_filters": {{"brands": [], "year_min": null, "year_max": null, "max_cost": null}}, "explanation": "why these cars match", "car_count": 0, "market_insights": {{"value_rating": "string", "price_trend": "string", "best_time_to_buy": "string", "alternative_suggestions": []}}}}"""
        )
        
        # Create chains
        self.interpreter_chain = LLMChain(llm=self.llm, prompt=self.generation_interpreter_prompt)
        self.generator_chain = LLMChain(llm=self.llm, prompt=self.car_generation_prompt)
        self.chat_chain = LLMChain(llm=self.llm, prompt=self.chat_prompt_template)

    def generate_cars_from_request(self, request):
        try:
            # First, interpret the request
            interpretation = self.interpreter_chain.invoke({
                "user_request": request
            })
            
            params = json.loads(interpretation['text'].strip())
            
            # Generate cars based on interpreted parameters
            result = self.generator_chain.invoke({
                "params": json.dumps(params, indent=2)
            })
            
            cars_data = json.loads(result['text'].strip())
            return cars_data, params
            
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
    print(colored("You can ask me to generate cars or ask questions about existing ones.", "cyan"))
    print(colored("\nExample generation commands:", "yellow"))
    print("- generate 10 JDM sports cars from 2005-2010 with RWD and manual transmission")
    print("- create 5 German luxury sedans from 2015-2020 with AWD")
    print("- make some 90s Japanese drift cars with turbo engines")
    print(colored("\nType 'exit' to quit or 'help' for more examples", "yellow"))

def print_help():
    print(colored("\nCar Generation Examples:", "yellow"))
    print("- generate 10 JDM sports cars from 2005-2010 with RWD")
    print("- create 5 German luxury cars with AWD")
    print("- make some Japanese drift cars with turbo")
    print("- generate 8 4-door performance cars with over 400hp")
    
    print(colored("\nCar Query Examples:", "yellow"))
    print("- Show me sports cars under 50000")
    print("- What's a good family SUV?")
    print("- Find me some German luxury cars")
    
    print(colored("\nCommands:", "yellow"))
    print("- help: Show this help message")
    print("- clear: Clear the screen")
    print("- exit: Exit the program")

def format_car_info_detailed(car):
    specs = car.get('specifications', {})
    return (f"\n{colored(f'{car['year']} {car['brand']} {car['model']}', 'green')}\n"
            f"  Category: {car['category']}\n"
            f"  Origin: {car['origin']}\n"
            f"  Price: ${car['cost']:,}\n"
            f"  Mileage: {car['mileage']:,} miles\n"
            f"  Specifications:\n"
            f"    • Drivetrain: {specs.get('drivetrain', 'N/A')}\n"
            f"    • Transmission: {specs.get('transmission', 'N/A')}\n"
            f"    • Engine: {specs.get('engine_type', '')} {specs.get('engine_size', '')}\n"
            f"    • Horsepower: {specs.get('horsepower', 'N/A')} hp\n"
            f"    • Body: {specs.get('doors', '')} {specs.get('body_style', '')}\n")

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
                print(colored("\nGoodbye! Happy car hunting! 🚗\n", "yellow"))
                break
                
            if user_input.lower() == 'help':
                print_help()
                continue
                
            if user_input.lower() == 'clear':
                print_header()
                continue
            
            # Check if this is a generation request
            if any(word in user_input.lower() for word in ['generate', 'create', 'make']):
                print(colored("\nGenerating cars based on your request...", "yellow"))
                try:
                    cars_data, params = car_api.generate_cars_from_request(user_input)
                    stored_cars = car_api.db.insert_many(cars_data)
                    
                    print(colored("\nGeneration Parameters:", "blue"))
                    print(f"Years: {params['year_start']}-{params['year_end']}")
                    print(f"Categories: {', '.join(params['categories'])}")
                    print(f"Regions: {', '.join(params['regions'])}")
                    
                    print(colored(f"\nGenerated {len(stored_cars)} cars:", "green"))
                    for car in stored_cars:
                        print(format_car_info_detailed(car))
                        
                except Exception as e:
                    print(colored(f"\nError generating cars: {str(e)}", "red"))
                continue
            
            # Handle regular chat queries
            print(colored("\nThinking...", "yellow"))
            
            try:
                response = car_api.chat_query(user_input)
                
                print(colored("\n🤔 Understanding: ", "blue") + response['query_interpretation'])
                print(colored("\n📝 Analysis: ", "blue") + response['explanation'])
                
                if 'matching_cars' in response and response['matching_cars']:
                    print(colored(f"\n🚗 Found {len(response['matching_cars'])} matching cars:", "green"))
                    for car in response['matching_cars'][:5]:
                        print(format_car_info_detailed(car))
                    
                    if len(response['matching_cars']) > 5:
                        print(colored(f"...and {len(response['matching_cars']) - 5} more matches", "yellow"))
                
                if 'market_insights' in response:
                    insights = response['market_insights']
                    print(colored("\n📊 Market Insights:", "magenta"))
                    print(f"Value Rating: {insights['value_rating']}")
                    print(f"Price Trend: {insights['price_trend']}")
                    print(f"Best Time to Buy: {insights['best_time_to_buy']}")
                    
                    if 'alternative_suggestions' in insights:
                        print(colored("\n💡 You might also consider:", "cyan"))
                        for suggestion in insights['alternative_suggestions']:
                            print(f"- {suggestion}")
                
            except Exception as e:
                print(colored(f"\nOops! Something went wrong: {str(e)}", "red"))
                print(colored("Please try rephrasing your question.", "yellow"))
            
            print("\n" + colored("-" * 80, "blue"))
            
    except KeyboardInterrupt:
        print(colored("\n\nGoodbye! Happy car hunting! 🚗\n", "yellow"))
        sys.exit(0)

if __name__ == "__main__":
    main()