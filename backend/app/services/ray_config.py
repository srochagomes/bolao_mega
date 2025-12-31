"""
Ray configuration module
Configures Ray to suppress warnings and disable unnecessary features
Should be imported before ray is initialized
"""
import os
import warnings

# Configure environment variables before Ray is imported
# These must be set before ray.init() is called

# Disable metrics export to avoid connection warnings
os.environ.setdefault("RAY_DISABLE_IMPORT_WARNING", "1")
os.environ.setdefault("RAY_ACCEL_ENV_VAR_OVERRIDE_ON_ZERO", "0")

# Disable metrics collection
os.environ.setdefault("RAY_ENABLE_METRICS_COLLECTION", "0")

# Suppress Ray warnings
warnings.filterwarnings("ignore", category=FutureWarning, module="ray.*")
warnings.filterwarnings("ignore", message=".*metrics.*")
warnings.filterwarnings("ignore", message=".*accelerator.*")
warnings.filterwarnings("ignore", message=".*exporter.*")

