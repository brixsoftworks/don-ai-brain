from tools.web.browser import browser_start, browser_execute, browser_close

print("Starting browser...")
dom1 = browser_start.invoke({"url": "https://example.com"})
print(f"Initial DOM length: {len(dom1)}")

print("\nExecuting click on 'More information...' link")
script = """
page.locator('a').click()
"""
dom2 = browser_execute.invoke({"python_script": script})
print(f"New DOM length after click: {len(dom2)}")
print("\nClosing browser...")
browser_close.invoke({})
print("Done.")
