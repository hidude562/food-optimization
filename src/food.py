import os
import requests
import base64
from typing import Dict, List, Optional
import time
import json
import csv

from dotenv import load_dotenv


class KrogerAPI:
    def __init__(self, client_id: str, client_secret: str, zip_code: str,
                 redirect_uri: str = "http://localhost:8000/callback",
                 use_sandbox: bool = True):
        self.client_id = client_id
        self.client_secret = client_secret
        self.zip_code = zip_code
        self.redirect_uri = redirect_uri
        self.use_sandbox = use_sandbox

        if use_sandbox:
            self.base_url = "https://api-ce.kroger.com/v1"
            print("🧪 Using SANDBOX environment")
        else:
            self.base_url = "https://api.kroger.com/v1"
            print("🌐 Using PRODUCTION environment")

        self.access_token = None
        self.nearest_store_id = None

    def get_access_token_client_credentials(self) -> str:
        """Get OAuth2 access token using client credentials"""
        token_url = f"{self.base_url}/connect/oauth2/token"

        credentials = f"{self.client_id}:{self.client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {encoded_credentials}"
        }

        data = {
            "grant_type": "client_credentials",
            "scope": "product.compact"
        }

        response = requests.post(token_url, headers=headers, data=data)
        response.raise_for_status()

        self.access_token = response.json()["access_token"]
        print(f"✓ Access token obtained")
        return self.access_token

    def get_nearest_store(self) -> Optional[Dict]:
        """Find the nearest Kroger store based on ZIP code"""
        url = f"{self.base_url}/locations"

        headers = {
            "Authorization": f"Bearer {self.access_token}"
        }

        params = {
            "filter.zipCode.near": self.zip_code,
            "filter.limit": 1
        }

        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()

        data = response.json()

        if data.get("data"):
            store = data["data"][0]
            self.nearest_store_id = store["locationId"]
            print(f"✓ Nearest store found: {store['name']} (ID: {self.nearest_store_id})")
            print(
                f"  Address: {store['address']['addressLine1']}, {store['address']['city']}, {store['address']['state']}")
            return store
        else:
            print("✗ No stores found near the provided ZIP code")
            return None

    def get_product_details(self, product_id: str) -> Dict:
        """Get detailed product information including nutrition facts"""
        url = f"{self.base_url}/products/{product_id}"

        headers = {
            "Authorization": f"Bearer {self.access_token}"
        }

        params = {
            "filter.locationId": self.nearest_store_id
        }

        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()

        return response.json()

    def search_products(self, search_term: str = None, max_results: int = 1000) -> List[Dict]:
        """Search for products"""
        url = f"{self.base_url}/products"

        headers = {
            "Authorization": f"Bearer {self.access_token}"
        }

        all_products = []
        start = 1
        limit = 50

        if search_term:
            print(f"Searching for '{search_term}'...")
        else:
            print(f"Fetching all products...")

        while len(all_products) < max_results:
            params = {
                "filter.locationId": self.nearest_store_id,
                "filter.limit": limit,
                "filter.start": start
            }

            if search_term:
                params["filter.term"] = search_term

            try:
                response = requests.get(url, headers=headers, params=params)
                response.raise_for_status()

                data = response.json()
                products = data.get("data", [])

                if not products:
                    break

                all_products.extend(products)
                print(f"  Retrieved {len(all_products)} products so far...")

                pagination = data.get("meta", {}).get("pagination", {})
                total = pagination.get("total", 0)

                if len(all_products) >= total or len(all_products) >= max_results:
                    break

                start += limit
                time.sleep(0.1)

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    print("  Rate limited, waiting 60 seconds...")
                    time.sleep(60)
                else:
                    print(f"  Error: {e}")
                    break

        all_products = all_products[:max_results]
        print(f"✓ Total products retrieved: {len(all_products)}")
        return all_products

    def get_all_food_products(self) -> List[Dict]:
        """Get all food products by searching common food categories"""

        # Comprehensive list of food search terms to cover all categories
        food_categories = [
            # Produce
            "fruits", "vegetables", "apples", "bananas", "oranges", "berries",
            "lettuce", "tomatoes", "potatoes", "onions", "carrots", "peppers",

            # Meat & Seafood
            "chicken", "beef", "pork", "turkey", "fish", "salmon", "shrimp",
            "ground beef", "steak", "bacon", "sausage", "ham",

            # Dairy & Eggs
            "milk", "cheese", "yogurt", "eggs", "butter", "cream", "ice cream",

            # Bakery
            "bread", "bagels", "muffins", "cookies", "cake", "rolls", "tortillas",

            # Pantry Staples
            "pasta", "rice", "beans", "cereal", "oats", "flour", "sugar",
            "canned", "soup", "sauce", "oil", "vinegar",

            # Frozen Foods
            "frozen pizza", "frozen vegetables", "frozen fruit", "frozen meals",
            "ice cream", "frozen chicken", "frozen fish",

            # Snacks
            "chips", "crackers", "nuts", "popcorn", "pretzels", "granola bars",

            # Beverages
            "juice", "soda", "water", "coffee", "tea", "sports drinks",

            # Condiments & Sauces
            "ketchup", "mustard", "mayonnaise", "salad dressing", "hot sauce",

            # International
            "mexican", "italian", "asian", "indian",

            # Specialty
            "organic", "gluten free", "vegan", "vegetarian",
        ]

        all_products = []
        seen_product_ids = set()

        print(f"\n{'=' * 80}")
        print(f"FETCHING ALL FOOD PRODUCTS FROM {len(food_categories)} CATEGORIES")
        print(f"{'=' * 80}\n")

        for i, category in enumerate(food_categories, 1):
            print(f"\n[{i}/{len(food_categories)}] Category: {category}")
            print(f"{'─' * 80}")

            try:
                products = self.search_products(search_term=category, max_results=200)

                # Deduplicate products
                new_products = 0
                for product in products:
                    product_id = product.get("productId")
                    if product_id and product_id not in seen_product_ids:
                        seen_product_ids.add(product_id)
                        all_products.append(product)
                        new_products += 1

                print(f"  ✓ Added {new_products} new unique products")
                print(f"  Total unique products so far: {len(all_products)}")

                # Small delay between categories
                time.sleep(0.1
                           )

            except Exception as e:
                print(f"  ⚠️  Error fetching category '{category}': {e}")
                continue

        print(f"\n{'=' * 80}")
        print(f"✅ COMPLETED: Found {len(all_products)} unique food products")
        print(f"{'=' * 80}\n")

        return all_products

    def extract_nutrition_data(self, product_detail: Dict) -> Optional[Dict]:
        """Extract nutrition data from product detail"""
        data = product_detail.get("data", {})

        product_id = data.get("productId", "")
        description = data.get("description", "")
        brand = data.get("brand", "")

        # Price and size
        items = data.get("items", [])
        price = items[0]["price"]["regular"] if items and items[0].get("price") else None
        size = items[0].get("size", "") if items else ""

        # Categories
        categories = ", ".join(data.get("categories", []))

        # Nutrition
        nutrition_info = data.get("nutritionInformation", [])
        if not nutrition_info:
            return None

        nutrition = nutrition_info[0]

        serving = nutrition.get("servingSize", {})
        serving_size = f"{serving.get('quantity', '')} {serving.get('unitOfMeasure', {}).get('name', '')}"
        servings_per_pkg = nutrition.get("servingsPerPackage", {}).get("value", "")
        rating = nutrition.get("nutritionalRating", "")

        # Extract specific nutrients
        nutrients_dict = {n.get("displayName"): n for n in nutrition.get("nutrients", [])}

        def get_nutrient_value(name):
            n = nutrients_dict.get(name, {})
            return n.get("quantity", "")

        def get_nutrient_daily(name):
            n = nutrients_dict.get(name, {})
            return n.get("percentDailyIntake", "")

        # Ingredients
        ingredients = nutrition.get("ingredientStatement", "")

        # Allergens
        allergens = data.get("allergens", [])
        allergen_str = "; ".join([f"{a.get('levelOfContainmentName', '')}: {a.get('name', '')}" for a in allergens])

        return {
            "product_id": product_id,
            "description": description,
            "brand": brand,
            "size": size,
            "price": price,
            "categories": categories,
            "serving_size": serving_size,
            "servings_per_package": servings_per_pkg,
            "calories": get_nutrient_value("Calories"),
            "calories_from_fat": get_nutrient_value("Calories from Fat"),
            "total_fat_g": get_nutrient_value("Total Fat"),
            "total_fat_dv": get_nutrient_daily("Total Fat"),
            "saturated_fat_g": get_nutrient_value("Saturated Fat"),
            "saturated_fat_dv": get_nutrient_daily("Saturated Fat"),
            "trans_fat_g": get_nutrient_value("Trans Fat"),
            "cholesterol_mg": get_nutrient_value("Cholesterol"),
            "cholesterol_dv": get_nutrient_daily("Cholesterol"),
            "sodium_mg": get_nutrient_value("Sodium"),
            "sodium_dv": get_nutrient_daily("Sodium"),
            "total_carb_g": get_nutrient_value("Total Carbohydrate"),
            "total_carb_dv": get_nutrient_daily("Total Carbohydrate"),
            "dietary_fiber_g": get_nutrient_value("Dietary Fiber"),
            "dietary_fiber_dv": get_nutrient_daily("Dietary Fiber"),
            "sugars_g": get_nutrient_value("Sugars"),
            "protein_g": get_nutrient_value("Protein"),
            "protein_dv": get_nutrient_daily("Protein"),
            "vitamin_a_dv": get_nutrient_daily("Vitamin A"),
            "vitamin_c_dv": get_nutrient_daily("Vitamin C"),
            "vitamin_d_dv": get_nutrient_daily("Vitamin D"),
            "calcium_dv": get_nutrient_daily("Calcium"),
            "iron_dv": get_nutrient_daily("Iron"),
            "potassium_mg": get_nutrient_value("Potassium"),
            "potassium_dv": get_nutrient_daily("Potassium"),
            "nutritional_rating": rating,
            "ingredients": ingredients[:500] if ingredients else "",  # Truncate long ingredients
            "allergens": allergen_str,
        }

    def create_master_nutrition_csv(self, nutrition_data_list: List[Dict], filename: str = "kroger_all_nutrition.csv"):
        """Create a comprehensive CSV with all nutrition data"""

        if not nutrition_data_list:
            print("No nutrition data to save!")
            return

        # Get all unique keys
        all_keys = set()
        for item in nutrition_data_list:
            all_keys.update(item.keys())

        fieldnames = sorted(all_keys)

        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(nutrition_data_list)

        print(f"\n✅ Master nutrition CSV saved to {filename}")
        print(f"   Total products: {len(nutrition_data_list)}")
        print(f"   Columns: {len(fieldnames)}")


def main():
    client_id = os.getenv("KROGER_CLIENT_ID")
    client_secret = os.getenv("KROGER_CLIENT_SECRET")
    zip_code = os.getenv("KROGER_USER_ZIP_CODE")

    if not all([client_id, client_secret, zip_code]):
        print("Error: Please set environment variables")
        return

    kroger = KrogerAPI(client_id, client_secret, zip_code, use_sandbox=True)

    try:
        # Authenticate
        kroger.get_access_token_client_credentials()

        # Find nearest store
        store = kroger.get_nearest_store()
        if not store:
            return

        # Get all food products
        print("\n" + "=" * 80)
        print("STEP 1: COLLECTING ALL FOOD PRODUCTS")
        print("=" * 80)

        all_products = kroger.get_all_food_products()

        if not all_products:
            print("No products found!")
            return

        # Save basic product list
        with open("kroger_all_products.json", "w") as f:
            json.dump(all_products, f, indent=2)
        print(f"✓ Basic product list saved to kroger_all_products.json")

        # Get detailed nutrition for each product
        print("\n" + "=" * 80)
        print(f"STEP 2: FETCHING DETAILED NUTRITION FOR {len(all_products)} PRODUCTS")
        print("=" * 80)
        print("⚠️  This may take a while...")

        nutrition_data_list = []
        failed_products = []

        for i, product in enumerate(all_products, 1):
            product_id = product.get("productId")
            description = product.get("description", "Unknown")

            if not product_id:
                continue

            # Progress indicator
            if i % 10 == 0:
                print(f"\n[{i}/{len(all_products)}] Progress: {(i / len(all_products) * 100):.1f}%")
                print(f"  Successfully fetched: {len(nutrition_data_list)}")
                print(f"  Failed: {len(failed_products)}")

            try:
                product_detail = kroger.get_product_details(product_id)
                nutrition_data = kroger.extract_nutrition_data(product_detail)

                if nutrition_data:
                    nutrition_data_list.append(nutrition_data)
                    if i % 10 == 1:  # Show sample
                        print(f"  ✓ {description[:60]}")
                else:
                    failed_products.append({
                        "id": product_id,
                        "description": description,
                        "reason": "No nutrition info"
                    })

                # Rate limiting - be nice to the API
                time.sleep(0.1)

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    print(f"\n  ⚠️  Rate limited! Waiting 30 seconds...")
                    time.sleep(30)
                    # Retry this product
                    try:
                        product_detail = kroger.get_product_details(product_id)
                        nutrition_data = kroger.extract_nutrition_data(product_detail)
                        if nutrition_data:
                            nutrition_data_list.append(nutrition_data)
                    except:
                        failed_products.append({
                            "id": product_id,
                            "description": description,
                            "reason": str(e)
                        })
                else:
                    failed_products.append({
                        "id": product_id,
                        "description": description,
                        "reason": str(e)
                    })
            except Exception as e:
                failed_products.append({
                    "id": product_id,
                    "description": description,
                    "reason": str(e)
                })

        # Save results
        print("\n" + "=" * 80)
        print("SAVING RESULTS")
        print("=" * 80)

        kroger.create_master_nutrition_csv(nutrition_data_list)

        # Save failed products log
        if failed_products:
            with open("kroger_failed_products.json", "w") as f:
                json.dump(failed_products, f, indent=2)
            print(f"⚠️  Failed products log saved to kroger_failed_products.json")

        # Summary
        print("\n" + "=" * 80)
        print("FINAL SUMMARY")
        print("=" * 80)
        print(f"Total products found: {len(all_products)}")
        print(f"Successfully fetched nutrition: {len(nutrition_data_list)}")
        print(f"Failed to fetch: {len(failed_products)}")
        print(f"Success rate: {(len(nutrition_data_list) / len(all_products) * 100):.1f}%")

    except requests.exceptions.HTTPError as e:
        print(f"HTTP Error: {e}")
        print(f"Response: {e.response.text}")
    except KeyboardInterrupt:
        print("\n\n⚠️  Process interrupted by user!")
        print("Saving partial results...")
        if 'nutrition_data_list' in locals() and nutrition_data_list:
            kroger.create_master_nutrition_csv(nutrition_data_list, "kroger_partial_nutrition.csv")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

load_dotenv()
if __name__ == "__main__":
    main()