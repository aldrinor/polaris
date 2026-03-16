"""Check state.endTime and feed timestamps at render time."""
import os
from playwright.sync_api import sync_playwright

URL = os.environ.get("POLARIS_URL", "http://localhost:8765")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_context(viewport={"width": 1920, "height": 1080}).new_page()
    page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(10000)

    result = page.evaluate("""() => {
        var r = {};
        r.endTime = state.endTime || 0;
        r.endTimeDate = state.endTime ? new Date(state.endTime).toISOString() : "UNSET";
        r.pipelineComplete = state.pipelineComplete;
        if (typeof _wsTaskFeedItems !== "undefined") {
            r.feedSample = _wsTaskFeedItems.slice(-8).map(function(t) {
                return { label: t.label.substring(0, 50), ts: t.ts, status: t.status };
            });
        }
        var island = document.getElementById("ws-dynamic-island");
        r.islandClass = island ? island.className : "NONE";
        var islandText = document.getElementById("ws-island-text");
        r.islandText = islandText ? islandText.textContent.substring(0, 60) : "NONE";
        return r;
    }""")

    for k, v in result.items():
        if k == "feedSample":
            print("feedSample:")
            for item in v:
                print(f"  {item['status']:15s} ts={item['ts']}  {item['label']}")
        else:
            print(f"{k}: {v}")

    browser.close()
