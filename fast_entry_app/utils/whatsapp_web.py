"""WhatsApp Web automation for sending documents.

Runs a persistent headless Firefox session against web.whatsapp.com in a
background thread. The first time it is used the user must scan the QR code
to link the browser as a WhatsApp device. After that the session stays
logged in across requests and processes restarts (profile saved on disk).

Only one browser session is supported per site. The session is owned by the
process that first calls into this module (the web process). Do not run
multiple bench web workers against the same site or the persistent profile
will be locked.
"""

import base64
import os
import queue
import tempfile
import threading

import frappe
from frappe import _

PROFILE_DIR_NAME = "whatsapp_profile"
WHATSAPP_URL = "https://web.whatsapp.com"
DEFAULT_COUNTRY_CODE = "91"

_worker = None
_worker_lock = threading.Lock()


def _get_worker():
	global _worker
	with _worker_lock:
		if _worker is None or not _worker.is_alive():
			profile_dir = frappe.get_site_path("private", PROFILE_DIR_NAME)
			os.makedirs(profile_dir, exist_ok=True)
			_worker = _WhatsAppWebWorker(profile_dir)
			_worker.start()
		return _worker


def _run(fn, timeout=300):
	worker = _get_worker()
	result = worker.submit(fn, timeout=timeout)
	if isinstance(result, Exception):
		raise result
	return result


def format_whatsapp_number(number, country_code=DEFAULT_COUNTRY_CODE):
	"""Normalise a phone number to digits with country code for wa.me/send URLs."""
	digits = "".join(ch for ch in str(number) if ch.isdigit())
	if digits.startswith("00"):
		digits = digits[2:]
	if not digits.startswith(country_code):
		digits = country_code + digits
	return digits


def is_logged_in():
	return _run(_get_worker()._is_logged_in)


def get_qr_base64():
	return _run(_get_worker()._get_qr_base64)


def send_pdf(number, pdf_path, caption, timeout=180):
	worker = _get_worker()
	return _run(lambda: worker._send_pdf(number, pdf_path, caption), timeout=timeout)


def close():
	"""Stop the worker and its browser (used on app uninstall / shutdown)."""
	with _worker_lock:
		global _worker
		if _worker is not None:
			_worker.shutdown()
			_worker = None


class _WhatsAppWebWorker(threading.Thread):
	def __init__(self, profile_dir):
		super().__init__(daemon=True)
		self.profile_dir = profile_dir
		self._q = queue.Queue()
		self._sync = None
		self._context = None
		self._page = None
		self._closed = False

	def run(self):
		while True:
			job = self._q.get()
			if job is None:
				self._cleanup()
				break
			fn, result_q = job
			try:
				result_q.put(fn())
			except Exception as e:
				result_q.put(e)
				self._recover()
			finally:
				result_q.put(_SENTINEL)

	def submit(self, fn, timeout=300):
		result_q = queue.Queue(maxsize=2)
		self._q.put((fn, result_q))
		result = result_q.get(timeout=timeout)
		result_q.get(timeout=timeout)
		return result

	def shutdown(self):
		self._q.put(None)
		self.join(timeout=10)

	def _cleanup(self):
		try:
			if self._context:
				self._context.close()
		except Exception:
			pass
		try:
			if self._sync:
				self._sync.stop()
		except Exception:
			pass
		self._context = None
		self._page = None
		self._sync = None

	def _recover(self):
		"""Close the browser after a failed job so the next one relaunches fresh."""
		try:
			if self._context:
				self._context.close()
		except Exception:
			pass
		try:
			if self._sync:
				self._sync.stop()
		except Exception:
			pass
		self._context = None
		self._page = None
		self._sync = None

	def _ensure_browser(self):
		if self._page is not None:
			try:
				self._page.url
				return self._page
			except Exception:
				pass

		# Remove stale Firefox lock files that prevent relaunching
		for lock_name in (".parentlock", "lock"):
			lock_path = os.path.join(self.profile_dir, lock_name)
			try:
				if os.path.exists(lock_path):
					os.remove(lock_path)
			except OSError:
				pass

		from playwright.sync_api import sync_playwright

		self._sync = sync_playwright().start()
		self._context = self._sync.firefox.launch_persistent_context(
			user_data_dir=self.profile_dir,
			headless=True,
		)
		self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
		self._page.set_default_timeout(60000)
		self._page.goto(WHATSAPP_URL, wait_until="domcontentloaded")
		self._page.wait_for_timeout(5000)
		return self._page

	def _is_logged_in(self):
		page = self._ensure_browser()
		for _ in range(15):
			if page.locator("#pane-side").is_visible():
				return True
			qr = page.locator('canvas[aria-label*="Scan"], [data-testid="qrcode"], div[aria-label*="Scan"]')
			if qr.count():
				return False
			page.wait_for_timeout(1000)
		return page.locator("#pane-side").is_visible()

	def _get_qr_base64(self):
		page = self._ensure_browser()
		for _ in range(30):
			if page.locator("#pane-side").is_visible():
				return None
			qr = page.locator('canvas[aria-label*="Scan"]')
			if qr.count():
				return base64.b64encode(qr.first.screenshot()).decode()
			qr = page.locator('[data-ref] canvas, [data-testid="qrcode"] canvas')
			if qr.count():
				return base64.b64encode(qr.first.screenshot()).decode()
			qr = page.locator('div[aria-label*="Scan"], div[aria-label*="scan"], div[data-testid="qrcode"]')
			if qr.count():
				return base64.b64encode(qr.first.screenshot()).decode()
			qr = page.locator('#app canvas, .landing-main canvas')
			if qr.count():
				return base64.b64encode(qr.first.screenshot()).decode()
			page.wait_for_timeout(1000)
		raise Exception(_("WhatsApp Web QR code could not be captured"))

	def _send_pdf(self, number, pdf_path, caption):
		page = self._ensure_browser()
		if not self._is_logged_in():
			raise Exception(
				_("WhatsApp Web is not logged in. Scan the QR code on the Sales Entry page first.")
			)

		# Always navigate to WhatsApp main page to ensure search is visible
		page.goto(WHATSAPP_URL, wait_until="domcontentloaded")

		# Wait for the search input with retries
		search = None
		for attempt in range(15):
			s = page.locator('input[data-tab="3"][placeholder*="Search"]')
			if s.count() > 0 and s.first.is_visible():
				search = s.first
				break
			page.wait_for_timeout(2000)
		if search is None:
			s = page.locator('input[placeholder*="Search"]')
			if s.count() > 0:
				search = s.first
		if search is None:
			ss = os.path.join(tempfile.gettempdir(), "wa_debug_no_search.png")
			page.screenshot(path=ss)
			raise Exception(_("Could not find WhatsApp search input. Screenshot: {0}").format(ss))
		# Dismiss any popover/tooltip that may intercept clicks
		try:
			page.evaluate('''() => {
				const bucket = document.getElementById("wa-popovers-bucket");
				if (bucket) bucket.style.display = "none";
				document.querySelectorAll('[role="dialog"][aria-modal="true"]').forEach(d => {
					const close = d.querySelector('[data-testid="x"], [aria-label="Close"], button');
					if (close) close.click();
					else d.style.display = "none";
				});
			}''')
		except Exception:
			pass
		page.wait_for_timeout(500)
		# Use JS click to bypass any overlays
		page.evaluate('''() => {
			const input = document.querySelector('input[data-tab="3"]');
			if (input) input.click();
		}''')
		page.wait_for_timeout(500)
		page.evaluate('''() => {
			const input = document.querySelector('input[data-tab="3"]');
			if (input) input.focus();
		}''')
		page.wait_for_timeout(300)
		page.keyboard.type(number, delay=30)
		page.wait_for_timeout(3000)

		# The search results appear in #side. Click the first non-(You) result.
		results = page.locator('#side [data-testid="cell-frame-title"]')
		if results.count() == 0:
			ss = os.path.join(tempfile.gettempdir(), "wa_debug_no_contact.png")
			page.screenshot(path=ss)
			raise Exception(
				_("Contact {0} not found in WhatsApp. Screenshot saved to {1}").format(number, ss)
			)

		# Prefer a contact that doesn't say "(You)"
		clicked = False
		for i in range(results.count()):
			try:
				txt = results.nth(i).text_content() or ""
				if "(You)" not in txt:
					# Click the parent row (the whole cell-frame div) for reliability
					page.evaluate('''(idx) => {
						const titles = document.querySelectorAll('#side [data-testid="cell-frame-title"]');
						if (titles[idx]) {
							const row = titles[idx].closest('[data-testid="cell-frame-container"]') || titles[idx].closest('[role="listitem"]') || titles[idx].parentElement;
							if (row) row.click();
							else titles[idx].click();
						}
					}''', i)
					clicked = True
					break
			except Exception:
				continue
		if not clicked:
			if results.count() > 0:
				first_txt = results.first.text_content() or ""
				if "(You)" in first_txt:
					ss = os.path.join(tempfile.gettempdir(), "wa_debug_self_number.png")
					page.screenshot(path=ss)
					raise Exception(
						_("Number {0} is your own WhatsApp number. Please use a different mobile number for this party.").format(number)
					)
			# Fallback: try clicking any clickable contact row
			page.evaluate('''() => {
				const el = document.querySelector('#side [data-testid="cell-frame-title"]');
				if (el) {
					const row = el.closest('[data-testid="cell-frame-container"]') || el.closest('[role="listitem"]') || el.parentElement;
					if (row) row.click(); else el.click();
				}
			}''')
		page.wait_for_timeout(4000)

		# Verify chat opened — check for message input area
		chat_box = page.locator('[data-testid="conversation-compose-box-input"]')
		if chat_box.count() == 0:
			chat_box = page.locator('#main [contenteditable="true"]')
		if chat_box.count() == 0:
			chat_box = page.locator('[title="Type a message"]')
		if chat_box.count() == 0:
			chat_box = page.locator('[data-testid="msg-input"]')
		if chat_box.count() == 0:
			ss = os.path.join(tempfile.gettempdir(), "wa_debug_no_chat.png")
			page.screenshot(path=ss)
			raise Exception(
				_("Chat did not open for {0}. Screenshot: {1}").format(number, ss)
			)

		# Try attach via the paperclip / plus button
		attach = page.locator('[data-testid="attach-menu-plus"]')
		if attach.count() == 0:
			attach = page.locator('button[aria-label="Attach"]')
		if attach.count() == 0:
			attach = page.locator('[title="Attach"]')
		if attach.count() == 0:
			ss = os.path.join(tempfile.gettempdir(), "wa_debug_attach.png")
			page.screenshot(path=ss)
			raise Exception(
				_("No attach button found. Screenshot saved to {0}").format(ss)
			)
		attach.first.click(timeout=15000)
		page.wait_for_timeout(2000)

		ss_menu = os.path.join(tempfile.gettempdir(), "wa_debug_after_attach.png")
		page.screenshot(path=ss_menu)

		# Click "Document" option from the attach menu using file chooser
		menu_items = page.locator('[role="menuitem"]')
		doc_clicked = False
		with page.expect_file_chooser(timeout=15000) as fc:
			for i in range(menu_items.count()):
				try:
					txt = (menu_items.nth(i).text_content() or "").strip().lower()
					if "document" in txt:
						menu_items.nth(i).click()
						doc_clicked = True
						break
				except Exception:
					continue
			if not doc_clicked:
				doc_option = page.locator('[data-testid="attach-menu-document"]')
				if doc_option.count() == 0:
					doc_option = page.locator('[data-testid="document-attach"]')
				if doc_option.count():
					doc_option.first.click(timeout=10000)
					doc_clicked = True
		if not doc_clicked:
			ss = os.path.join(tempfile.gettempdir(), "wa_debug_no_document.png")
			page.screenshot(path=ss)
			raise Exception(_("Could not click Document option. Screenshot: {0}").format(ss))
		file_chooser = fc.value
		file_chooser.set_files(pdf_path)
		page.wait_for_timeout(5000)

		ss = os.path.join(tempfile.gettempdir(), "wa_debug_before_send.png")
		page.screenshot(path=ss)

		# Wait for send button to appear
		send_btn = None
		for attempt in range(15):
			for selector in [
				'[data-testid="send"]',
				'[aria-label="Send"]',
				'[aria-label*="Send"]',
				'[data-testid="send-message"]',
				'[data-testid="wds-ic-send-filled"]',
				'span[data-testid="wds-ic-send-filled"]',
			]:
				btn = page.locator(selector)
				if btn.count() > 0 and btn.first.is_visible():
					send_btn = btn.first
					break
			if send_btn:
				break
			page.wait_for_timeout(2000)

		if send_btn is None:
			ss2 = os.path.join(tempfile.gettempdir(), "wa_debug_no_send.png")
			page.screenshot(path=ss2)
			raise Exception(_("No send button found after {0}s. Screenshot: {1}").format(30, ss2))

		# Add caption if available
		if caption:
			try:
				caption_input = page.locator('[data-testid="media-caption-input-container"] [contenteditable="true"]')
				if caption_input.count() == 0:
					caption_input = page.locator('[data-testid="media-caption-input-container"]')
				if caption_input.count():
					caption_input.first.click(force=True, timeout=5000)
					page.keyboard.type(caption, delay=10)
					page.wait_for_timeout(1000)
			except Exception:
				pass

		send_btn.click(force=True)
		page.wait_for_timeout(5000)

		ss_after = os.path.join(tempfile.gettempdir(), "wa_debug_after_send.png")
		page.screenshot(path=ss_after)

		return True


_SENTINEL = object()
