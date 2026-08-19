from tools.web.browser import browser_start, browser_execute, browser_close
import time

print("Starting WA...")
dom1 = browser_start.invoke({"url": "https://web.whatsapp.com"})
print("Waiting for WA to load...")
script = "page.wait_for_timeout(15000)"
dom1 = browser_execute.invoke({"python_script": script})
print(f"Loaded DOM: {len(dom1)} chars")
with open("dom1.txt", "w") as f:
    f.write(dom1)

print("Closing browser...")
browser_close.invoke({})
print("Done.")
