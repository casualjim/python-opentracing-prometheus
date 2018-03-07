from setuptools import setup

setup(
  name='opentracing_prometheus',
  version='0.1.3',
  description='OpenTracing Jaeger and Prometheus integration',
  classifiers=[
    'Development Status :: 3 - Alpha',
    'License :: OSI Approved :: MIT License',
    'Programming Language :: Python :: 2.7',
    'Topic :: System :: Monitoring',
  ],
  keywords='opentracing jaeger prometheus',
  url='https://github.com/casualjim/python-opentracing-prometheus',
  author='Ivan Porto Carrero',
  license='MIT',
  packages=['opentracing_prometheus'],
  install_requires=[
    'opentracing_instrumentation',
    'jaeger-client',
    'prometheus_client',
  ],
  platforms='any',
  modules=['six', ]
)
