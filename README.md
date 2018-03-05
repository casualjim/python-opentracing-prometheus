# OpenTracing Prometheus

An integration for opentracing and prometheus.
It exposes the same metrics as jaeger and prometheus for golang.

This package contains a PrometheusReporter and PrometheusMetricsFactory

The reporter is used to report on metrics based on span contents
The factory is used to report on metrics from jaeger itself.

There is also a wsgi middleware that combines all the options.

## Middleware

```python
from flask import Flask, make_response
from opentracing_prometheus import TracerMiddleware

import requests
import logging
import sys
import os
import datetime

app = Flask('prometheus-tracing')

logging.basicConfig(stream=sys.stderr)
log_level = logging.DEBUG
logging.getLogger('').handlers = []
logging.basicConfig(format='%(asctime)s %(message)s', level=log_level)

app.wsgi_app = TracerMiddleware(app)
log = logging.getLogger()

@app.route('/')
def fetch_hello_world():
  resp = make_response('Hello, World!')
  resp.headers['Content-Type'] = 'text/plain'
  return resp

if __name__ == '__main__':
  app.run(host='0.0.0.0', port=5000)

```

You can then make a few requests to localhost:5000 and check the metrics at: http://localhost:5000/metrics
