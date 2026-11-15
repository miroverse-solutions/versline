"""Importing this package registers every bridge tool.

Tool modules only define parameter models and thin run functions; the heavy services they use are imported
inside the run functions, so ``versline bridge info`` stays fast. To add a tool: create a module here (or add
to one), decorate a function with ``@tool(...)``, and list the module below.
"""
from versline.bridge.tools import export, media, organize, study, system, telegram, text  # noqa: F401
