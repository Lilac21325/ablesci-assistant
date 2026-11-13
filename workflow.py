import re
from datetime import datetime
from urllib.parse import urljoin, urlsplit

from browser import NeedsLogin, SITE, browser, is_site, visit
from library import attach, db, download_path, list_requests, pdf_matches, try_open_copy, update
from playwright.sync_api import TimeoutError as BrowserTimeout

SIGN = re.compile(r'^\s*今日打卡签到\s*$')
SIGNED = re.compile(r'^\s*(?:今日已签到|今日已打卡(?:签到)?|已完成今日签到|已签到|签到成功)[！!。]?\s*$')
REQUEST = '/my/assist-my'


def visible(locator):
    return [item for item in locator.all() if item.is_visible()]


def one(locator):
    matches = visible(locator)
    return matches[0] if len(matches) == 1 else None


def clock():
    return datetime.now().astimezone()


def sign_status():
    with db() as connection:
        row = connection.execute('SELECT * FROM checkins WHERE day=?', (clock().date().isoformat(),)).fetchone()
    return row['note'] if row else '今日签到尚未运行。'


def has_checkin_record(page, day):
    visit(page, '/my/point')
    for row in page.locator('tr').filter(has_text=re.compile('签到|打卡')).all():
        cells = row.locator('td').all_inner_texts()
        if len(cells) >= 3 and cells[0].strip().split(' ', 1)[0] == day and cells[-1].strip() == '签到':
            return True
    return False


def signin(page, day):
    with db() as connection:
        row = connection.execute('SELECT state FROM checkins WHERE day=?', (day,)).fetchone()
    if row and row['state'] == 'ok':
        return
    state = 'error'
    try:
        visit(page, REQUEST)
        visit(page, '/')
        panel = page.locator('.fly-signin')
        if not visible(panel.get_by_text(SIGNED)):
            button = one(panel.get_by_text(SIGN))
            if button is not None:
                button.click()
                try:
                    panel.get_by_text(SIGNED).first.wait_for(state='visible', timeout=3500)
                except BrowserTimeout:
                    if not has_checkin_record(page, day):
                        raise
            elif not has_checkin_record(page, day):
                raise RuntimeError('官网未显示签到按钮，今日积分记录也未找到签到。请在官网查看。')
        state, note = 'ok', '官网确认今日已签到。'
    except NeedsLogin as exc:
        state, note = 'login', str(exc)
    except BrowserTimeout:
        note = '官网未显示签到成功。请查看首页签到状态。'
    except RuntimeError as exc:
        note = str(exc)
    with db() as connection:
        connection.execute('INSERT OR REPLACE INTO checkins VALUES (?,?,?)', (day, state, note))
    if state == 'login':
        raise NeedsLogin(note)


def detail_links(page, title):
    return {
        urljoin(SITE, link.get_attribute('href') or '')
        for link in page.locator('a[href*="/assist/detail"]').all()
        if link.is_visible() and ' '.join(link.inner_text().split()) == ' '.join(title.split())
    }


def published_link(page, row):
    visit(page, REQUEST)
    matches = detail_links(page, row['title'])
    if len(matches) > 1:
        raise RuntimeError('“我的求助”出现多条同名记录，请手动绑定正确的详情链接。')
    return next(iter(matches), None)


def submit(page, row):
    existing = published_link(page, row)
    if existing:
        attach(row['doi'], existing, row['state'])
        return
    visit(page, '/assist/create')
    form = page.locator('#assist-create-form')
    doi = one(form.locator('#onekey'))
    query = one(form.get_by_role('button', name='智能提取文献信息', exact=True))
    if doi is None or query is None:
        raise RuntimeError('官网求助表单与工具预期不同。请用“打开官网求助页”手动发布。')
    doi.fill(row['doi'])
    query.click()
    title = form.locator('#Assist-title')
    title.first.wait_for(state='visible')
    expected = ' '.join(row['title'].split()).casefold()
    for _ in range(20):
        if ' '.join(title.first.input_value().split()).casefold() == expected:
            break
        page.wait_for_timeout(300)
    else:
        raise RuntimeError('官网识别的文献标题与已授权的标题不同。请手动核对。')
    identified_doi = one(form.locator('#Assist-doi'))
    if identified_doi is None or identified_doi.input_value().strip().casefold() != row['doi'].casefold():
        raise RuntimeError('官网提取的 DOI 与已授权的 DOI 不一致。请手动核对。')
    publisher = one(form.locator('#Assist-url'))
    points = one(form.locator('#Assist-point'))
    button = one(form.get_by_role('button', name='立即发布', exact=True))
    if publisher is None or points is None or button is None:
        raise RuntimeError('无法确认官网的文献链接、悬赏积分和发布按钮。请手动发布。')
    publisher.fill(row['publisher'])
    points.fill(str(row['points']))
    if points.input_value() != str(row['points']):
        raise RuntimeError('悬赏积分与授权金额不一致。')
    if not update(row['doi'], 'submitting', '已尝试提交，正在核对我的求助。', before='queued'):
        return
    button.click()
    page.wait_for_timeout(1200)
    link = page.url if is_site(page.url) and urlsplit(page.url).path == '/assist/detail' else published_link(page, row)
    if link:
        attach(row['doi'], link, 'submitting')
    else:
        update(row['doi'], 'uncertain', '请核对官网“我的求助”，如已发布可粘贴详情页链接。', before='submitting')


def retrieve(page, row):
    parsed = urlsplit(row['post_url'])
    visit(page, parsed.path + '?' + parsed.query)
    if not visible(page.get_by_text(row['title'], exact=True)):
        update(row['doi'], 'submitted', '官网详情页标题待核对。', before='submitted')
        return
    button = one(page.get_by_text(re.compile(r'^(?:普通下载|下载文件|下载文献)$')))
    if button is None:
        update(row['doi'], 'submitted', '等待应助或需在官网手动选择下载入口。', before='submitted')
        return
    destination = download_path(row)
    partial = destination.with_suffix('.received.part')
    try:
        with page.expect_download(timeout=9000) as download:
            button.click()
        download.value.save_as(partial)
        try:
            pdf_matches(partial, row)
        except Exception:
            review = destination.with_suffix('.待核对.pdf')
            with partial.open('rb') as source:
                if source.read(5) != b'%PDF-':
                    raise ValueError('下载内容不是 PDF。')
            partial.replace(review)
            update(row['doi'], 'review', '已保存 PDF，需核对文件内容。', before='submitted', file=str(review))
            return
        partial.replace(destination)
        update(row['doi'], 'downloaded', '已保存 PDF 并核对标题。请在官网查看应助采纳状态。',
               before='submitted', file=str(destination))
    except BrowserTimeout:
        update(row['doi'], 'submitted', '官网需要选择下载方式或暂无可下载的应助文件。', before='submitted')
    finally:
        partial.unlink(missing_ok=True)


def run(*, checkin=True, doi=None, submit_queued=True):
    day = clock().date().isoformat()
    states = {'submitting', 'uncertain', 'submitted'}
    if submit_queued:
        states.add('queued')
    rows = [row for row in list_requests() if row['state'] in states and (doi is None or row['doi'] == doi)]
    if not rows and (not checkin or sign_status() == '官网确认今日已签到。'):
        return
    with browser() as context:
        page = context.pages[0]
        if checkin:
            signin(page, day)
        for row in rows:
            try:
                if row['state'] == 'queued':
                    if not try_open_copy(row):
                        submit(page, row)
                elif row['state'] == 'submitted':
                    retrieve(page, row)
                else:
                    link = published_link(page, row)
                    if link:
                        attach(row['doi'], link, row['state'])
            except NeedsLogin:
                raise
            except RuntimeError as exc:
                update(row['doi'], 'action' if row['state'] == 'queued' else row['state'], str(exc), before=row['state'])
            except Exception as exc:
                update(row['doi'], row['state'], f'网站操作未完成（{type(exc).__name__}）。', before=row['state'])
