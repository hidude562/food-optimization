import os
import requests
import base64
from typing import Dict, List, Optional
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import webbrowser

from dotenv import load_dotenv


class CallbackHandler(BaseHTTPRequestHandler):
    auth_code = None

    def do_GET(self):
        query_components = parse_qs(urlparse(self.path).query)

        if 'code' in query_components:
            CallbackHandler.auth_code = query_components['code'][0]
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(
                b'<html><body><h1>Authorization successful!</h1><p>You can close this window.</p></body></html>')
        else:
            self.send_response(400)
            self.end_headers()

    def log_message(self, format, *args):
        pass


class KrogerAPI:
    def __init__(self, client_id: str, client_secret: str, zip_code: str,
                 redirect_uri: str = "http://localhost:8000/callback",
                 use_sandbox: bool = True):
        self.client_id = client_id
        self.client_secret = client_secret
        self.zip_code = zip_code
        self.redirect_uri = redirect_uri
        self.use_sandbox = use_sandbox

        # Set base URL based on environment
        if use_sandbox:
            self.base_url = "https://api-ce.kroger.com/v1"
            print("🧪 Using SANDBOX environment")
        else:
            self.base_url = "https://api.kroger.com/v1"
            print("🌐 Using PRODUCTION environment")

        self.access_token = None
        self.nearest_store_id = None

    def get_access_token_client_credentials(self) -> str:
        """Get OAuth2 access token using client credentials (no user auth needed)"""
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

    def get_authorization_code(self) -> str:
        """Start OAuth2 authorization code flow (for user-specific data)"""
        auth_url = f"{self.base_url}/connect/oauth2/authorize"

        params = {
            "scope": "product.compact",
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri
        }

        param_string = "&".join([f"{k}={v}" for k, v in params.items()])
        full_url = f"{auth_url}?{param_string}"

        print(f"Opening browser for authorization...")
        print(f"If browser doesn't open, visit: {full_url}")

        server = HTTPServer(('localhost', 8000), CallbackHandler)
        webbrowser.open(full_url)

        print("Waiting for authorization...")
        while CallbackHandler.auth_code is None:
            server.handle_request()

        return CallbackHandler.auth_code

    def get_access_token_with_auth_code(self, auth_code: str) -> str:
        """Exchange authorization code for access token"""
        token_url = f"{self.base_url}/connect/oauth2/token"

        credentials = f"{self.client_id}:{self.client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {encoded_credentials}"
        }

        data = {
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": self.redirect_uri
        }

        response = requests.post(token_url, headers=headers, data=data)
        response.raise_for_status()

        self.access_token = response.json()["access_token"]
        print(f"✓ Access token obtained")
        return self.access_token

    def authenticate_with_user(self):
        """Complete authentication flow with user authorization"""
        auth_code = self.get_authorization_code()
        self.get_access_token_with_auth_code(auth_code)

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

    def get_products(self, limit: int = 50, start: int = 1, term: str = None) -> Dict:
        """Get products from the nearest store"""
        url = f"{self.base_url}/products"

        headers = {
            "Authorization": f"Bearer {self.access_token}"
        }

        params = {
            "filter.limit": limit,
            "filter.start": start
        }

        # Add location filter if we have a store
        if self.nearest_store_id:
            params["filter.locationId"] = self.nearest_store_id

        # Add search term if provided
        if term:
            params["filter.term"] = term

        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()

        return response.json()

    def search_products(self, search_term: str, max_results: int = 100) -> List[Dict]:
        """Search for specific products"""
        all_products = []
        start = 1
        limit = 50

        print(f"\nSearching for '{search_term}'...")

        while len(all_products) < max_results:
            try:
                data = self.get_products(limit=limit, start=start, term=search_term)
                products = data.get("data", [])

                if not products:
                    break

                all_products.extend(products)
                print(f"  Found {len(all_products)} products so far...")

                pagination = data.get("meta", {}).get("pagination", {})
                total = pagination.get("total", 0)

                if len(all_products) >= total or len(all_products) >= max_results:
                    break

                start += limit
                time.sleep(0.5)

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    print("  Rate limited, waiting 60 seconds...")
                    time.sleep(60)
                else:
                    raise

        all_products = all_products[:max_results]
        print(f"✓ Total products retrieved: {len(all_products)}")
        return all_products

    def get_all_products(self, max_products: Optional[int] = None) -> List[Dict]:
        """Fetch all products (Note: This might not work well without search term)"""
        all_products = []
        start = 1
        limit = 50

        print(f"\nFetching products...")

        while True:
            try:
                data = self.get_products(limit=limit, start=start)
                products = data.get("data", [])

                if not products:
                    break

                all_products.extend(products)
                print(f"  Retrieved {len(all_products)} products so far...")

                pagination = data.get("meta", {}).get("pagination", {})
                total = pagination.get("total", 0)

                if max_products and len(all_products) >= max_products:
                    all_products = all_products[:max_products]
                    break

                if total > 0 and len(all_products) >= total:
                    break

                start += limit
                time.sleep(0.5)

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    print("  Rate limited, waiting 60 seconds...")
                    time.sleep(60)
                else:
                    raise

        print(f"✓ Total products retrieved: {len(all_products)}")
        return all_products

    def display_products(self, products: List[Dict], max_display: int = 20):
        """Display product information"""
        print(f"\n{'=' * 80}")
        print(f"PRODUCTS (showing first {min(len(products), max_display)} of {len(products)})")
        print(f"{'=' * 80}\n")

        for i, product in enumerate(products[:max_display], 1):
            print(f"{i}. {product.get('description', 'N/A')}")
            print(f"   Brand: {product.get('brand', 'N/A')}")
            print(f"   Product ID: {product.get('productId', 'N/A')}")

            items = product.get('items', [])
            if items and items[0].get('price'):
                price = items[0]['price']
                regular = price.get('regular', 'N/A')
                promo = price.get('promo', 0)

                if promo > 0:
                    print(f"   Price: ${regular} (Sale: ${promo})")
                else:
                    print(f"   Price: ${regular}")

            if items and items[0].get('size'):
                print(f"   Size: {items[0]['size']}")

            categories = product.get('categories', [])
            if categories:
                print(f"   Categories: {', '.join(categories[:3])}")

            print()

    def save_products_to_file(self, products: List[Dict], filename: str = "kroger_products.txt"):
        """Save all products to a text file"""
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"Total Products: {len(products)}\n")
            f.write(f"{'=' * 80}\n\n")

            for i, product in enumerate(products, 1):
                f.write(f"{i}. {product.get('description', 'N/A')}\n")
                f.write(f"   Product ID: {product.get('productId', 'N/A')}\n")
                f.write(f"   Brand: {product.get('brand', 'N/A')}\n")

                items = product.get('items', [])
                if items:
                    item = items[0]
                    if item.get('price'):
                        price = item['price']
                        f.write(f"   Regular Price: ${price.get('regular', 'N/A')}\n")
                        if price.get('promo', 0) > 0:
                            f.write(f"   Promo Price: ${price['promo']}\n")

                    if item.get('size'):
                        f.write(f"   Size: {item['size']}\n")

                    if item.get('upc'):
                        f.write(f"   UPC: {item['upc']}\n")

                categories = product.get('categories', [])
                if categories:
                    f.write(f"   Categories: {', '.join(categories)}\n")

                f.write("\n")

        print(f"✓ Products saved to {filename}")


def main():
    client_id = os.getenv("KROGER_CLIENT_ID")
    client_secret = os.getenv("KROGER_CLIENT_SECRET")
    zip_code = os.getenv("KROGER_USER_ZIP_CODE")

    if not all([client_id, client_secret, zip_code]):
        print(
            "Error: Please set KROGER_CLIENT_ID, KROGER_CLIENT_SECRET, and KROGER_USER_ZIP_CODE environment variables")
        return

    # Use sandbox=True since your credentials work in sandbox
    kroger = KrogerAPI(client_id, client_secret, zip_code, use_sandbox=True)

    try:
        # Use client credentials (no user login required for product data)
        kroger.get_access_token_client_credentials()

        # Find nearest store
        store = kroger.get_nearest_store()

        if store:
            # Option 1: Search for specific categories
            print("\n" + "=" * 80)
            print("OPTION 1: Search for specific products")
            print("=" * 80)

            search_terms = ["chicken", "milk", "bread", "eggs", "bananas"]
            all_products = []

            for term in search_terms:
                products = kroger.search_products(term, max_results=50)
                all_products.extend(products)

            kroger.display_products(all_products, max_display=20)
            kroger.save_products_to_file(all_products, "kroger_search_products.txt")

        # Option 2: Try to get all products (may be limited in sandbox)
        print("\n" + "=" * 80)
        print("OPTION 2: Get all available products")
        print("=" * 80)
        products = kroger.get_all_products(max_products=200)

        if products:
            kroger.display_products(products, max_display=20)
            kroger.save_products_to_file(products, "kroger_all_products.txt")

    except requests.exceptions.HTTPError as e:
        print(f"HTTP Error: {e}")
        print(f"Response: {e.response.text}")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

load_dotenv()

if __name__ == "__main__":
    main()