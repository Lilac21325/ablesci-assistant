import argparse
import json
import sys
from pathlib import Path

import requests

from browser import NeedsLogin
from library import list_requests, lookup, normalize_doi, try_open_copy, update
from workflow import run


def search_title(title):
    response = requests.get('https://api.crossref.org/works',
                            params={'query.bibliographic': title, 'rows': 5}, timeout=20)
    response.raise_for_status()
    results = []
    for work in response.json()['message']['items']:
        date = (work.get('issued', {}).get('date-parts') or [[]])[0]
        author = next(iter(work.get('author', [])), {})
        results.append({
            'doi': work['DOI'], 'title': next(iter(work.get('title', [])), ''),
            'year': date[0] if date else None,
            'first_author': ' '.join(filter(None, (author.get('given'), author.get('family')))),
            'journal': next(iter(work.get('container-title', [])), ''),
        })
    return {'candidates': results}


def existing(doi):
    return next((row for row in list_requests() if row['doi'] == doi), None)


def report(row):
    result = {key: row[key] for key in ('doi', 'title', 'publisher', 'state', 'points', 'post_url', 'file', 'note')}
    result['file_exists'] = bool(row['file'] and Path(row['file']).is_file())
    return result


def positive(value):
    points = int(value)
    if points < 1:
        raise argparse.ArgumentTypeError('悬赏积分必须为正整数。')
    return points


def execute(args):
    if args.command == 'search':
        return search_title(args.title)

    doi = normalize_doi(args.doi)
    if args.command == 'inspect':
        return report(lookup(doi))

    row = existing(doi)
    if row is None:
        raise ValueError('请先用 inspect 核对这篇文献。')

    if args.command == 'fetch':
        if row['state'] in ('draft', 'action'):
            found = try_open_copy(row)
            return {**report(existing(doi)), 'public_pdf_saved': found}
    elif args.command == 'request':
        if row['state'] not in ('draft', 'action'):
            return report(row)
        if not update(doi, 'queued', '已授权，等待提交。', before=row['state'], points=args.points):
            return report(existing(doi))
        try:
            run(checkin=False, doi=doi)
        except (NeedsLogin, RuntimeError) as exc:
            return {**report(existing(doi)), 'attention': str(exc)}
    elif args.command == 'sync':
        try:
            run(checkin=False, doi=doi, submit_queued=False)
        except (NeedsLogin, RuntimeError) as exc:
            return {**report(existing(doi)), 'attention': str(exc)}

    return report(existing(doi))


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description='核对、下载和跟踪指定文献')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('search').add_argument('title')
    for command in ('inspect', 'fetch', 'request', 'status', 'sync'):
        sub = commands.add_parser(command)
        sub.add_argument('doi')
        if command == 'request':
            sub.add_argument('--points', type=positive, required=True)

    try:
        result = execute(parser.parse_args())
    except (ValueError, RuntimeError, requests.RequestException) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
