import re
import logging
from urllib.parse import urljoin

import requests_cache
from bs4 import BeautifulSoup
from tqdm import tqdm

from configs import configure_argument_parser, configure_logging
from constants import (BASE_DIR, MAIN_DOC_URL, MAIN_PEP_URL,
                       EXPECTED_STATUS, PARSER, VERSION_STATUS_PATTERN)
from outputs import control_output
from exceptions import NotFoundException
from utils import get_response, find_tag


def whats_new(session):
    whats_new_url = urljoin(MAIN_DOC_URL, 'whatsnew/')
    response = get_response(session, whats_new_url)
    soup = BeautifulSoup(response.text, PARSER)
    main_div = find_tag(soup, 'section', attrs={'id': 'what-s-new-in-python'})
    div_with_ul = find_tag(main_div,
                           'div', attrs={'class': 'toctree-wrapper'})
    sections_by_python = div_with_ul.find_all('li',
                                              attrs={'class': 'toctree-l1'})

    results = [('Ссылка на статью', 'Заголовок', 'Редактор, автор')]
    for section in tqdm(sections_by_python):
        version_a_tag = section.find('a')
        version_link = urljoin(whats_new_url, version_a_tag['href'])
        response = get_response(session, version_link)
        if response is None:
            continue
        soup = BeautifulSoup(response.text, PARSER)
        h1 = find_tag(soup, 'h1')
        dl = find_tag(soup, 'dl')
        dl_text = dl.text.replace('\n', ' ')
        results.append(
            (h1.text, version_link, dl_text)
        )

    return results


def latest_versions(session):
    response = get_response(session, MAIN_DOC_URL)
    soup = BeautifulSoup(response.text, PARSER)

    sidebar = find_tag(soup, 'div', {'class': 'sphinxsidebarwrapper'})

    ul_tags = sidebar.find_all('ul')

    for ul in ul_tags:
        if 'All versions' in ul.text:
            a_tags = ul.find_all('a')
            break
    else:
        raise NotFoundException('Ничего не нашлось')

    results = [('Ссылка на документацию', 'Версия', 'Статус')]
    for a_tag in a_tags:
        link = a_tag['href']
        text_match = VERSION_STATUS_PATTERN.search(a_tag.text)
        if text_match is not None:
            version, status = text_match.groups()
        else:
            version, status = a_tag.text, ''
        results.append(
            (link, version, status)
        )
    return results


def download(session):
    downloads_url = urljoin(MAIN_DOC_URL, 'download.html')
    response = get_response(session, downloads_url)

    soup = BeautifulSoup(response.text, PARSER)

    main_tag = find_tag(soup, 'div', {'role': 'main'})
    table_tag = find_tag(main_tag, 'table', {'class': 'docutils'})

    pdf_a4_tag = find_tag(table_tag, 'a',
                          {'href': re.compile(r'.+pdf-a4\.zip$')})

    pdf_a4_link = pdf_a4_tag['href']
    archive_url = urljoin(downloads_url, pdf_a4_link)

    filename = archive_url.split('/')[-1]

    downloads_dir = BASE_DIR / 'downloads'
    downloads_dir.mkdir(exist_ok=True)
    archive_path = downloads_dir / filename

    response = session.get(archive_url)

    with open(archive_path, 'wb') as file:
        file.write(response.content)
    logging.info(f'Архив был загружен и сохранён: {archive_path}')


def pep(session):
    response = get_response(session, MAIN_PEP_URL)
    soup = BeautifulSoup(response.text, PARSER)
    numerical_index = find_tag(soup, 'section', {'id': 'numerical-index'})
    tbody = find_tag(numerical_index, 'tbody')
    tr = tbody.find_all('tr')
    pep_count = 0
    status_count = {}
    results = [('Статус', 'Количество')]
    for pep in tqdm(tr):
        pep_count += 1
        status_short = pep.find('td').text[1:]
        if status_short in EXPECTED_STATUS:
            status_long = EXPECTED_STATUS[status_short]
        else:
            status_long = []
            logging.info(
                f'В списке есть неверно указанный статус: {status_short}'
                f'В строке: {pep}'
            )
        pep_link_short = pep.find('a')['href']
        pep_link_full = urljoin(MAIN_PEP_URL, pep_link_short)
        response = get_response(session, pep_link_full)
        soup = BeautifulSoup(response.text, PARSER)
        dl_table = find_tag(soup, 'dl', {'class': 'rfc2822 field-list simple'})
        status_line = dl_table.find(string='Status')
        if status_line:
            status_parent = status_line.find_parent()
            status_page = status_parent.next_sibling.next_sibling.string
            if status_page not in status_long:
                logging.info(
                    f'Несовпали статусы PEP: {pep_link_full}'
                    f'Статус на странице - {status_page}'
                    f'Статус в списке - {status_long}'
                )
            if status_page in status_count:
                status_count[status_page] += 1
            else:
                status_count[status_page] = 1
        else:
            logging.error(
                f'На странице PEP {pep_link_full}'
                'В таблице нет строки статуса.'
            )
            continue
    results.extend(status_count.items())
    results.append(('Total', pep_count))
    return results


MODE_TO_FUNCTION = {
    'whats-new': whats_new,
    'latest-versions': latest_versions,
    'download': download,
    'pep': pep,
}


def main():
    configure_logging()
    logging.info('Парсер запущен!')

    arg_parser = configure_argument_parser(MODE_TO_FUNCTION.keys())
    args = arg_parser.parse_args()
    logging.info(f'Аргументы командной строки: {args}')

    session = requests_cache.CachedSession()
    if args.clear_cache:
        session.cache.clear()

    parser_mode = args.mode
    results = MODE_TO_FUNCTION[parser_mode](session)

    if results is not None:
        control_output(results, args)
    logging.info('Парсер завершил работу.')


if __name__ == '__main__':
    main()
