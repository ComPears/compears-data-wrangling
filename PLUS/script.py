import json
import os
import time
import re
import math
from playwright.sync_api import sync_playwright, TimeoutError
from typing import List, Optional


class PlusScraper:
    def __init__(self):
        self.unit_pattern = re.compile(
            r"\b(per\s*)?\d+\s?(g|kg|ml|l|cl|stuks?|x\s?\d+.*|st|gram)\b", re.IGNORECASE
        )
        self.price_pattern = re.compile(r"\d+[.,]?\d{2}")
        self.offer_keywords = [
            "nu voor",
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
            "1+2 GRATIS",
            "2+1 GRATIS",
            "1.00 KORTING",
            "2E 50% KORTING",
            "OP=OP",
            "2E HALVE PRIJS",
            "500 GRAM 4.99",
            "250 GRAM 2.69",
        ]

    def get_product_count(self, page) -> Optional[int]:
        try:
            # Look for text containing "producten"
            product_count_element = page.get_by_text(" productenSorteer")
            if product_count_element:
                text = product_count_element.text_content()
                # Extract number using regex
                match = re.search(r"(\d+)", text)
                if match:
                    return int(match.group(1))
        except:
            pass
        return None

    def clean_raw_text(self, file_path: str, patterns_to_remove: List[str]) -> None:
        if not os.path.exists(file_path):
            return print(f"❌ File not found: {file_path}")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            for item in data if isinstance(data, list) else []:
                if "raw_text" in item:
                    for pattern in patterns_to_remove:
                        if pattern in item["raw_text"]:
                            item["raw_text"] = item["raw_text"].replace(pattern, "")

            base, ext = os.path.splitext(file_path)
            output_file = f"{base}{ext}"

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            print(f"✅ Cleaned file saved to: {output_file}")

        except Exception as e:
            print(f"⚠️ Error processing file: {e}")

    def extract_price(self, lines: List[str]) -> str:
        joined = " ".join(lines)
        collapsed = re.sub(r"[\s\n]+", "", joined).replace(",", ".")

        matches = re.findall(r"\d+\.\d{2}", collapsed)
        if not matches:
            fallback = re.findall(r"\b\d{3}\b", collapsed)
            if fallback:
                try:
                    prices = [float(f"{p[:-2]}.{p[-2:]}") for p in fallback]
                    return f"{min(prices):.2f}"
                except ValueError:
                    return ""
        else:
            try:
                prices = [float(p) for p in matches]
                return f"{min(prices):.2f}"
            except ValueError:
                return ""
        return ""

    def extract_size(self, lines: List[str]) -> str:
        for line in lines:
            match = self.unit_pattern.search(line)
            if match:
                return match.group()
        return ""

    def clean_name(self, name: str) -> str:
        # Remove size patterns from name
        cleaned = re.sub(self.unit_pattern, "", name).strip()
        # Remove extra whitespace
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned

    def has_offer_keywords(self, text: str) -> bool:
        text_lower = text.lower()
        return any(keyword.lower() in text_lower for keyword in self.offer_keywords)

    def parse_entry(self, entry: dict) -> dict:
        raw_lines = [line.strip() for line in entry["raw_text"].split("\n") if line.strip()]

        is_offer = raw_lines and self.has_offer_keywords(raw_lines[0])

        if is_offer:
            # Find where offer lines end and product name begins
            offer_lines = []
            name_index = 0

            for i, line in enumerate(raw_lines):
                if self.has_offer_keywords(line):
                    offer_lines.append(line)
                    name_index = i + 1
                else:
                    break

            offer = " ".join(offer_lines)
            name = self.clean_name(raw_lines[name_index]) if name_index < len(raw_lines) else ""

            # Size is typically the next line after name
            size_index = name_index + 1
            size = ""
            if size_index < len(raw_lines):
                size_line = raw_lines[size_index]
                match = self.unit_pattern.search(size_line)
                if match:
                    size = match.group()
        else:
            name = self.clean_name(raw_lines[0]) if raw_lines else ""
            offer = ""
            size = self.extract_size(raw_lines)

        price = self.extract_price(raw_lines)
        image = entry.get("image", "")

        return {"n": name, "o": offer, "s": size, "p": price, "l": image}

    def scrape_plus_products(self, links: List[str], output_file: str = "plus.json") -> None:
        # Load existing data if file exists
        if os.path.exists(output_file):
            with open(output_file, "r", encoding="utf-8") as f:
                product_data = json.load(f)
            print(f"📂 Loaded {len(product_data)} existing products")
        else:
            product_data = []

        with sync_playwright() as p:
            browser = p.firefox.launch(headless=True)
            page = browser.new_page()
            page.set_viewport_size({"width": 1280, "height": 800})

            page.set_extra_http_headers(
                {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/115.0 Safari/537.36"
                }
            )

            for url in links:
                print(f"\n🌐 Scraping: {url}")
                try:
                    page.goto(url, wait_until="networkidle", timeout=60000)
                except TimeoutError:
                    print(f"⚠️ Timeout on {url}, falling back to domcontentloaded...")
                    page.goto(url, wait_until="domcontentloaded")

                print("⏳ Waiting for content to load")

                try:
                    page.get_by_role("button", name="Accepteer").click()
                    page.wait_for_url(url)
                    print("🍪 Clicked accept cookie button")
                except:
                    print("🍪 Cookie button not found or already accepted")

                try:
                    page.get_by_role("link", name="Sluit winkel keuze").click()
                    print("✖️ Closed the sidebar modal")
                except:
                    print("🔍 Sidebar not present")

                number_of_products = self.get_product_count(page)

                if number_of_products is not None:
                    click_space = math.ceil(number_of_products / 12) * 2
                else:
                    click_space = 90

                try:
                    page.locator("h1").click()
                    count = 0
                    for i in range(0, click_space):
                        page.keyboard.press("Space")
                        page.wait_for_timeout(1000)
                        page.keyboard.press("Space")

                        count += 1
                        
                        print(f"⬇️ Scrolling ... {count}/{click_space}")

                except:
                    print("📍 Stopped Scrolling")

                page.wait_for_timeout(2000)

                try:
                    cards = page.query_selector_all(".plp-item-wrapper")
                    new_data = []

                    for card in cards:
                        raw_text = card.inner_text().strip()
                        img = card.query_selector("img")
                        image_url = img.get_attribute("src") if img else None
                        new_data.append({"raw_text": raw_text, "image": image_url})

                    product_data.extend(new_data)

                    with open(output_file, "w", encoding="utf-8") as f:
                        json.dump(product_data, f, indent=2, ensure_ascii=False)

                    print(
                        f"🗂️ Scraped {len(cards)} products from {url}. Total: {len(product_data)}"
                    )

                except Exception as e:
                    print(f"❌ Error scraping {url}: {e}")
                    continue

            browser.close()
            print("🎯 Done.")

    def process_data(self, input_file: str = "plus.json", output_file: str = "structured_plus.json") -> None:
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
    from links import links  # Make sure this exists

    scraper = PlusScraper()
    
    # Step 1: Scrape the products
    scraper.scrape_plus_products(links)
    
    # Step 2: Clean raw text (optional)
    patterns_to_remove = ["Uit de keuken van"]
    scraper.clean_raw_text("plus.json", patterns_to_remove)
    
    # Step 3: Process and structure the data
    scraper.process_data()