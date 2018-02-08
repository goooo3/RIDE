from cx_Freeze import setup, Executable

# exclude unneeded packages. More could be added. Has to be changed for
# other programs.
#build_exe_options = {"excludes": ["tkinter", "tcl", "tk"],
#                     "optimize": 2}

# Dependencies are automatically detected, but it might need
# fine tuning.
buildOptions = {"packages": [], "excludes": ['tkinter', 'tcl', 'tk', 'tcl8.6', 'tk8.6', 'lib-dynload'],
                    "optimize":2}

import sys
base = 'Win32GUI' if sys.platform=='win32' else None

executables = [
    Executable('robotide/__init__.py', base=base, targetName = 'ride')
]

setup(name='RIDE',
      version = '1.7.1',
      description = 'RIDE - Robot Framework Integrated Development Editor',
      options = {"build_exe": buildOptions},
      executables = executables)
