import os
import pathlib

from setuptools import setup, find_packages

HERE = pathlib.Path(__file__).parent.resolve()
LONG_DESCRIPTION = (HERE / "README.md").read_text(encoding="utf8")
LONG_DESC_TYPE = "text/markdown"

try:
      __version__ = os.environ.get('GITHUB_REF_NAME', '0.0.0')
except:
      __version__ = "0.0.0"

VERSION = tuple(map(int, __version__.split('.')))
CURR_VERSION = '.'.join(str(x) for x in VERSION)

setup(name='ixspy-ai-api',
      version=CURR_VERSION,
      description='A client of IXSPY AI  Api',
      long_description=LONG_DESCRIPTION,
      long_description_content_type=LONG_DESC_TYPE,
      author='IXSPY Team',
      author_email='tech@ixspy.com',
      url='https://github.com/ixspyinc/ixspy-ai-api-python',
      license='MIT',
      keywords='',
      packages=find_packages(),
      install_requires=['requests >= 2'],
      classifiers=["Programming Language :: Python :: 3.5",
                   "Programming Language :: Python :: 3.6",
                   "Programming Language :: Python :: 3.7",
                   "Programming Language :: Python :: 3.8",
                   "Programming Language :: Python :: 3.9",
                   "Programming Language :: Python :: 3.10",
                   "Programming Language :: Python :: 3.11",
                   "Programming Language :: Python :: 3.12",
                   "Programming Language :: Python :: 3.13",]
      )
