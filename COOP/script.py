import json
import os
import re
from playwright.sync_api import sync_playwright, TimeoutError
from links import links


class CoopScraper:
    def __init__(self):
        # Patterns for data structuring
        self.offer_keywords = [
            "nu voor",
            "korting",
            "actie",
            "van ",
            "voor ",
            "deal",
            "2 voor",
            "3 voor",
            "aanbieding",
            "probeer prijs",
            "sale",
            "special",
            "2 + 1 GRATIS",
            "1 + 1 GRATIS",
            "2 VOOR",
            "3 VOOR",
            "4 VOOR",
            "6 VOOR",
            "aanbieding",
            "gratis",
            "3+1 GRATIS",
            "1+1 GRATIS",
            "GRATIS BEZORGING",
            "25 % KORTING",
            "15 % KORTING",
            "50 % KORTING",
            "1.00 KORTING",
            "2E 50% KORTING",
            "OP=OP",
            "2E HALVE PRIJS",
        ]
        self.unit_pattern = re.compile(
            r"\b\d+([.,]?\d+)?\s?(g|kg|ml|l|cl|stuks?|stuk\(s\)|x\s?\d+.*)\b", re.IGNORECASE
        )
        self.price_pattern = re.compile(r"\d+[.,]\d{2}")

    def scrape_coop_products(self, urls, output_file="coop.json"):
        """Scrape product data from Coop website"""
        if isinstance(urls, str):
            urls = [urls]

        # Load existing data if file exists
        if os.path.exists(output_file):
            with open(output_file, "r", encoding="utf-8") as f:
                product_data = json.load(f)
            print(f"📂 Loaded {len(product_data)} existing products")
        else:
            product_data = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_viewport_size({"width": 1280, "height": 800})

            all_products = []

            for url in urls:
                print(f"🔄 Opening {url}...")
                try:
                    page.goto(url, wait_until="networkidle", timeout=60000)
                except TimeoutError:
                    page.goto(url, wait_until="domcontentloaded")

                page.wait_for_timeout(2000)

                print("🔄 Scraping paginated results...")
                while True:
                    try:
                        cards = page.query_selector_all(".product-card")

                        for card in cards:
                            raw_text = card.inner_text().strip()
                            img = card.query_selector("img")
                            img_src = img.get_attribute("src") if img else None
                            all_products.append({"raw_text": raw_text, "image": img_src})

                        product_data.extend(all_products)

                        print(
                            f"📦 Found {len(cards)} on this page, Scraped {len(all_products)} products. Total so far: {len(product_data)}"
                        )
                        try:
                            next_btn = page.locator(
                                "custom-product-list-paging a:not(.product-list-paging__previous) button.button__svg--pagination"
                            )

                            if next_btn and next_btn.is_visible():
                                next_btn.click()
                                print("➡️ Clicked next page")
                                page.wait_for_timeout(3000)
                            else:
                                print("✅ No more pages.")
                                break

                        except Exception as e:
                            print("✅ No more pages.", e)

                    except Exception as e:
                        print(f"⚠️ Error during pagination: {e}")
                        break

                # Save to JSON
                filename = f"{output_file}"
                with open(filename, "w", encoding="utf-8") as f:
                    json.dump(product_data, f, indent=2, ensure_ascii=False)
                print(f"✅ Saved {len(product_data)} products to {filename}")

            browser.close()

    def parse_entry(self, entry):
        """Parse a single product entry into structured data"""
        raw_lines = [line.strip() for line in entry["raw_text"].split("\n") if line.strip()]

        # Find all prices in the text
        all_prices = re.findall(self.price_pattern, entry["raw_text"])

        # Initialize variables
        name = ""
        offer = ""
        regular_price = ""
        offer_price = ""

        # 1. Identify offer lines and extract offer price
        offer_lines = []
        for line in raw_lines:
            line_lower = line.lower()
            if any(keyword in line_lower for keyword in self.offer_keywords):
                offer_lines.append(line)
                # Extract offer price from this line
                line_prices = re.findall(self.price_pattern, line)
                if line_prices:
                    offer_price = line_prices[0].replace(",", ".")

        # 2. Find product name (first line that's not offer, price, or size)
        for line in raw_lines:
            line_lower = line.lower()
            is_offer_line = any(keyword in line_lower for keyword in self.offer_keywords)
            is_price_only = re.match(r"^\d+[.,]\d{2}$", line.strip())
            is_size_only = self.unit_pattern.match(line.strip()) and not any(
                char.isalpha() for char in line if char not in "gkmlxstuc()"
            )

            if (
                not is_offer_line
                and not is_price_only
                and not is_size_only
                and line.strip()
            ):
                name = line.strip()
                break

        # 3. Determine regular price
        if len(all_prices) >= 2 and offer_price:
            # If we have an offer price and multiple prices, find the regular price
            remaining_prices = [p for p in all_prices if p.replace(",", ".") != offer_price]
            if remaining_prices:
                regular_price = remaining_prices[0].replace(",", ".")
        elif len(all_prices) == 1 and not offer_price:
            # Only one price and no offer - it's the regular price
            regular_price = all_prices[0].replace(",", ".")
        elif len(all_prices) >= 1 and not offer_price:
            # Multiple prices but no clear offer - take the highest as regular price
            regular_price = f"{max([float(p.replace(',', '.')) for p in all_prices]):.2f}"

        # 4. Create offer text
        offer = " ".join(offer_lines) if offer_lines else ""

        # 5. Size: match size units like "400 g", "1 kg", "6 x 250ml", etc.
        size = ""
        for line in raw_lines:
            match = self.unit_pattern.search(line)
            if match:
                size = match.group()
                break

        # 6. Image link
        image = entry.get("image", "")
        if image == "/assets/img/not_available.svg":
            image = ""

        return {
            "n": name,
            "o": offer if offer else "",
            "p": regular_price,
            "s": size,
            "l": image,
        }

    def structure_data(self, input_file="coop.json", output_file="coop_structured.json"):
        """Process scraped data into structured format"""
        try:
            with open(input_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            structured = [self.parse_entry(entry) for entry in data]

            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(structured, f, indent=2, ensure_ascii=False)

            print(f"✅ Processed {len(data)} entries")
            print(f"✅ Output saved to '{output_file}'")

        except Exception as e:
            print(f"❌ Error: {str(e)}")


if __name__ == "__main__":
    scraper = CoopScraper()
    
    # Step 1: Scrape the products
    scraper.scrape_coop_products(links)
    
    # Step 2: Structure the scraped data
    scraper.structure_data()