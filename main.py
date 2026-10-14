import os
import re
import time
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
from bs4 import BeautifulSoup

app = FastAPI(
    title="Élő Üzemanyag & Ár API",
    description="Holtankoljak.hu legfrissebb cikkeit dinamikusan elemző háttérszerver",
    version="4.0.0"
)

# CORS engedélyezése, hogy a frontend weboldal elérhesse
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class FuelPrices(BaseModel):
    benzin_95: int
    gázolaj: int
    frissitve: str
    forras: str

# Memóriában lévő élő cache kezdeti értékekkel
price_cache = {
    "benzin_95": 642,
    "gázolaj": 709,
    "utolso_lekerdezes": 0,
    "forras": "Holtankoljak.hu (Induló adat)"
}

def fetch_live_fuel_prices():
    global price_cache
    now = time.time()

    # 1 órás belső gyorsítótár (3600 másodperc)
    if now - price_cache["utolso_lekerdezes"] < 3600 and price_cache["utolso_lekerdezes"] != 0:
        return price_cache

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "hu-HU,hu;q=0.9"
    }

    try:
        # 1. Lekérjük a változások gyűjtőoldalát
        base_url = "https://holtankoljak.hu"
        list_res = requests.get(f"{base_url}/uzemanyag_arvaltozasok", headers=headers, timeout=8)
        
        if list_res.status_code == 200:
            soup = BeautifulSoup(list_res.text, 'html.parser')

            # 2. Megkeressük a legfelső, legújabb árváltozás cikk linkjét
            latest_article_link = None
            for a in soup.find_all('a', href=True):
                if 'uzemanyagar_valtozas' in a['href']:
                    latest_article_link = a['href']
                    break

            if latest_article_link:
                if not latest_article_link.startswith('http'):
                    latest_article_link = base_url + latest_article_link

                # 3. Megnyitjuk a legújabb cikket
                art_res = requests.get(latest_article_link, headers=headers, timeout=8)
                if art_res.status_code == 200:
                    art_soup = BeautifulSoup(art_res.text, 'html.parser')
                    page_text = art_soup.get_text(separator=" ")

                    benzin_match = re.search(r'95-ös\s+benzin[:\s]+(\d{3})\s*Ft', page_text, re.IGNORECASE)
                    dizel_match = re.search(r'gázolaj[:\s]+(\d{3})\s*Ft', page_text, re.IGNORECASE)

                    if benzin_match:
                        price_cache["benzin_95"] = int(benzin_match.group(1))
                    if dizel_match:
                        price_cache["gázolaj"] = int(dizel_match.group(1))

                    price_cache["utolso_lekerdezes"] = now
                    price_cache["forras"] = f"Holtankoljak: {latest_article_link}"
                    print(f"[API SIKER] Friss árak betöltve: Benzin {price_cache['benzin_95']} Ft, Dízel {price_cache['gázolaj']} Ft")
    except Exception as err:
        print(f"[API HIBA] Nem sikerült a frissítés, a legutóbbi árak maradnak: {err}")

    return price_cache

@app.get("/", summary="Státusz")
def root():
    return {"status": "Az üzemanyag API 0/24-ben aktív és automatikusan olvassa a legfrissebb híreket!"}

@app.get("/prices", response_model=FuelPrices, summary="Élő árak lekérése")
def get_prices():
    data = fetch_live_fuel_prices()
    timestamp_str = time.strftime(
        "%Y-%m-%d %H:%M:%S", 
        time.localtime(data["utolso_lekerdezes"] if data["utolso_lekerdezes"] > 0 else time.time())
    )
    return {
        "benzin_95": data["benzin_95"],
        "gázolaj": data["gázolaj"],
        "frissitve": timestamp_str,
        "forras": data["forras"]
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
