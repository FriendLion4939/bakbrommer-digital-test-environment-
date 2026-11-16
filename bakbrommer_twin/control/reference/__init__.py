"""Reference controller: the STM32G4 control logic written as readable Python.

Each file is one function block of the firmware (speed estimate, ride modes,
engine start/stop, traction control, torque vectoring, regen, limits);
``controller.py`` calls them in order. The blocks use only simple arithmetic
and a few state variables each, so they translate line by line into C.
"""
