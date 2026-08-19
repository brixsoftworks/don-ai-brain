from tools.web.browser import browser_start, browser_execute, browser_close
import time

print("Starting browser...")
browser_start.invoke({"url": "https://web.whatsapp.com"})

print("Waiting for WA to load...")
script_wait = "page.wait_for_timeout(10000)"
browser_execute.invoke({"python_script": script_wait})

print("Typing search query...")
script_search = """
search_box = page.locator('input[placeholder="Search or start a new chat"]')
if search_box.count() == 0:
    search_box = page.locator('div[contenteditable="true"]').first
search_box.fill('abi')
page.wait_for_timeout(3000)
page.keyboard.press('Enter')
page.screenshot(path='wa_after_search.png')
"""
browser_execute.invoke({"python_script": script_search})

print("Typing and sending message...")
script_msg = """
page.screenshot(path='wa_before_msg.png')
page.wait_for_timeout(2000)
# The message box is usually the second contenteditable or explicitly the one at the bottom
msg_box = page.locator('div[contenteditable="true"]').last
msg_box.fill('Hello from DON! (Second attempt)')
page.keyboard.press('Enter')
page.wait_for_timeout(3000)
page.screenshot(path='wa_after_msg.png')
"""
browser_execute.invoke({"python_script": script_msg})

browser_close.invoke({})
print("Message successfully sent.")
