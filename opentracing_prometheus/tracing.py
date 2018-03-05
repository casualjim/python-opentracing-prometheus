from opentracing_instrumentation.http_server import before_request
from opentracing_instrumentation.http_server import WSGIRequestWrapper
from opentracing_instrumentation.request_context import get_current_span
from opentracing_instrumentation.client_hooks import install_all_patches
from jaeger_client import Config
from jaeger_client.reporter import CompositeReporter
from metrics import PrometheusMetricsFactory, PrometheusReporter, _NORM_RE
from prometheus_client import make_wsgi_app
import opentracing_instrumentation
from opentracing_instrumentation.interceptors import ClientInterceptors, OpenTracingInterceptor
import urlparse

def default_config(service_name):
  return Config(
    config={
      'sampler': {
        'type': 'const',
        'param': 1,
      },
      'logging': True,
      'local_agent': {
        'reporting_host': 'jaeger-agent',
      }
    },
    service_name=service_name,
    metrics_factory=PrometheusMetricsFactory(namespace=service_name)
  )


class NamingClientInterceptor(OpenTracingInterceptor):

  def process(self, request, span):
    parsed = urlparse.urlparse(request.full_url)
    span.set_operation_name('HTTP Client ' + request.method + ' ' + parsed.path)

ClientInterceptors.append(NamingClientInterceptor())

class TracerMiddleware(object):

  def __init__(self, app, config=None):
    self.service_name = app.name
    self.config = config or default_config(app.name)
    install_all_patches()
    self.wsgi_app = create_wsgi_middleware(app.wsgi_app)
    self.init_tracer()

  def __call__(self, environ, start_response):
    return self.wsgi_app(environ, start_response)

  def init_tracer(self):
    self.tracer = self.config.initialize_tracer()
    self.tracer.reporter = CompositeReporter(self.tracer.reporter, PrometheusReporter(namespace=self.service_name))


def create_wsgi_middleware(other_wsgi, tracer=None):
  """
  Create a wrapper middleware for another WSGI response handler.
  If tracer is not passed in, 'opentracing.tracer' is used.
  """

  prometheus_app = make_wsgi_app()
  def wsgi_tracing_middleware(environ, start_response):
    if environ['PATH_INFO'] == '/metrics':
      return prometheus_app(environ, start_response)

    # TODO find out if the route can be retrieved from somewhere
    request = WSGIRequestWrapper.from_wsgi_environ(environ)
    span = before_request(request=request, tracer=tracer)
    nm = '%s %s %s' % (environ['wsgi.url_scheme'].upper(), request.operation.upper(), environ['PATH_INFO'])
    nm = _NORM_RE.sub('-', nm)
    span.set_operation_name(nm)

    # Wrapper around the real start_response object to log
    # additional information to opentracing Span
    def start_response_wrapper(status, response_headers, exc_info=None):
        span.set_tag('error', exc_info is not None)
        span.set_tag('http.status_code', status[:3])
        span.finish()

        return start_response(status, response_headers)

    with opentracing_instrumentation.span_in_context(span):
        return other_wsgi(environ, start_response_wrapper)

  return wsgi_tracing_middleware


