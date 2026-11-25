"""Allow ``python -m scraper``."""

import sys

from .cli import main

sys.exit(main())
