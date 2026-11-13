import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

import msvcrt

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
SITE = 'https://www.ablesci.com'
from playwright.sync_api import Error as BrowserError, sync_playwright


class NeedsLogin(RuntimeError):
    pass


@contextmanager
def browser(headless=True):
    DATA.mkdir(exist_ok=True)
    with (DATA / 'browser.lock').open('a+b') as lock:
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise RuntimeError('科研通专用浏览器正在使用，请关闭后重试。') from exc
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                DATA / 'browser', channel='chrome', headless=headless,
                accept_downloads=True, locale='zh-CN',
            )
            context.set_default_timeout(8000)
            try:
                yield context
            finally:
                context.close()


def is_site(url):
    parsed = urlsplit(url)
    return parsed.scheme == 'https' and parsed.netloc == 'www.ablesci.com'


def visit(page, path):
    page.goto(SITE + path, wait_until='domcontentloaded', timeout=30000)
    if not is_site(page.url) or urlsplit(page.url).path.startswith('/site/login'):
        raise NeedsLogin('请打开工具，点击“登录科研通”，在浏览器完成验证。')


def login():
    with browser(headless=False) as context:
        page = context.pages[0]
        page.goto(SITE + '/my/assist-my', wait_until='domcontentloaded', timeout=30000)
        deadline = time.monotonic() + 600
        next_probe = time.monotonic() + 12
        while time.monotonic() < deadline and not page.is_closed():
            if is_site(page.url) and urlsplit(page.url).path.rstrip('/') == '/my/assist-my':
                return
            if time.monotonic() >= next_probe:
                next_probe = time.monotonic() + 12
                try:
                    response = context.request.get(SITE + '/my/assist-my', timeout=8000)
                    if response.ok and is_site(response.url) and urlsplit(response.url).path.rstrip('/') == '/my/assist-my':
                        return
                except BrowserError:
                    if page.is_closed():
                        break
            page.wait_for_timeout(600)
        raise NeedsLogin('未确认登录成功。请再次打开登录窗口。')


if __name__ == '__main__':
    login()
    print('科研通已登录')
