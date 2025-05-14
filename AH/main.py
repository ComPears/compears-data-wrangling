import json
from playwright.sync_api import sync_playwright
from links_dictionary import get_ah_links



def scrape_ah_products(links, output_file):
    if isinstance(links, str):
        links = [links]  # wrap single link in list

    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        page = browser.new_page()

        all_products = []

        for url in links:
            print(f"🔄 Opening {url}...")
            page.set_viewport_size({"width": 390, "height": 844})
            page.set_extra_http_headers({
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/44.0.4919.1885 Safari/537.36"
            })
            page.goto(url, wait_until="networkidle")
            page.wait_for_timeout(3000)

            # 🍪 Accept cookies
            try:
                accept_btn = page.query_selector("button:has-text('Accepteren')")
                if accept_btn:
                    accept_btn.click()
                    print("clicked accept button")
                    page.wait_for_timeout(1000)
            except Exception as e:
                print("⚠️ Error clicking cookie button:", e)

            # 🔄 Click 'More results' until gone
            print("🔄 Loading all products...")
            print("🔄 Loading all products via 'More results' button...")



        click_count = 0
        while True:
            try:
                more_btn = page.query_selector('button[data-testhook="load-more"]')
                
                if more_btn and more_btn.is_enabled():
                    print(f"➕ Click #{click_count + 1} on 'More results'")
                    more_btn.click()
                    page.wait_for_timeout(2000)

                    # Scroll to bottom to force product load
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(1500)

                    click_count += 1
                else:
                    print("✅ 'More results' button not found or disabled.")
                    break
            except Exception as e:
                print("⚠️ Error during load-more clicking:", e)
                break

            # 🧊 Scrape and structure product info
        cards = page.query_selector_all("article[data-testhook='product-card']")
        print(f"🔍 Found {len(cards)} products.")


        for card in cards:
            raw_text = card.inner_text().strip()
            img_card = card.query_selector("img[data-testhook='product-image']")
            img_src = img_card.get_attribute("src") if img_card else None
            all_products.append({
                "raw_text": raw_text,
                "image": img_src
            })

        filename = f"new_results/{output_file}.json"

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(all_products, f, indent=2, ensure_ascii=False)

        print(f"✅ Done! {len(all_products)} products saved to {output_file}")
        browser.close()

ah_links = get_ah_links()

for name,url in ah_links.items():
    print(f"Scraping category: {name}")
    scrape_ah_products(url, name)