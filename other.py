import json
from playwright.sync_api import sync_playwright
import links


with sync_playwright() as p:
    browser = p.firefox.launch(headless=True)
    page = browser.new_page()

    print("🔄 Opening AH.nl...")
    page.set_viewport_size({"width": 390, "height": 844})
    page.set_extra_http_headers({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/44.0.4919.1885 Safari/537.36"
    })
    page.goto(links.ah_voordeelshop, wait_until="networkidle")  #replace the links.(the particular link in the links file)
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
    print("🔄 Loading all products via 'More results' button...") #doing this so as to capture all the possible results for that praticular category

    click_count = 0
    while True:
        try:
            more_btn = page.query_selector('button[data-testhook="load-more"]') 
            
            if more_btn and more_btn.is_enabled():
                print(f"➕ Click #{click_count + 1} on 'More results'")  #counting the number of times ive clicked the More results button
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
    products = []


    product_data = [
    {"raw_text": card.inner_text().strip()} for card in cards
]

    # 💾 Save to JSON
    with open("ah_voordeelshop.json", "w", encoding="utf-8") as f: #replace the ah blah blah to whatever you wanna save it as
        json.dump(product_data, f, indent=2, ensure_ascii=False)

    print(f"✅ Done! {len(product_data)} products saved to ah_voordeelshop.json") # same here

    browser.close()

