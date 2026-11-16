"""Software-in-the-loop: run controller C code (compiled for the PC) in the simulator.

See docs/SIL.md. ``header.py`` generates the C header from the Python
interface, ``build.py`` compiles a C file into a shared library and
``bridge.py`` loads it as a controller.
"""
