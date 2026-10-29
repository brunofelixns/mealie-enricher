"""Synthetic OFF search service for the isolated Compose smoke test."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

PRODUCTS = {
    "weizenmehl": ("Weizenmehl", 364, 10.3, 76.3, 1.0, 0.2, 0, 2.7, 0.4, 0.002, 0),
    "mehl": ("Mehl", 364, 10.3, 76.3, 1.0, 0.2, 0, 2.7, 0.4, 0.002, 0),
    "emmentaler": ("Emmentaler", 380, 27, 0, 30, 19, 1.2, 0, 0, 0.6, 0.1),
    "eier": ("Ei", 155, 13, 1.1, 11, 3.3, 0, 0, 0.3, 0.14, 0.373),
}
FIELDS = [
    "energy-kcal_100g",
    "proteins_100g",
    "carbohydrates_100g",
    "fat_100g",
    "saturated-fat_100g",
    "trans-fat_100g",
    "fiber_100g",
    "sugars_100g",
    "sodium_100g",
    "cholesterol_100g",
]


def search_response(query: str) -> dict:
    product = PRODUCTS.get(query.lower().strip())
    hits = (
        []
        if product is None
        else [
            {
                "product_name": product[0],
                "nutriments": dict(zip(FIELDS, product[1:], strict=True)),
            }
        ]
    )
    return {"hits": hits}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        query = parse_qs(urlsplit(self.path).query).get("q", [""])[0]
        body = json.dumps(search_response(query)).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 3000), Handler).serve_forever()
