#! /usr/bin/env python
# -*- coding=utf-8 -*-

import os
import re
import csv
import email
import base64
import binascii
import threading
import mimetypes
import quopri
from field_names import fieldnames

muxlock = threading.Lock()
mail_dir = '/Users/vayne/dnc-mails'
fieldnames = map(lambda filed: filed.lower(), fieldnames)


def get_chunks(l, n=100):
    for i in range(0, len(l), n):
        yield l[i: i+n]


def decode_base64(str):
    if re.findall('=[a-z0-9]{2}', str):
        return quopri.decodestring(str)
    elif not re.findall('[^A-Za-z0-9/+=]', str):
        try:
            str = base64.decodestring(str)
        except binascii.Error:
            pass
    return quopri.decodestring(str)


def split_name_and_address(_value):
    if re.match('^[\w.-]+@.*', _value):
        addresses_str = ';'.join(re.findall('[\w.+-]+@[\w.+-]*', _value)).strip(';')
    else:
        addresses_str = ';'.join(re.findall('[<(\'\[* ](?:mailto:)?([\w.+-]+@[\w.+-]*)', _value)).strip(';')
        if not addresses_str:
            addresses_str = ';'.join(re.findall('[<(\[* ](?:http.*?mailto:)?([\w.+-]+@[\w.+-]*)', _value)).strip(';')
    names = map(lambda name: name.strip(' ,;\'"\r\n\t<>[]('), re.split('(?:http.*?)?(?:mailto:)?[\w.+-]+@[\w.+-]*', _value))
    for value in ['mailto:', 'mailto', 'on', 'On', 'info=', 'mailto:info=', 'news=', 'mailto:news=']:
        try:
            names.remove(value)
        except ValueError:
            pass
    names_str = ';'.join(names).strip(';')
    return names_str, addresses_str


def decode_str(mess_string):
    useful_parts = []
    if '=?' not in mess_string:
        return quopri.decodestring(mess_string)
    while '=?' in mess_string:
        useful_part = re.findall('\?(?:utf-8|Windows-125\d|big5|GBK|koi8-r|ANSI|iso-2022|iso-8859-\d+|Cp1252|cp932|US-ASCII)[^?]*\?[A-Z]\?(.*)',
                                 flags=re.IGNORECASE | re.DOTALL, string=mess_string)
        if not useful_part and '=?=' in mess_string:
            break
        assert len(useful_part) == 1, (mess_string, useful_part)
        found_segment = re.split('=\?(?:utf|win|iso|cp|us|big|gbk|koi|ANSI)', flags=re.IGNORECASE, string=mess_string)[0].rstrip(' \r\n\t')
        if '?=' in found_segment:
            found_segment = re.split('\?=', found_segment)[0]
        useful_parts.append(decode_base64(found_segment))
        mess_string = useful_part[0]
    useful_parts.append(decode_base64(''.join(mess_string.split('?='))))
    return ''.join(useful_parts)


def parse_the_fw_mail(_mail):
    this_mail = {}
    if re.match('\n[\s>*]*from', _mail, flags=re.IGNORECASE):
        pairs = re.findall('\n[\s>*]*(?:from|sent|to|cc|subject|bcc|date):.*', _mail, flags=re.IGNORECASE)
        for pair in pairs:
            kv = pair.split(':')
            key = kv[0].strip('\r\n\t >*').lower()
            assert key in ['from', 'sent', 'to', 'cc', 'bcc', 'subject', 'date']
            value = ':'.join(kv[1:]).strip('\r\n\t *')
            if key in ['sent', 'date']:
                split_date(value, this_mail)
            else:
                this_mail[key] = value
            if key in ['from', 'to', 'cc', 'bcc']:
                if this_mail.get(key):
                    this_mail[key + '-name'], this_mail[key + '-address'] = split_name_and_address(this_mail[key])

        lines = _mail.split('\n')
        useful_lines = []
        for i, line in enumerate(lines):
            if re.findall('[\s>*]*(from|sent|to|cc|subject|bcc|date):.*', line, re.IGNORECASE):
                continue
            else:
                useful_lines.append(line)
            this_mail['simplify-content'] = '\n'.join(useful_lines)
    elif re.match('^on (?:Sun|Mon|Tue|Wed|Thu|Fri|Sat|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Otc|Nov|Dec).{0,160}? wrote:',
                  _mail, re.IGNORECASE):
        contents = re.split(' wrote:', _mail, re.IGNORECASE)
        from_add = contents[0]
        this_mail['simplify-content'] = ' wrote:'.join(contents[1:]).strip('\r\n\t ')
        from_adds = re.split(' (PM|AM)[, ]*', from_add, re.IGNORECASE)
        if len(from_adds) == 1:
            from_adds = re.split(' (\d\d\d\d)', from_add, re.IGNORECASE)
            if len(from_adds) == 1:
                from_adds = re.split('[/ ](\d\d?),', from_add, re.IGNORECASE)
                if len(from_adds) == 1:
                    from_adds = re.split('(day),', from_add, re.IGNORECASE)
        split_date(' '.join(from_adds[0:2]), this_mail)
        try:
            sender = from_adds[2]
            this_mail['from'] = sender
            this_mail['from-name'], this_mail['from-address'] = split_name_and_address(sender)
        except Exception as e:
            print e
            print from_add,

    return this_mail


def split_date(date, mail):
    """

    :param date: string like 'Fri, 20 May 2016 11:30:27 -0700'
    :param mail: dict
    :return:
    """
    mail['date'] = date
    if re.findall('\d{1,2}/\d{1,2}/\d{4}', date):
        mail['month'], mail['day'], mail['year'] = re.findall('\d{1,2}/\d{1,2}/\d{4}', date)[0].split('/')
    elif re.findall('\d{4}-\d{1,2}-\d{1,2}', date):
        mail['year'], mail['month'], mail['day'] = re.findall('\d{4}-\d{1,2}-\d{1,2}', date)[0].split('-')
    else:
        mail['day'] = ' '.join(re.findall('[, ](\d{1,2})[ ,]', date))
        mail['month'] = ''.join(
            re.findall('Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Otc|Nov|Dec', date, re.IGNORECASE))
        mail['year'] = ''.join(re.findall('[, ]([12]\d{3})[, ]?', date))

    mail['wday'] = ''.join(re.findall('Sun|Mon|Tue|Wed|Thu|Fri|Sat', date, re.IGNORECASE))

    if re.findall('\d{1,2}:\d{1,2}:\d{1,2}', date):
        mail['hour'], mail['minute'], mail['second'] = re.findall('\d{1,2}:\d{1,2}:\d{1,2}', date)[0].split(':')
    if re.findall('\d{1,2}:\d{1,2}', date):
        mail['hour'], mail['minute'] = re.findall('\d{1,2}:\d{1,2}', date)[0].split(':')

    month = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6, 'jul': 7,
             'aug': 8, 'sep': 9, 'otc': 10, 'nov': 11, 'dec': 12}
    for m, v in month.items():
        if not isinstance(mail['month'], int) and mail['month'].lower().startswith(m):
            mail['month'] = v


def parse_mail(mail_file):

    def split_subject_prefix(subject):
        re_num = fw_num = 0
        if not subject:
            return
        subject_abbreviations = ''.join(re.findall('^[\r\t\n ]*((?:(?:re:|fw:|fwd:) *)+)', flags=re.IGNORECASE, string=subject))\
            .lower().strip(' :\r\n\t')
        if not subject_abbreviations:
            mail['subject_abbreviations'] = 'none'
            mail['first_abbreviations'] = 'none'
        else:
            abbs = subject_abbreviations.split(':')
            for i in abbs:
                if 're' in i:
                    re_num += 1
                elif 'fw' in i:
                    fw_num += 1

            mail['subject_abbreviations'] = subject_abbreviations
            mail['first_abbreviations'] = abbs[0]

        mail['re_num'] = re_num
        mail['fw_num'] = fw_num

    def encode_new_line(_mail):
        for _key, _value in _mail.items():
            if isinstance(_value, str) and '\n' in _value:
                _mail[_key] = re.sub('\n', '=n', re.sub('\r', '=r', _value))

    with open(mail_file) as fp:
        msg = email.message_from_file(fp)
        mail = {}
        attachment_filenames = []
        attachment_file_types = []
        mail['has-attachment'] = 0
        for key, value in msg.items():
            if key.lower() == 'date':
                split_date(value, mail)
            elif key.lower() in ['subject', 'thread-topic', 'from', 'to']:
                mail[key.lower()] = decode_str(value)
            elif key.lower() in fieldnames:
                mail[key.lower()] = value
        for part in msg.walk():
            if part.get_content_maintype() == 'multipart' or part.get_content_type() == 'text/html':
                continue
            if part.get_all('Content-Disposition') and 'attachment;' in ';'.join(part.get_all('Content-Disposition')):
                mail['has-attachment'] = 1
                if part.get_filename():
                    name, ext = os.path.splitext(part.get_filename())
                    attachment_filenames.append(name)
                if part.get_content_type():
                    ext = mimetypes.guess_extension(part.get_content_type())
                    if not ext:
                        ext = part.get_content_type()
                    attachment_file_types.append(ext.strip('\r\n\t .'))
            if part.get_content_type().lower() in ['text/plain']:
                mail[part.get_content_type().lower()] = part.get_payload(decode=True)
        mail['mail_path'] = os.path.basename(mail_file)
        mail['attachment_filename'] = '; '.join(attachment_filenames) if attachment_filenames else ''
        mail['attachment_file_type'] = '; '.join(attachment_file_types) if attachment_file_types else ''

    for field in ['from', 'to', 'cc', 'bcc']:
        if mail.get(field):
            mail[field + '-name'], mail[field + '-address'] = split_name_and_address(mail[field])

    if 'text/plain' not in mail:
        encode_new_line(mail)
        return [mail]
    mails_in_one_file = split_mails(mail['text/plain'])
    mail['simplify-content'] = mails_in_one_file[0]
    mails_in_one_file.pop(0)
    all_mails = [mail]

    for _mail in mails_in_one_file:
        this_mail = parse_the_fw_mail(_mail)
        this_mail.update({'mail_path': mail['mail_path']})
        all_mails.append(this_mail)

    for mail in all_mails:
        if 'subject' in mail:
            split_subject_prefix(mail['subject'])
        if 'simplify-content' in mail:
            mail['simplify-content'] = clear_the_content(mail['simplify-content'])
        if 'text/plain' in mail:
            mail.pop('text/plain')
        encode_new_line(mail)
    return all_mails


def split_mails(content):

    def split_mails_by_from_to(_mail):
        _all_mails = []
        contents = re.split('(\n[\s>*]*from:.*\s*[> *]*(?:sent|to|cc|subject|bcc|date):)', _mail, flags=re.IGNORECASE)
        _all_mails.append(contents[0])
        contents.pop(0)
        for i, segment in enumerate(contents):
            if re.match('\n[\s>*]*from', segment, flags=re.IGNORECASE):
                _all_mails.append(''.join([segment, contents[i+1]]))
        return _all_mails

    def split_mails_by_on_wrote(_mail):
        _all_mails = []
        contents = re.split('(on (?:Sun|Mon|Tue|Wed|Thu|Fri|Sat|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Otc|Nov|Dec).{0,160}? wrote:)',
                            flags=re.IGNORECASE, string=_mail)
        _all_mails.append(contents[0])
        contents.pop(0)
        for i, segment in enumerate(contents):
            if re.match('^on (?:Sun|Mon|Tue|Wed|Thu|Fri|Sat|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Otc|Nov|Dec)',
                        flags=re.IGNORECASE, string=segment):
                _all_mails.append(''.join([segment, contents[i+1]]))
        return _all_mails

    all_mails = []
    for mail in split_mails_by_on_wrote(content):
        all_mails.extend(split_mails_by_from_to(mail))
    return all_mails


def convert_to_csv(mail_path, writer):
    mails = parse_mail(mail_path)
    muxlock.acquire()
    for mail in mails:
        if 'from' in mail and 'to' in mail:
            writer.writerow(mail)
    muxlock.release()


def main():
    for _, _, files in os.walk(mail_dir):
        with open('dnc_mails.csv', 'wb') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, delimiter=',', doublequote=True)
            writer.writeheader()
            for mails_chunk in get_chunks(files, n=300):
                threads = [threading.Thread(target=convert_to_csv, args=(os.path.join(mail_dir, mail), writer))
                           for mail in mails_chunk]
                [thread.start() for thread in threads]
                [thread.join() for thread in threads]


if __name__ == '__main__':
    main()
