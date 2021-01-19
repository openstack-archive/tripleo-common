#!/usr/bin/python3
import argparse
import os
import requests

default_output = ("\n%(http_code)s %(remote_ip)s:%(remote_port)s "
                  "%(time_total)s seconds\n")

parser = argparse.ArgumentParser(description='Check remote HTTP')
parser.add_argument('uri', metavar='URI', type=str, nargs=1,
                    help='Remote URI to check')
parser.add_argument('--max-time', type=int, default=10,
                    help=('Maximum time in seconds that you allow the'
                          ' whole operation to take.')
                    )
parser.add_argument('--user-agent', type=str, default='pyrequests-healthcheck',
                    help=('Specify the User-Agent string to send to the'
                          ' HTTP server.')
                    )
parser.add_argument('--write-out', type=str, default=default_output,
                    help=('Display information on stdout after a completed'
                          ' transfer.')
                    )

args = parser.parse_args()
uri = args.uri[0]
output = args.write_out.replace('%{', '%(').replace('}', ')s') \
    .replace('\\n', os.linesep)

headers = {'User-Agent': args.user_agent}
with requests.get(uri, headers=headers, timeout=args.max_time,
                  allow_redirects=True, stream=True, verify=False) as req:
    r_ip, r_port = req.raw._original_response.fp.raw._sock.getpeername()
    resp = {'http_code': req.status_code,
            'remote_ip': r_ip,
            'remote_port': r_port,
            'time_total': req.elapsed.total_seconds()
            }
    try:
        print(output % resp)
    except KeyError:
        print(default_output % resp)
    except ValueError:
        print(default_output % resp)
