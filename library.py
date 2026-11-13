import hashlib
import json
import re
import sqlite3
from contextlib import contextmanager
from urllib.parse import quote, unquote, urljoin, urlsplit
from uuid import uuid4

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

from browser import DATA, is_site


@contextmanager
def db():
    DATA.mkdir(exist_ok=True)
    connection = sqlite3.connect(DATA / 'library.sqlite3')
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            connection.executescript('''
                CREATE TABLE IF NOT EXISTS requests (
                    doi TEXT PRIMARY KEY, title TEXT NOT NULL, publisher TEXT NOT NULL,
                    pdf_urls TEXT NOT NULL, points INTEGER, state TEXT NOT NULL DEFAULT 'draft',
                    post_url TEXT, file TEXT, note TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS checkins (
                    day TEXT PRIMARY KEY, state TEXT NOT NULL, note TEXT NOT NULL
                );
            ''')
            yield connection
    finally:
        connection.close()


def normalize_doi(value):
    value = re.sub(r'^(?:doi:\s*|https?://(?:dx\.)?doi\.org/)', '', value.strip(), flags=re.I)
    value = unquote(value).strip().lower()
    if not re.fullmatch(r'10\.\d{4,9}/[^\s<>"\\]+', value):
        raise ValueError('请输入有效 DOI，例如 10.1371/journal.pone.0000308。')
    return value


def lookup(value):
    doi = normalize_doi(value)
    with db() as connection:
        row = connection.execute('SELECT * FROM requests WHERE doi = ?', (doi,)).fetchone()
    if row:
        return dict(row)
    response = requests.get(f'https://api.crossref.org/works/{quote(doi, safe="/")}', timeout=20)
    if response.status_code == 404:
        raise ValueError('Crossref 未找到该 DOI。请核对 DOI 或到科研通手动填写。')
    response.raise_for_status()
    work = response.json()['message']
    title = next(iter(work.get('title', [])), '')
    title = re.sub(r'<[^>]+>', '', title).strip()
    publisher = work.get('resource', {}).get('primary', {}).get('URL', '')
    if not title or not safe_web(publisher):
        raise ValueError('缺少可核对的标题或出版商链接。')
    pdf_urls = [entry['URL'] for entry in work.get('link', [])
                if entry.get('content-type') == 'application/pdf' and safe_web(entry.get('URL', ''))]
    with db() as connection:
        connection.execute('INSERT OR IGNORE INTO requests (doi,title,publisher,pdf_urls) VALUES (?,?,?,?)',
                           (doi, title, publisher, json.dumps(pdf_urls)))
        return dict(connection.execute('SELECT * FROM requests WHERE doi=?', (doi,)).fetchone())


def safe_web(value):
    parts = urlsplit(value)
    return parts.scheme == 'https' and bool(parts.hostname) and not parts.username


def list_requests():
    with db() as connection:
        return [dict(row) for row in connection.execute('SELECT * FROM requests ORDER BY rowid DESC')]


def update(doi, state, note='', *, before, post_url=None, file=None, points=None):
    with db() as connection:
        result = connection.execute('''UPDATE requests SET state=?, note=?,
            post_url=coalesce(?,post_url), file=coalesce(?,file), points=coalesce(?,points)
            WHERE doi=? AND state=?''', (state, note, post_url, file, points, doi, before))
        return result.rowcount == 1


def attach(doi, url, before):
    url = url.strip()
    if not is_site(url) or not re.fullmatch(r'/assist/detail', urlsplit(url).path) or not re.search(
        r'(?:^|&)id=[a-zA-Z0-9]+(?:&|$)', urlsplit(url).query
    ):
        raise ValueError('请粘贴科研通求助详情页的网址。')
    if not update(doi, 'submitted', before=before, post_url=url):
        raise ValueError('需求状态已经变化，请刷新。')


def pdf_matches(path, row):
    import unicodedata

    def compact(value):
        return ''.join(c for c in unicodedata.normalize('NFKC', value).casefold() if c.isalnum())

    with path.open('rb') as source:
        if source.read(5) != b'%PDF-':
            raise ValueError('下载内容不是 PDF。')
        reader = PdfReader(source)
        text = '\n'.join(page.extract_text() or '' for page in reader.pages[:2])
        title = compact(row['title'])
        if len(title) < 10 or title not in compact(text):
            raise ValueError('未能从 PDF 前两页核对完整标题，请手动查看。')


def download_path(row):
    folder = DATA / '文献'
    folder.mkdir(exist_ok=True)
    name = re.sub(r'[^a-zA-Z0-9._-]', '_', row['doi'])[:90]
    suffix = hashlib.sha256(row['doi'].encode()).hexdigest()[:12]
    return folder / f'{name}-{suffix}.pdf'


def public_candidates(row):
    urls = dict.fromkeys(json.loads(row['pdf_urls']))
    try:
        with requests.get(row['publisher'], stream=True, timeout=(5, 8)) as response:
            if response.ok and 'text/html' in response.headers.get('Content-Type', ''):
                html = response.raw.read(350_000, decode_content=True)
                soup = BeautifulSoup(html, 'html.parser')
                for meta in soup.select('meta[name="citation_pdf_url"][content]'):
                    urls[urljoin(response.url, meta['content'])] = None
    except requests.RequestException:
        pass
    try:
        doi = quote(row['doi'], safe='/')
        response = requests.get(f'https://api.openalex.org/works/https://doi.org/{doi}',
                                params={'select': 'locations'}, timeout=(5, 8))
        if response.ok:
            for location in response.json().get('locations', []):
                if location.get('is_oa') and location.get('pdf_url'):
                    urls[location['pdf_url']] = None
    except (requests.RequestException, ValueError):
        pass
    return [url for url in urls if safe_web(url)][:5]


def try_open_copy(row):
    destination = download_path(row)
    if destination.exists():
        try:
            pdf_matches(destination, row)
            return update(row['doi'], 'downloaded', '已核对本地 PDF 标题。',
                          before=row['state'], file=str(destination))
        except Exception:
            pass
    for url in public_candidates(row):
        partial = destination.with_suffix(f'.{uuid4().hex[:12]}.part')
        try:
            with requests.get(url, stream=True, timeout=(8, 15)) as response:
                if not response.ok or not safe_web(response.url) or 'text/html' in response.headers.get('Content-Type', ''):
                    continue
                size = 0
                with partial.open('wb') as output:
                    for chunk in response.iter_content(chunk_size=65536):
                        size += len(chunk)
                        if size > 80 * 1024 * 1024:
                            raise ValueError('PDF 超过下载大小上限。')
                        output.write(chunk)
            pdf_matches(partial, row)
            partial.replace(destination)
            return update(row['doi'], 'downloaded', '已核对公开 PDF 标题。',
                          before=row['state'], file=str(destination))
        except Exception:
            continue
        finally:
            partial.unlink(missing_ok=True)
    return False
