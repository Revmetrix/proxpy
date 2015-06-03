# import argparse
#
# parser = argparse.ArgumentParser(description='Process some integers.')
# parser.add_argument('appid')
#
# args = parser.parse_args()
# print(args.accumulate(args.integers))
#
# if args.inject == 'revjs-local':
#     src = '/dist/' + revJsFilename
# else:
#     src = '//static.revmetrix.com/' + revJsFileName
import StringIO
import gzip
import logging
import threading
import pprint
import traceback
import sys

pprinter = pprint.PrettyPrinter(indent=4)

logging.basicConfig(level=logging.DEBUG)

req_dict_lock = threading.Lock()
req_by_thread_id_dict = {}
req_count = 0

REV_TAG = """<script type="text/javascript">var _rev = _rev || {{}};
  _rev["_revAppId"] = "{appid}";
  (function() {{
    var reva = document.createElement('script'); reva.type = 'text/javascript'; reva.async = true;
    reva.src = "{src}";
    var s = document.getElementsByTagName('script')[0]; s.parentNode.insertBefore(reva, s);
    }})();</script>""".format(
    appid='stm_3c1f62b47e6431e4',
    src='//static.revmetrix.com/rev-gc-min.js')

def proxy_mangle_request(req):
    _store_request(req)
    logging.info("Processing request  [{}]: {}".format(req.req_number, req.url))
    return req


def proxy_mangle_response(res):
    try:
        req = _get_request()
        logging.info("Processing response [{}] {}: {}".format(req.req_number, res.code, req.url))
        if _is_html_response(res):
            res.body = _insert_revjs_into_response_body(res)
            fix_content_length(res)
    except Exception as e:
        logging.error(traceback.format_exc())
    finally:
        _pop_request()
        return res


def fix_content_length(res):
    # Chunked responses lack a Content-Length header
    if len(res.getHeader('Content-Length')) > 0:
        res.setHeader('Content-Length', sys.getsizeof(res.body))


def _is_html_response(res):
    v = res.getHeader("Content-Type")
    return len(v) > 0 and "text/html" in v[0]


def _get_content_encoding(res):
    ce = res.getHeader("Content-Encoding")
    if len(ce) > 0:
        return ce[0]
    return None


def _insert_revjs_into_response_body(res):
    encoding = _get_content_encoding(res)
    if encoding is None:
        return _insert_revjs_into_html(res.body)
    elif encoding == 'gzip':
        return _insert_revjs_into_gzip(res.body)
    else:
        req = _get_request()
        logging.error("Unsupported content encoding [{}]({}): {}".format(req.req_number, req.url, encoding))
        return res.body


def _insert_revjs_into_html(html):
    index = html.find('</body>')
    if index < 0:
        req = _get_request()
        logging.warn('</body> not found in HTML response [{}]: {}'.format(req.req_number, req.url))
        return html
    return html[:index] + REV_TAG + html[index:]


def _insert_revjs_into_gzip(data):
    io_in = StringIO.StringIO(data)
    with gzip.GzipFile(mode='rb', fileobj=io_in) as gzip_in:
        text = gzip_in.read()
        injected = _insert_revjs_into_html(text)
        io_out = StringIO.StringIO()
        with gzip.GzipFile(mode='wb', fileobj=io_out) as gzip_out:
            gzip_out.write(injected)
            gzip_out.close()
            io_out.seek(0)
            new_data = io_out.read()
    return new_data


def _store_request(req):
    global req_count
    with req_dict_lock:
        req.req_number = req_count
        req_count += 1
        thread_id = threading.current_thread().ident
        req_by_thread_id_dict[thread_id] = req


def _get_request():
    with req_dict_lock:
        thread_id = threading.current_thread().ident
        return req_by_thread_id_dict[thread_id]


def _pop_request():
    with req_dict_lock:
        thread_id = threading.current_thread().ident
        return req_by_thread_id_dict.pop(thread_id)