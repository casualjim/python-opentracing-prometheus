from prometheus_client import REGISTRY, Histogram, Counter, Gauge
from jaeger_client.metrics import MetricsFactory
from jaeger_client.reporter import NullReporter
from jaeger_client import Span
from threading import Lock
from math import ceil
import six
import re
import inspect


_INF = float("inf")
_MINUS_INF = float("-inf")
_BUCKETS=(.005, .01, .025, .05, .075, .1, .25, .5, .75, 1.0, 2.5, 5.0, 7.5, 10.0, _INF)
_NORM_RE = re.compile("[^a-zA-Z0-9-_/.]")
_NS_RE = re.compile("[-.]")
METRICS_NAME_OPERATION = 'operations'
METRICS_NAME_HTTP_REQUESTS = 'requests'
METRICS_NAME_HTTP_REQUEST_LATENCY = 'request_latency'
METRICS_NAME_HTTP_STATUS_CODES = "http_requests"
LABEL_PARENT_SERVICE_UNKNOWN = 'unknown'

def default_normalize(name):
  return _NORM_RE.sub('-', name)

def metric_name(name, namespace=''):
  if not namespace:
    return _NS_RE.sub('_', name)
  if not name:
    return _NS_RE.sub('_', namespace)

  return _NS_RE.sub('_', namespace) + ':' + _NS_RE.sub('_', name)

class HTTPMetrics(object):

  def __init__(self, namespace='', normalize=default_normalize):
    self.namespace = namespace
    self.normalize = normalize or default_normalize

    self.requests = Counter(
      self.metric_name(METRICS_NAME_HTTP_REQUESTS),
      'Counts the number of requests made distinguished by their endpoint and error status',
      ['endpoint', 'error']
    )

    self.latency = Histogram(
      self.metric_name(METRICS_NAME_HTTP_REQUEST_LATENCY),
      'Duration of HTTP requests in second distinguished by their endpoint and error status',
      ['endpoint', 'error']
    )

    self.status_codes = Counter(
      self.metric_name(METRICS_NAME_HTTP_STATUS_CODES),
      'Counts the responses distinguished by endpoint and status code bucket',
      ['endpoint', 'status_code']
    )


  def record(self, span):
    status_code = self.get_int_tag(span, 'http.status_code')
    sc = status_code/100

    endpoint = self.normalize(span.operation_name)
    if not endpoint:
      endpoint = "other"

    error = self.get_tag(span, 'error')
    if not error or error.lower() == 'false':
      error = 'false'
    else:
      error = 'true'

    self.requests.labels(endpoint, error).inc(1)
    self.latency.labels(endpoint, error).observe(span.end_time-span.start_time)
    if sc >= 2 and sc <= 5:
      self.status_codes.labels(endpoint, str(sc)+'xx').inc(1)

  def get_int_tag(self, span, key):
    tg = self.get_tag(span, key)
    if not tg:
      return 0
    return int(tg)

  def get_tag(self, span, key):
    for tag in span.tags:
      if tag.key == key:
        if hasattr(tag, 'value'):
          return str(tag.value)
        break

    return ''

  def metric_name(self, name):
    return metric_name(name, namespace=self.namespace)

class PrometheusReporter(NullReporter):

  def __init__(self, namespace='', normalize=default_normalize):
    self.histograms = {}
    self.lock = Lock()
    self.namespace = namespace
    self.normalize = normalize or default_normalize
    self._http_metrics = HTTPMetrics(namespace=namespace, normalize=normalize)
    self._operation_metrics = Histogram(
      self.metric_name(METRICS_NAME_OPERATION),
      'Duration of operations in microsecond',
      ['name']
    )

  def report_span(self, span):
    srv = self.get_tag(span, 'span.kind')
    surl = self.get_tag(span, 'http.url')
    smeth = self.get_tag(span, 'http.method')
    if srv == 'server' and (surl or smeth):
      self._http_metrics.record(span)
      return
    else:
      self._operation_metrics.labels(self.normalize(span.operation_name)).observe(span.end_time-span.start_time)

  def get_tag(self, span, key):
    for tag in span.tags:
      if tag.key == key:
        if hasattr(tag, 'value'):
          return str(tag.value)
        break

    return ''

  def metric_name(self, name):
    return metric_name(name, namespace=self.namespace)

class VectorCache(object):

  def __init__(self, registry=REGISTRY):
    self._lock = Lock()
    self._counters = {}
    self._histograms = {}
    self._gauges = {}
    self.registry = registry

  def get_or_create_counter(self, name, labels):
    with self._lock:
      if name not in self._counters:
        cv = Counter(name, name, labels, registry=self.registry)
        self._counters[name] = cv

      return self._counters[name]

  def get_or_create_histogram(self, name, labels):
    with self._lock:
      if name not in self._histograms:
        hv = Histogram(name, name, labels, registry=self.registry)
        self._histograms[name] = hv

      return self._histograms[name]

  def get_or_create_gauge(self, name, labels):
    with self._lock:
      if name not in self._gauges:
        gv = Gauge(name, name, labels, registry=self.registry)
        self._gauges[name] = gv

      return self._gauges[name]


class PrometheusMetricsFactory(MetricsFactory):
  """A MetricsFactory adapter for a prometheus registry."""

  def __init__(self, namespace='', registry=REGISTRY, tags={}):
    self.registry = registry
    self.namespace = namespace
    self.tags = tags
    self._cache = VectorCache(registry=registry)

  def create_counter(self, name, tags={}):
    tags = self._merge_tags(tags)
    keys = self._tags_as_label_names(tags)
    values = self._tags_as_label_values(keys, tags)

    c = self._cache.get_or_create_counter(self._get_key_name(name), keys)
    def inc(value):
      c.labels(*values).inc(value)
    return inc

  def create_timer(self, name, tags={}):
    tags = self._merge_tags(tags)
    keys = self._tags_as_label_names(tags)
    values = self._tags_as_label_values(keys, tags)

    h = self._cache.get_or_create_histogram(self._get_key_name(name), keys)
    def observe(value):
      h.labels(*values).observe(value)

    return observe

  def create_gauge(self, name, tags={}):
    tags = self._merge_tags(tags)
    keys = self._tags_as_label_names(tags)
    values = self._tags_as_label_values(keys, tags)

    g = self._cache.get_or_create_gauge(self._get_key_name(name), keys)
    def update(value):
      g.labels(*values).set(value)
    return update

  def _get_key_name(self, name):
    if not self.namespace:
      return self._normalize(name)
    if not name:
      return self._normalize(self.namespace)

    return self._normalize(self.namespace + ':' + name)

  def _normalize(self, name):
    return name.replace('.', '_').replace('-', '_')

  def _tags_as_label_names(self, tags):
    if tags is None:
      return []
    return sorted(tags.keys())

  def _tags_as_label_values(self, labels, tags):
    if labels is None:
      labels = []
    result = []
    for l in labels:
      result.append(tags[l])
    return result

  def _merge_tags(self, tags):
    if tags is None:
      tags = {}
    if self.tags is None:
      self.tags = {}

    result = self.tags.copy()
    result.update(tags)
    return result
