from flask import Flask, request, jsonify
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from pymongo import MongoClient
from bson import ObjectId
import os
from dotenv import load_dotenv
import datetime
import json

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
            # Add timestamp to each car
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

def create_app():
    app = Flask(__name__)
    car_api = CarAPI()
    
    # Use custom JSON encoder for the Flask app
    app.json_encoder = JSONEncoder

    @app.route('/generate_cars', methods=['POST'])
    def generate_cars():
        try:
            data = request.json
            print("Received data:", data)
            
            num_cars = data.get('num_cars', 10)
            year_start = data.get('year_start', 2010)
            year_end = data.get('year_end', 2020)
            
            cars_data = car_api.generate_cars(num_cars, year_start, year_end)
            stored_cars = car_api.db.insert_many(cars_data)
            
            return jsonify({
                'message': f'{len(cars_data)} cars added to database successfully',
                'cars': stored_cars
            })
        
        except Exception as e:
            print("Error:", str(e))
            print("Error type:", type(e))
            return jsonify({'error': str(e)}), 500

    @app.route('/cars', methods=['GET'])
    def get_cars():
        try:
            query_params = {}
            if request.args.get('brand'):
                query_params['brand'] = request.args.get('brand')
            if request.args.get('year_min'):
                query_params['year_min'] = int(request.args.get('year_min'))
            if request.args.get('year_max'):
                query_params['year_max'] = int(request.args.get('year_max'))
            
            cars = car_api.db.find_all(query_params)
            return jsonify(cars)
        
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/car/<car_id>', methods=['GET'])
    def get_car(car_id):
        try:
            car = car_api.db.find_one(car_id)
            
            if car:
                return jsonify(car)
            else:
                return jsonify({'error': 'Car not found'}), 404
                
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    return app

class CarAPI:
    def __init__(self):
        self.db = CarDatabase()
        self.llm = ChatOpenAI(
            api_key=os.getenv('OPENAI_API_KEY'),
            model="gpt-3.5-turbo"
        )
        
        self.prompt_template = PromptTemplate(
            input_variables=["num_cars", "year_range"],
            template="""
            Generate exactly {num_cars} car entries as a JSON array. Each car should be in this exact format with NO additional fields:
            {{"brand": "string", "model": "string", "year": number, "mileage": number, "cost": number}}
            
            Requirements:
            - Years between {year_range}
            - Use realistic car brands and models
            - Realistic mileage for car age
            - Market-appropriate costs
            - Ensure valid JSON format
            - No extra fields or comments
            - No trailing commas
            - Use double quotes for strings
            
            Example format for one car:
            {{"brand": "Toyota", "model": "Camry", "year": 2018, "mileage": 45000, "cost": 18500}}
            """
        )
        
        self.chain = LLMChain(llm=self.llm, prompt=self.prompt_template)

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

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)